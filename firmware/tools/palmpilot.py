#!/usr/bin/env python3
"""PalmPilot ESP32-S3 firmware driver: build -> pack -> simulate.

Replaces the ad-hoc shell scripts under tmp/simantic/. All pinned paths come
from firmware/tools/env.sh (CLAUDE.md section 3).

  palmpilot.py build <app>          idf.py build
  palmpilot.py pack  <app>          merge_bin + ROM wrapper -> sim.elf
  palmpilot.py sim   <app> <script> run a harness script against sim.elf
  palmpilot.py run   <app> <script> build + pack + sim
  palmpilot.py system <script>      build + pack LEFT, RIGHT and HUB, then run a
                                    whole-controller script (tools/controller.py);
                                    --replay puts apps/replay in place of the hands
  palmpilot.py env                  print the resolved environment

<app> is a directory containing an ESP-IDF project (CMakeLists.txt), either an
absolute path or one relative to firmware/apps/. `<app>:<variant>` adds the
app's sdkconfig.<variant> on top of sdkconfig.defaults, e.g. `hand:right`.

Build artifacts land in tmp/palmpilot/<app-name>[-<variant>]/ and are gitignored. The
physical board and the simulator are flashed from the SAME bootloader/partition/
app binaries; only the ROM wrapper differs. Keep it that way.
"""
import argparse
import hashlib
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = ROOT / "firmware/components"
ENV_SH = ROOT / "firmware/tools/env.sh"
APPS = ROOT / "firmware/apps"

# Flash offsets are fixed by the ESP32-S3 boot layout; the packer assumes them.
BOOTLOADER_OFFSET, PARTITION_OFFSET, APP_OFFSET = "0x0", "0x8000", "0x10000"


