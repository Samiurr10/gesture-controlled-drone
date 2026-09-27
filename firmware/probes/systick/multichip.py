#!/usr/bin/env python3
"""Build the SYSTIMER tick probe for every SYSTIMER-based ESP target and run it
on the stock platform twice: with the engine's own SYSTIMER model and with the
candidate fix (tmp/simantic/upstream-candidates/systimer-work-en).

    python3 firmware/probes/systick/multichip.py [esp32s3 esp32c3 esp32p4]

Stock platforms come from the CLI's cache (~/.sim_cache/<model>.json, fetched by
`sim --mcu <model> --use-cached ...`). Mask ROMs: tmp/simantic/roms (C3/C6, SHA-256
pinned as in the CLI), the S3 ROM from env.sh, P4 extracted from esp-rom-elfs.
Pass, fixed before running: every 1 s window after the first has
ticks == CONFIG_FREERTOS_HZ +/- 1 and vTaskDelay(10 ms) loops == 100 +/- 1.
"""
import json, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "firmware/tools"))
from palmpilot import load_env  # noqa: E402

APP = Path(__file__).resolve().parent
TARGETS = {
    "esp32s3": {"model": "esp32-s3-wroom-1-n8r2", "cls": "ESP32C3_Systimer"},
    "esp32c3": {"model": "esp32-c3", "cls": "ESP32C3_Systimer"},
    # ESP32-C6 is not listed: its platform does not run an ESP-IDF application
    # on engine 0.5.14 (the 2nd-stage bootloader reads the app header as zeros;
    # a RAM-loaded app stops advancing virtual time). ESP32C6_Systimer is still
    # exercised on firmware here through the P4, whose platform uses it.
    "esp32p4": {"model": "esp32-p4", "cls": "ESP32C6_Systimer"},
}
SECONDS = 6
FIXED_DLL = ROOT / "tmp/simantic/upstream-candidates/systimer-work-en/bin/Debug/net10.0/SystFixed.dll"


