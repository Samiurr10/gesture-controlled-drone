#!/usr/bin/env python3
"""PalmPilot ESP32-S3 firmware driver: build -> pack -> simulate.

Replaces the ad-hoc shell scripts under tmp/simantic/. All pinned paths come
from firmware/tools/env.sh (CLAUDE.md section 3).

  palmpilot.py build <app>          idf.py build
  palmpilot.py pack  <app>          merge_bin + ROM wrapper -> sim.elf
  palmpilot.py sim   <app> <script> run a harness script against sim.elf
  palmpilot.py run   <app> <script> build + pack + sim
  palmpilot.py env                  print the resolved environment

<app> is a directory containing an ESP-IDF project (CMakeLists.txt), either an
absolute path or one relative to firmware/apps/.

Build artifacts land in tmp/palmpilot/<app-name>/ and are gitignored. The
physical board and the simulator are flashed from the SAME bootloader/partition/
app binaries; only the ROM wrapper differs. Keep it that way.
"""
import argparse
import hashlib
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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


def resolve_app(name: str) -> Path:
    app = Path(name)
    if not app.is_absolute():
        app = (APPS / name) if (APPS / name).exists() else Path.cwd() / name
    app = app.resolve()
    if not (app / "CMakeLists.txt").exists():
        sys.exit(f"{app} is not an ESP-IDF project (no CMakeLists.txt)")
    return app


def build_dir(env: dict, app: Path) -> Path:
    return Path(env["PALMPILOT_BUILD_ROOT"]) / app.name


def run(cmd: list[str], env: dict) -> None:
    print(f"+ {shlex.join(str(c) for c in cmd)}", flush=True)
    if subprocess.run(cmd, cwd=ROOT, env=env).returncode != 0:
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
    run([f"{env['IDF_PYTHON_ENV_PATH']}/bin/python", f"{env['IDF_PATH']}/tools/idf.py",
         "-C", str(app), "-B", str(out), "-D", f"SDKCONFIG={out}/sdkconfig",
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


def cmd_sim(env: dict, app: Path, script: str, extra: list[str]) -> None:
    sim_elf = build_dir(env, app) / "sim.elf"
    if not sim_elf.exists():
        sys.exit(f"{sim_elf} not found — run `pack` first")
    child = dict(env, PALMPILOT_APP=str(app), PALMPILOT_SIM_ELF=str(sim_elf),
                 PALMPILOT_OUT=str(build_dir(env, app)),
                 PYTHONPATH=str(ROOT / "firmware/tools") + os.pathsep + env.get("PYTHONPATH", ""))
    run([env["PALMPILOT_SIM_PYTHON"], str(Path(script).resolve()), *extra], child)


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
    sub.add_parser("env")
    args = parser.parse_args()

    env = load_env()
    if args.action == "env":
        for key in sorted(k for k in env if k.startswith(("IDF_", "SIMANTIC_", "PALMPILOT_"))):
            print(f"{key}={env[key]}")
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
