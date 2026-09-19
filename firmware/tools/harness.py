"""Reusable Simantic harness for PalmPilot ESP32-S3 firmware.

Encodes the workarounds that the September 2026 bench work established, so they
are not re-derived per script (CLAUDE.md section 4):

  * ADC needs the PR #168 overlay; stock engine 0.5.7 does not convert. The
    overlay is namespace-only, so the .repl's `Miscellaneous.ESP32S3_Sens` has
    to be rewritten to `AdcUnderTest.ESP32S3_Sens`.
  * `Sim.read_uart` duplicates and interleaves fragments on engine 0.5.7 /
    SDK 0.3.1. Assertions must use the Renode `CharReceived` event instead.
  * ADC voltage injection is not in the SDK; it goes through Renode interop
    (`IADCExtensions.SetVoltage`).

Run scripts through `palmpilot.py sim`, which sets PALMPILOT_* and PYTHONPATH.

The ADC model is ideal and synchronous. Values returned here validate the model
contract only — never analog accuracy, noise, conversion latency or factory
calibration.
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
BATTERY_GPIO = 10        # reserved, must stay disconnected
I2C_SDA_GPIO, I2C_SCL_GPIO = 8, 9
LSM6DS3TRC_ADDRESS, LIS3MDL_ADDRESS = 0x6A, 0x1C


def ideal_raw(microvolts: int, attenuation: int) -> int:
    """The ADC model's declared transfer function (PR #168). Not silicon."""
    return min(4095, microvolts * 4095 * (4 - attenuation) // 4400000)


class PalmPilotSim:
    """Context manager wrapping simantic.Sim with the PalmPilot fixtures."""

    def __init__(self, sim_elf=None, out=None, platform=None, adc=True,
                 uart="uart0", show_logs=False, scenario=None, i2c=None,
                 timg=False):
        # timg=True swaps in the timer-group model under development and wires
        # its IRQ lines, which the stock platform leaves unconnected.
        self.timg = timg
        # i2c maps a 7-bit address to a ScriptedI2cSlave script, e.g.
        # {0x6A: "firmware/tests/fixtures/lsm6ds3trc.py"}. The scripts run in
        # this interpreter, so a test mutates their shared state directly.
        self.i2c = dict(i2c or {})
        self.sim_elf = Path(sim_elf or os.environ["PALMPILOT_SIM_ELF"])
        self.out = Path(out or os.environ.get("PALMPILOT_OUT", "."))
        self.platform = Path(platform or os.environ["PALMPILOT_PLATFORM"])
        self.adc, self.uart_name = adc, uart
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

        platform = self.platform
        platform_text = platform.read_text()

        if self.timg:
            import clr
            from Antmicro.Renode.Utilities import TypeManager
            overlay = os.environ["PALMPILOT_TIMG_OVERLAY"]
            clr.AddReference(overlay)
            if not TypeManager.Instance.ScanFile(overlay):
                raise RuntimeError(f"TIMG overlay type scan failed: {overlay}")
            lines = []
            for line in platform_text.split("\n"):
                stripped = line.strip()
                name = stripped.split(":", 1)[0] if ":" in stripped else ""
                if name in TIMG_IRQ and "Timers.ESP32C3_Timg" in line:
                    lines.append(line.replace("Timers.ESP32C3_Timg",
                                              "TimgUnderTest.ESP32C3_Timg"))
                    for index, source in sorted(TIMG_IRQ[name].items()):
                        lines.append(f"    {index} -> intmatrix@{source} "
                                     f"| intmatrix1@{source}")
                else:
                    lines.append(line)
            platform_text = "\n".join(lines)

        if self.i2c:
            # The fixture scripts import each other (imu_state), so their
            # directory has to be importable from inside the simulator.
            for script in self.i2c.values():
                directory = str(Path(script).resolve().parent)
                if directory not in sys.path:
                    sys.path.insert(0, directory)
            lines = [platform_text.rstrip("\n"), ""]
            for address, script in sorted(self.i2c.items()):
                lines.append(f"i2c_dev_{address:02x}: I2C.ScriptedI2cSlave "
                             f"@ {I2C_BUS} {hex(address)}")
                lines.append(f'    file: "{Path(script).resolve()}"')
            platform_text = "\n".join(lines) + "\n"

        if self.adc:
            import clr
            from Antmicro.Renode.Utilities import TypeManager
            overlay = os.environ["PALMPILOT_ADC_OVERLAY"]
            clr.AddReference(overlay)
            if not TypeManager.Instance.ScanFile(overlay):
                raise RuntimeError(f"overlay type scan failed: {overlay}")
            if platform_text.count("Miscellaneous.ESP32S3_Sens") != 1:
                raise RuntimeError("platform does not declare exactly one ESP32S3_Sens")
            platform_text = platform_text.replace(
                "Miscellaneous.ESP32S3_Sens", "AdcUnderTest.ESP32S3_Sens")

        if self.adc or self.i2c or self.timg:
            self.out.mkdir(parents=True, exist_ok=True)
            platform = self.out / "platform.repl"
            platform.write_text(platform_text)

        self.sim = Sim(repl=platform, elf=self.sim_elf, uart=self.uart_name,
                       show_logs=self.show_logs, scenario=self.scenario).__enter__()
        self.machine = list(EmulationManager.Instance.CurrentEmulation.Machines)[0]

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
        from Antmicro.Renode.Peripherals.Sensor import IADCExtensions
        from System import Int32, UInt32
        if not 0 <= microvolts <= 0xFFFFFFFF:
            raise ValueError("microvolts must fit unsigned 32-bit")
        IADCExtensions.SetVoltage(self.machine["sysbus.sens"],
                                  UInt32(microvolts), Int32(channel))

    def set_enable(self, pressed: bool) -> None:
        """ENABLE is active low: pressed drives GPIO7 to 0."""
        self.sim.inject_gpio("gpio", ENABLE_GPIO, not pressed)

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
