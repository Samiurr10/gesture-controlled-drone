"""Reusable Simantic harness for PalmPilot ESP32-S3 firmware.

Encodes the workarounds that the September 2026 bench work established, so they
are not re-derived per script (CLAUDE.md section 4):

  * ADC1 conversion is upstream since engine 0.5.14 (PR #168). The stock
    platform wires `CalibrationEfuse`, so raw counts follow the modeled die's
    factory calibration, not the ideal TRM line.
  * `Sim.read_uart` duplicates and interleaves fragments on engine 0.5.7 /
    SDK 0.3.1; not re-examined on 0.5.14. Assertions must use the Renode `CharReceived` event instead.
  * ADC voltage injection is not in the SDK; it goes through Renode interop
    (`IADCExtensions.SetVoltage`).

Run scripts through `palmpilot.py sim`, which sets PALMPILOT_* and PYTHONPATH.

The ADC model is synchronous and noise-free. Raw counts are specific to the
modeled die's eFuse, exactly as they are specific to each physical chip, so
tests assert the calibrated millivolts ESP-IDF derives from them. That validates
the model's calibrated contract only — never silicon accuracy, noise,
conversion latency or the bench board's own eFuse.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Frozen bench pin map — CLAUDE.md section 2. Keys are the finger names used in
# the build guide; ADC1 channel n is GPIO n+1 on this part.
FLEX: dict[str, dict[str, int]] = {
    "thumb":  {"gpio": 1, "channel": 0},
    "index":  {"gpio": 2, "channel": 1},
    "middle": {"gpio": 4, "channel": 3},
    "ring":   {"gpio": 5, "channel": 4},
    "little": {"gpio": 6, "channel": 5},
}
ENABLE_GPIO = 7          # LEFT hand ENABLE / HUB CALIBRATE, active low
# The platform exposes one I2C controller the fixtures attach to. The design
# routes SDA/SCL to GPIO8/9 through the GPIO matrix; the model does not
# simulate that routing, so pin selection is NOT covered by these tests.
I2C_BUS = "i2c0"

# Timer-group interrupt sources on ESP32-S3, counted from
# ETS_TIMER1_INTR_SOURCE = 48 in soc/interrupts.h and anchored against the
# platform's own systimer wiring (TARGET0 = 57).
TIMG_IRQ = {
    "timg0": {0: 50, 1: 52},        # T0 alarm, watchdog
    "timg1": {0: 53, 1: 55},
}
# Candidate upstream wiring: T0/T1/WDT level IRQs as in mcu-lib #222, and the
# MWDT CPU/system reset outputs to RTC_CNTL reset-reason inputs
# (esp32s3 soc/reset_reasons.h: CORE_MWDT0/1 = 7/8, CPU0_MWDT0/1 = 11/17).
S3_TIMG_WIRING = {
    "timg0": ["0 -> intmatrix@50 | intmatrix1@50", "1 -> intmatrix@51 | intmatrix1@51",
              "2 -> intmatrix@52 | intmatrix1@52", "3 -> rtccntl@11", "4 -> rtccntl@7"],
    "timg1": ["0 -> intmatrix@53 | intmatrix1@53", "1 -> intmatrix@54 | intmatrix1@54",
              "2 -> intmatrix@55 | intmatrix1@55", "3 -> rtccntl@17", "4 -> rtccntl@8"],
}
BATTERY_GPIO = 10       # reserved, must stay disconnected
I2C_SDA_GPIO, I2C_SCL_GPIO = 8, 9
LSM6DS3TRC_ADDRESS, LIS3MDL_ADDRESS = 0x6A, 0x1C


# Acceptance band for calibrated ADC1 millivolts against the injected voltage,
# fixed before the 0.5.14 runs. PR #168's calibrated-state model measured a
# worst error of 3 mV over 2480 public-driver checks. Model contract only.
ADC_MV_TOLERANCE = 5


# Model candidates that replace one engine class by name (env.sh sets the paths).
TYPE_SWAPS = [
    ("PALMPILOT_SYSTIMER_OVERLAY", "Miscellaneous.ESP32C3_Systimer", "SystFixed.ESP32C3_Systimer"),
    ("PALMPILOT_BLE_RADIO_OVERLAY", "Wireless.ESP32C3_Radio", "BleFixed.ESP32C3_Radio"),
    ("PALMPILOT_RNG_OVERLAY", "Miscellaneous.ESP32C3_Rng", "RngFixed.ESP32C3_Rng"),
]

_loaded_overlays: set[str] = set()


def load_overlay(path: str, label: str) -> None:
    """Loads a model-candidate assembly into the engine, once per process."""
    if path in _loaded_overlays:
        return
    import clr
    from Antmicro.Renode.Utilities import TypeManager
    clr.AddReference(path)
    if not TypeManager.Instance.ScanFile(path):
        raise RuntimeError(f"{label} overlay type scan failed: {path}")
    _loaded_overlays.add(path)


def build_platform(platform: Path, out: Path, i2c=None, timg=False, hand=None,
                   name="platform.repl", mac=None) -> Path:
    """The platform one PalmPilot machine runs on: the stock S3 platform with
    the model candidates from env.sh and, optionally, I2C fixture scripts.

    `hand` names the hand in a two-hand run. Each fixture script is then copied
    with `HAND = "<hand>"` prepended, so each hand's sensors read their own
    state (fixtures/imu_state.py).

    `mac` sets the factory MAC in eFuse BLOCK1. Every simulated chip otherwise
    reads the same one, and so advertises the same Bluetooth address (base MAC
    + 2); on silicon each chip has its own. A multi-machine BLE run must give
    every machine a distinct value.

    Returns the unmodified platform when nothing had to change.
    """
    platform_text = platform.read_text()
    original_text = platform_text

    mwdt = os.environ.get("PALMPILOT_S3_MWDT_OVERLAY")
    if mwdt and os.environ.get("PALMPILOT_OVERLAYS") != "0":
        # Candidate upstream ESP32S3_Timg with the MWDT modeled
        # (renode-infrastructure #258), loaded under its real type name
        # (absent from engine 0.5.14) for every run, so all tests model the
        # same chip. A platform still declaring the C3 stub is rewired as
        # mcu-lib #222 plus the MWDT reset outputs (mcu-lib #229).
        load_overlay(mwdt, "S3 MWDT")
        lines = []
        for line in platform_text.split("\n"):
            stripped = line.strip()
            peripheral = stripped.split(":", 1)[0] if ":" in stripped else ""
            if peripheral in S3_TIMG_WIRING and "Timers.ESP32C3_Timg" in line:
                lines.append(line.replace("Timers.ESP32C3_Timg", "Timers.ESP32S3_Timg"))
                lines.extend(f"    {wire}" for wire in S3_TIMG_WIRING[peripheral])
            else:
                lines.append(line)
        platform_text = "\n".join(lines)
    elif timg:
        load_overlay(os.environ["PALMPILOT_TIMG_OVERLAY"], "TIMG")
        lines = []
        for line in platform_text.split("\n"):
            stripped = line.strip()
            peripheral = stripped.split(":", 1)[0] if ":" in stripped else ""
            if peripheral in TIMG_IRQ and "Timers.ESP32C3_Timg" in line:
                lines.append(line.replace("Timers.ESP32C3_Timg",
                                          "TimgUnderTest.ESP32C3_Timg"))
                for index, source in sorted(TIMG_IRQ[peripheral].items()):
                    lines.append(f"    {index} -> intmatrix@{source} "
                                 f"| intmatrix1@{source}")
            else:
                lines.append(line)
        platform_text = "\n".join(lines)

    for variable, engine_type, candidate_type in TYPE_SWAPS:
        if os.environ.get(variable):
            load_overlay(os.environ[variable], variable)
            if engine_type not in platform_text:
                raise RuntimeError(f"platform declares no {engine_type}")
            platform_text = platform_text.replace(engine_type, candidate_type)

    if i2c:
        # The fixture scripts import each other (imu_state), so their
        # directory has to be importable from inside the simulator.
        for script in i2c.values():
            directory = str(Path(script).resolve().parent)
            if directory not in sys.path:
                sys.path.insert(0, directory)
        lines = [platform_text.rstrip("\n"), ""]
        for address, script in sorted(i2c.items()):
            script = Path(script).resolve()
            if hand:
                copy = out / "fixtures" / f"{hand}-{script.name}"
                copy.parent.mkdir(parents=True, exist_ok=True)
                copy.write_text(f'HAND = "{hand}"\n' + script.read_text())
                script = copy
            lines.append(f"i2c_dev_{address:02x}: I2C.ScriptedI2cSlave "
                         f"@ {I2C_BUS} {hex(address)}")
            lines.append(f'    file: "{script}"')
        platform_text = "\n".join(lines) + "\n"

    if mac:
        if platform_text.count("efuse: Miscellaneous.ESP32C3_Efuse") != 1:
            raise RuntimeError("platform does not declare exactly one ESP32C3_Efuse")
        platform_text = platform_text.rstrip("\n") + f'\n\nefuse:\n    MacAddress: "{mac}"\n'

    if platform_text == original_text:
        return platform
    out.mkdir(parents=True, exist_ok=True)
    written = out / name
    written.write_text(platform_text)
    return written

class ExternalInputs:
    """What drives a board's pins from outside: flex voltages and buttons.

    Renode resets injected inputs together with the chip, but a real flex
    sensor or button keeps driving its pin through an MCU reset, so every
    input is re-applied after each machine reset.
    """

    def __init__(self, machine):
        from System import Action
        from Antmicro.Renode.Core import IMachine
        from Antmicro.Renode.Peripherals import IPeripheral
        self.machine = machine
        self.voltages: dict[int, int] = {}
        self.levels: dict[int, bool] = {}
        # A software reset (esp_restart, watchdog) resets peripherals one by one
        # and raises only PeripheralReset; a full machine reset raises MachineReset.
        machine.MachineReset += Action[IMachine](lambda _m: self.apply())
        machine.PeripheralReset += Action[IMachine, IPeripheral](lambda _m, _p: self.apply())

    def set_voltage(self, channel: int, microvolts: int) -> None:
        if not 0 <= microvolts <= 0xFFFFFFFF:
            raise ValueError("microvolts must fit unsigned 32-bit")
        self.voltages[channel] = microvolts
        self._voltage(channel, microvolts)

    def set_level(self, pin: int, level: bool) -> None:
        self.levels[pin] = level
        self._gpio().OnGPIO(pin, level)

    def apply(self) -> None:
        for channel, microvolts in self.voltages.items():
            self._voltage(channel, microvolts)
        for pin, level in self.levels.items():
            self._gpio().OnGPIO(pin, level)

    def _gpio(self):
        from Antmicro.Renode.Core import IGPIOReceiver
        return IGPIOReceiver(self.machine["sysbus.gpio"])

    def _voltage(self, channel: int, microvolts: int) -> None:
        from Antmicro.Renode.Peripherals.Sensor import IADCExtensions
        from System import Int32, UInt32
        IADCExtensions.SetVoltage(self.machine["sysbus.sens"], UInt32(microvolts), Int32(channel))


class PalmPilotSim:
    """Context manager wrapping simantic.Sim with the PalmPilot fixtures."""

    def __init__(self, sim_elf=None, out=None, platform=None,
                 uart="uart0", show_logs=False, scenario=None, i2c=None,
                 timg=False):
        # timg=True swaps in the timer-group model under development and wires
        # its IRQ lines, which the stock platform leaves unconnected.
        # PALMPILOT_OVERLAYS=0 drops it so a run exercises the engine's own
        # timer-group model unmodified.
        self.timg = timg and os.environ.get("PALMPILOT_OVERLAYS") != "0"
        # i2c maps a 7-bit address to a ScriptedI2cSlave script, e.g.
        # {0x6A: "firmware/tests/fixtures/lsm6ds3trc.py"}. The scripts run in
        # this interpreter, so a test mutates their shared state directly.
        self.i2c = dict(i2c or {})
        self.sim_elf = Path(sim_elf or os.environ["PALMPILOT_SIM_ELF"])
        self.out = Path(out or os.environ.get("PALMPILOT_OUT", "."))
        self.platform = Path(platform or os.environ["PALMPILOT_PLATFORM"])
        self.uart_name = uart
        self.show_logs, self.scenario = show_logs, scenario
        self.stream = bytearray()
        self.sim = self.machine = None
        self._uart = self._handler = self._event = None

    # -- lifecycle ------------------------------------------------------------
    def __enter__(self) -> "PalmPilotSim":
        os.environ.setdefault("SIMANTIC_TELEMETRY", "0")
        from simantic.engine import load
        load()
        from Antmicro.Renode.Core import EmulationManager
        from System import Action, Byte
        from simantic import Sim

        platform = build_platform(self.platform, self.out, i2c=self.i2c, timg=self.timg)
        self.sim = Sim(repl=platform, elf=self.sim_elf, uart=self.uart_name,
                       show_logs=self.show_logs, scenario=self.scenario).__enter__()
        self.machine = list(EmulationManager.Instance.CurrentEmulation.Machines)[0]
        self.inputs = ExternalInputs(self.machine)

        # Clean capture: the SDK's read_uart duplicates fragments on 0.5.7/0.3.1.
        self._uart = self.machine[f"sysbus.{self.uart_name}"]
        self._handler = Action[Byte](lambda value: self.stream.append(int(value)))
        self._event = self._uart.GetType().GetEvent("CharReceived")
        self._event.AddEventHandler(self._uart, self._handler)
        return self

    def __exit__(self, *exc):
        if self._event is not None:
            self._event.RemoveEventHandler(self._uart, self._handler)
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "uart.txt").write_bytes(bytes(self.stream))
        try:
            (self.out / "logs.json").write_text(
                json.dumps(self.sim.logs(from_start=True)[-500:], indent=2) + "\n")
        except Exception:                       # logs are diagnostics, never fatal
            pass
        return self.sim.__exit__(*exc)

    # -- stimulus -------------------------------------------------------------
    def set_flex_uv(self, finger: str, microvolts: int) -> None:
        """Inject a flex-node voltage through the modeled ADC, not the app."""
        self.set_channel_uv(FLEX[finger]["channel"], microvolts)

    def set_channel_uv(self, channel: int, microvolts: int) -> None:
        self.inputs.set_voltage(channel, microvolts)

    def set_enable(self, pressed: bool) -> None:
        """ENABLE is active low: pressed drives GPIO7 to 0."""
        self.inputs.set_level(ENABLE_GPIO, not pressed)

    # -- execution and observation --------------------------------------------
    def run_for(self, seconds: float) -> float:
        return self.sim.run_for(seconds)

    def send_line(self, text: str) -> None:
        self.sim.send_bytes(text.encode() + b"\n")

    @property
    def text(self) -> str:
        return self.stream.decode("utf-8", errors="replace")

    def records(self, since: int = 0) -> list[dict]:
        """Parse the firmware's newline-delimited JSON diagnostics.

        Only complete lines are parsed. Polling can snapshot the stream while
        the firmware is midway through a printf, and a partial line is not a
        malformed record.
        """
        text = self.stream[since:].decode("utf-8", errors="replace")
        lines = text.split("\n")
        if not text.endswith("\n"):
            lines.pop()                      # trailing fragment, still being written
        return [json.loads(line) for line in lines if line.startswith("{")]

    def wait_for(self, predicate, timeout: float = 3.0, step: float = 0.25,
                 since: int = 0):
        """Advance virtual time until predicate(records) is truthy."""
        elapsed = 0.0
        while elapsed < timeout:
            self.run_for(step)
            elapsed += step
            found = predicate(self.records(since))
            if found:
                return found
        raise AssertionError(
            f"predicate unmet after {timeout}s; tail={self.text[-400:]!r}")

    def wait_for_type(self, kind: str, timeout: float = 3.0, since: int = 0,
                      step: float = 0.25) -> dict:
        return self.wait_for(
            lambda rows: next((r for r in rows if r.get("type") == kind), None),
            timeout=timeout, step=step, since=since)

    def wait_ready(self, timeout: float = 3.0) -> dict:
        return self.wait_for_type("ready", timeout=timeout)

    def save(self, name: str, payload) -> Path:
        self.out.mkdir(parents=True, exist_ok=True)
        path = self.out / name
        path.write_text(json.dumps(payload, indent=2) + "\n")
        return path