def run(cmd, env, **kw):
    r = subprocess.run([str(c) for c in cmd], cwd=ROOT, env=env, capture_output=True, text=True, **kw)
    if r.returncode:
        sys.exit(f"failed: {' '.join(map(str, cmd))}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return r


def build(target, env):
    out = Path(env["PALMPILOT_BUILD_ROOT"]) / f"systick-{target}"
    py = f"{env['IDF_PYTHON_ENV_PATH']}/bin/python"
    run([py, f"{env['IDF_PATH']}/tools/idf.py", "-C", APP, "-B", out, "-D", f"SDKCONFIG={out}/sdkconfig",
         "-D", f"IDF_TARGET={target}", "build"], env)
    args = json.loads((out / "flasher_args.json").read_text())
    flash = out / "flash.bin"
    pairs = [x for off, f in sorted(args["flash_files"].items(), key=lambda kv: int(kv[0], 16)) for x in (off, out / f)]
    run([py, "-m", "esptool", "--chip", target, "merge_bin", "-o", flash, "--flash_mode", "dio",
         "--flash_size", "4MB", *pairs], env)
    boot = out / "boot.elf"
    rom_dir = ROOT / "tmp/simantic/roms"
    if target == "esp32s3":
        run([py, env["PALMPILOT_IMAGE_PACKER"], "--rom", env["PALMPILOT_ROM"], "--flash", flash, "--out", boot], env)
    elif target == "esp32p4":
        rom_elf = next(Path(env["IDF_TOOLS_PATH"]).glob("tools/esp-rom-elfs/*/esp32p4_rev0_rom.elf"))
        rom = rom_dir / "esp32p4_rom.bin"
        objcopy = next(Path(env["IDF_TOOLS_PATH"]).glob("tools/riscv32-esp-elf/*/riscv32-esp-elf/bin/riscv32-esp-elf-objcopy"))
        run([objcopy, "-O", "binary", *[f"--only-section={s}" for s in
             (".fixed.text", ".init.text", ".text", ".rodata", ".rodata.interface")], rom_elf, rom], env)
        run([py, ROOT / "tmp/simantic/packers/esp32p4_build_image.py", "--rom", rom, "--rom-elf", rom_elf,
             "--flash", flash, "-o", boot], env)
    else:
        run([py, ROOT / f"tmp/simantic/packers/{target}_build_image.py", "--rom", rom_dir / f"{target}-rom.bin",
             "--flash", flash, "-o", boot], env)
    return out, boot


SIM_SCRIPT = r'''
import json, os, sys
from pathlib import Path
os.environ.setdefault("SIMANTIC_TELEMETRY", "0")
from simantic.engine import load
load()
from simantic import Sim
from Antmicro.Renode.Core import EmulationManager
from System import Action, Byte
repl, elf, fixed, cls, secs, uart = sys.argv[1:7]
text = Path(repl).read_text()
if fixed == "1":
    import clr
    from Antmicro.Renode.Utilities import TypeManager
    dll = os.environ["FIXED_DLL"]
    clr.AddReference(dll); assert TypeManager.Instance.ScanFile(dll)
    assert text.count("Miscellaneous." + cls) == 1
    text = text.replace("Miscellaneous." + cls, "SystFixed." + cls)
plat = Path(elf).with_name(f"platform-{'fixed' if fixed == '1' else 'stock'}.repl")
plat.write_text(text)
stream = bytearray()
with Sim(repl=plat, elf=elf, uart=uart) as sim:
    m = list(EmulationManager.Instance.CurrentEmulation.Machines)[0]
    u = m["sysbus." + uart]
    h = Action[Byte](lambda b: stream.append(int(b)))
    ev = u.GetType().GetEvent("CharReceived"); ev.AddEventHandler(u, h)
    sim.run_for(float(secs))
    ev.RemoveEventHandler(u, h)
rows = []
for line in bytes(stream).decode("utf-8", "replace").splitlines():
    line = line.strip()
    if line.startswith("{"):
        try: rows.append(json.loads(line))
        except ValueError: pass
print("RESULT " + json.dumps(rows))
'''


def simulate(target, out, boot, fixed, env):
    model = TARGETS[target]["model"]
    cache = Path.home() / f".sim_cache/{model}.json"
    replx = json.loads(cache.read_text())
    repl = out / "stock-platform.repl"
    repl.write_text(replx["replx"])
    script = out / "sim_probe.py"
    script.write_text(SIM_SCRIPT)
    uart = "uart0"
    e = dict(env, FIXED_DLL=str(FIXED_DLL))
    r = subprocess.run([env["PALMPILOT_SIM_PYTHON"], script, repl, boot, "1" if fixed else "0",
                        TARGETS[target]["cls"], str(SECONDS), uart], cwd=ROOT, env=e, capture_output=True, text=True)
    m = re.search(r"^RESULT (.*)$", r.stdout, re.M)
    if not m:
        return {"error": (r.stdout + r.stderr)[-1500:]}, replx.get("sim_version")
    return json.loads(m.group(1)), replx.get("sim_version")


def score(rows):
    rates = [r for r in rows if r.get("type") == "rate"][1:]
    if not rates:
        return False, "no rate reports"
    hz = rates[0]["tick_hz"]
    ok = all(abs(r["ticks"] - hz) <= 1 and abs(r["delay_loops"] - 100) <= 1 for r in rates)
    return ok, " ".join(f"{r['ticks']}t/{r['delay_loops']}d" for r in rates)


def main():
    env = load_env()
    targets = sys.argv[1:] or list(TARGETS)
    evidence = {}
    for t in targets:
        out, boot = build(t, env)
        for fixed in (False, True):
            rows, ver = simulate(t, out, boot, fixed, env)
            label = "fixed " if fixed else "stock "
            if isinstance(rows, dict):
                print(f"{t:8} {label} ERROR {rows['error'][-400:]}", flush=True)
                evidence[f"{t}/{label.strip()}"] = rows
                continue
            ok, detail = score(rows)
            boot_ok = any(r.get("type") == "ready" for r in rows)
            print(f"{t:8} {label} engine {ver} booted={boot_ok} {'PASS' if ok else 'FAIL'}  per-second ticks/delay-loops: {detail}", flush=True)
            evidence[f"{t}/{label.strip()}"] = {"engine": ver, "pass": ok, "rows": rows}
    (Path(env["PALMPILOT_BUILD_ROOT"]) / "systick-multichip.json").write_text(json.dumps(evidence, indent=1))


if __name__ == "__main__":
    main()