def load_env() -> dict:
    """Source env.sh once and capture the exported variables."""
    if not ENV_SH.exists():
        sys.exit(f"missing {ENV_SH}")
    probe = subprocess.run(
        ["sh", "-c", f". {shlex.quote(str(ENV_SH))} >/dev/null && env -0"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if probe.returncode != 0:
        sys.exit(f"env.sh failed:\n{probe.stderr.strip()}")
    env = dict(
        item.split("=", 1) for item in probe.stdout.split("\0") if "=" in item
    )
    missing = [
        key for key in (
            "IDF_PATH", "IDF_PYTHON_ENV_PATH", "SIMANTIC_HOME",
            "PALMPILOT_PLATFORM", "PALMPILOT_ROM", "PALMPILOT_IMAGE_PACKER",
            "PALMPILOT_SIM_PYTHON",
        ) if not Path(env.get(key, "")).exists()
    ]
    if missing:
        sys.exit("env.sh resolved to missing paths: " + ", ".join(missing))
    Path(env["PALMPILOT_BUILD_ROOT"]).mkdir(parents=True, exist_ok=True)
    return env


class App(type(Path())):
    """An app directory plus the optional sdkconfig variant it is built with."""
    variant = ""


def resolve_app(name: str) -> Path:
    name, _, variant = name.partition(":")
    app = Path(name)
    if not app.is_absolute():
        app = (APPS / name) if (APPS / name).exists() else Path.cwd() / name
    app = app.resolve()
    if not (app / "CMakeLists.txt").exists():
        sys.exit(f"{app} is not an ESP-IDF project (no CMakeLists.txt)")
    app = App(app)
    app.variant = variant
    if variant and not (app / f"sdkconfig.{variant}").exists():
        sys.exit(f"{app} has no sdkconfig.{variant}")
    return app


def build_dir(env: dict, app: Path) -> Path:
    variant = getattr(app, "variant", "")
    return Path(env["PALMPILOT_BUILD_ROOT"]) / (f"{app.name}-{variant}" if variant else app.name)


def run(cmd: list[str], env: dict) -> None:
    print(f"+ {shlex.join(str(c) for c in cmd)}", flush=True)
    if subprocess.run(cmd, cwd=ROOT, env=env).returncode != 0:
        sys.exit("command failed")


# Limits on a simulation run. A healthy run keeps at least one core busy; the engine's
# lock-order deadlock (renode-infrastructure#340) leaves it near 0% CPU with no progress.
MAX_WALL_S = float(os.environ.get("PALMPILOT_MAX_WALL_S", "3600"))
STALL_S = float(os.environ.get("PALMPILOT_STALL_S", "120"))
STALL_CPU = 0.05                    # fraction of one core, averaged over STALL_S


def _cpu_seconds(pid: int) -> float | None:
    out = subprocess.run(["ps", "-o", "time=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    if not out:
        return None
    days, _, clock = out.rpartition("-")
    parts = [float(x) for x in clock.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return (float(days) if days else 0.0) * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]


def _dump_stacks(pid: int, env: dict) -> None:
    """Managed stacks of a stalled engine, next to the run's other output."""
    tool = ROOT / "tmp/dotnet-tools/dotnet-stack"
    if not tool.exists():
        return
    out = Path(env.get("PALMPILOT_OUT", env["PALMPILOT_BUILD_ROOT"])) / "stall-stacks.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        subprocess.run([str(tool), "report", "-p", str(pid)], stdout=f, stderr=subprocess.STDOUT, timeout=120,
                       env=dict(env, DOTNET_ROOT=str(ROOT / "tmp/simantic/dotnet-sdk")))
    print(f"engine stacks saved to {out}", flush=True)


def run_sim(cmd: list[str], env: dict) -> None:
    """run(), but killed when it stalls (under STALL_CPU of a core for STALL_S) or passes MAX_WALL_S."""
    print(f"+ {shlex.join(str(c) for c in cmd)}", flush=True)
    child = subprocess.Popen(cmd, cwd=ROOT, env=env, start_new_session=True)
    start = time.monotonic()
    window = (start, 0.0)
    reason = None
    while child.poll() is None:
        try:
            child.wait(timeout=5)
            break
        except subprocess.TimeoutExpired:
            pass
        now, cpu = time.monotonic(), _cpu_seconds(child.pid)
        if cpu is None:
            continue
        if now - start > MAX_WALL_S:
            reason = f"TIMED OUT after {MAX_WALL_S:.0f} s wall"
        elif now - window[0] >= STALL_S:
            if (cpu - window[1]) / (now - window[0]) < STALL_CPU:
                reason = f"STALLED: under {STALL_CPU:.0%} of a core for {now - window[0]:.0f} s"
                _dump_stacks(child.pid, env)
            window = (now, cpu)
        if reason:
            print(reason, flush=True)
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            sys.exit(reason)
    if child.returncode != 0:
        sys.exit("command failed")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project_name(app: Path) -> str:
    """Read project(<name>) out of the app's CMakeLists.txt."""
    for line in (app / "CMakeLists.txt").read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("project("):
            return stripped[len("project("):].rstrip(")").strip().strip('"')
    sys.exit(f"no project() declaration in {app}/CMakeLists.txt")


def cmd_build(env: dict, app: Path) -> Path:
    out = build_dir(env, app)
    out.mkdir(parents=True, exist_ok=True)
    # idf.py applies sdkconfig.defaults only when generating a fresh sdkconfig,
    # so an edited defaults file is silently ignored and the build keeps the
    # old configuration. Regenerate when the defaults are newer.
    defaults = [app / "sdkconfig.defaults"]
    if app.variant:
        defaults.append(app / f"sdkconfig.{app.variant}")
    generated = out / "sdkconfig"
    if generated.exists() and any(d.exists() and d.stat().st_mtime > generated.stat().st_mtime
                                  for d in defaults):
        print(f"+ sdkconfig defaults changed — regenerating {generated}")
        generated.replace(generated.with_suffix(".superseded"))
    run([f"{env['IDF_PYTHON_ENV_PATH']}/bin/python", f"{env['IDF_PATH']}/tools/idf.py",
         "-C", str(app), "-B", str(out), "-D", f"SDKCONFIG={out}/sdkconfig",
         "-D", "SDKCONFIG_DEFAULTS=" + ";".join(str(d) for d in defaults if d.exists()),
         "-D", "IDF_TARGET=esp32s3", "build"], env)
    return out


def cmd_pack(env: dict, app: Path) -> Path:
    """merge_bin the three images, then wrap with the mask ROM for the simulator."""
    out = build_dir(env, app)
    name = project_name(app)
    app_bin = out / f"{name}.bin"
    if not app_bin.exists():
        sys.exit(f"{app_bin} not found — run `build` first")
    flash, sim_elf = out / "flash.bin", out / "sim.elf"
    run([f"{env['IDF_PYTHON_ENV_PATH']}/bin/python", "-m", "esptool",
         "--chip", "esp32s3", "merge_bin", "-o", str(flash),
         "--flash_mode", "dio", "--flash_size", "4MB", "--flash_freq", "40m",
         BOOTLOADER_OFFSET, str(out / "bootloader/bootloader.bin"),
         PARTITION_OFFSET, str(out / "partition_table/partition-table.bin"),
         APP_OFFSET, str(app_bin)], env)
    run([f"{env['IDF_PYTHON_ENV_PATH']}/bin/python", env["PALMPILOT_IMAGE_PACKER"],
         "--rom", env["PALMPILOT_ROM"], "--flash", str(flash),
         "--out", str(sim_elf)], env)
    print(f"\napp elf  {out / f'{name}.elf'}\n  sha256 {sha256(out / f'{name}.elf')}")
    print(f"sim elf  {sim_elf}\n  sha256 {sha256(sim_elf)}")
    return sim_elf


def fresh_sim_elf(env: dict, app: Path) -> Path:
    """The packed image for `app`, refusing one older than its sources."""
    out = build_dir(env, app)
    sim_elf = out / "sim.elf"
    if not sim_elf.exists():
        sys.exit(f"{sim_elf} not found — run `pack` first")
    # Simulating a stale image silently tests the previous firmware, which is
    # worse than failing: the results look real.
    app_bin = out / f"{project_name(app)}.bin"
    sources = [*app.rglob("*.c"), *app.rglob("*.h"),
               *COMPONENTS.rglob("*.c"), *COMPONENTS.rglob("*.h")]
    newer = [p for p in (app_bin, *sources)
             if p.exists() and p.stat().st_mtime > sim_elf.stat().st_mtime]
    if newer:
        sys.exit(f"{sim_elf} is older than {newer[0]} — run `pack` (or `run`) first")
    return sim_elf


def cmd_sim(env: dict, app: Path, script: str, extra: list[str]) -> None:
    sim_elf = fresh_sim_elf(env, app)
    child = dict(env, PALMPILOT_APP=str(app), PALMPILOT_SIM_ELF=str(sim_elf),
                 PALMPILOT_OUT=str(build_dir(env, app)),
                 PYTHONPATH=str(ROOT / "firmware/tools") + os.pathsep + env.get("PYTHONPATH", ""))
    run_sim([env["PALMPILOT_SIM_PYTHON"], str(Path(script).resolve()), *extra], child)


SYSTEM_APPS = {"LEFT": "hand:left", "RIGHT": "hand:right", "HUB": "hub"}
# --replay: stand-in hands that send the packets a script gives them (apps/replay).
REPLAY_APPS = {"LEFT": "replay:left", "RIGHT": "replay:right", "HUB": "hub"}


def cmd_system(env: dict, script: str, extra: list[str], build: bool, replay: bool) -> None:
    child = dict(env, PALMPILOT_OUT=str(Path(env["PALMPILOT_BUILD_ROOT"]) / "system"),
                 PYTHONPATH=str(ROOT / "firmware/tools") + os.pathsep + env.get("PYTHONPATH", ""))
    for role, name in (REPLAY_APPS if replay else SYSTEM_APPS).items():
        app = resolve_app(name)
        if build:
            cmd_build(env, app)
            cmd_pack(env, app)
        child[f"PALMPILOT_{role}_ELF"] = str(fresh_sim_elf(env, app))
    run_sim([env["PALMPILOT_SIM_PYTHON"], str(Path(script).resolve()), *extra], child)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("build", "pack"):
        sub.add_parser(action).add_argument("app")
    for action in ("sim", "run"):
        node = sub.add_parser(action)
        node.add_argument("app")
        node.add_argument("script")
        node.add_argument("extra", nargs="*")
    node = sub.add_parser("system")
    node.add_argument("script")
    node.add_argument("extra", nargs="*")
    node.add_argument("--no-build", action="store_true")
    node.add_argument("--replay", action="store_true")
    sub.add_parser("env")
    args = parser.parse_args()

    env = load_env()
    if args.action == "env":
        for key in sorted(k for k in env if k.startswith(("IDF_", "SIMANTIC_", "PALMPILOT_"))):
            print(f"{key}={env[key]}")
        return
    if args.action == "system":
        cmd_system(env, args.script, args.extra, build=not args.no_build, replay=args.replay)
        return
    app = resolve_app(args.app)
    if args.action in ("build", "run"):
        cmd_build(env, app)
    if args.action in ("pack", "run"):
        cmd_pack(env, app)
    if args.action in ("sim", "run"):
        cmd_sim(env, app, args.script, args.extra)


if __name__ == "__main__":
    main()
