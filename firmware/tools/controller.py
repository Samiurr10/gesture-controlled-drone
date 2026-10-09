"""The whole controller in one simulation: LEFT hand, RIGHT hand and HUB, three
ESP32-S3 machines on one BLE medium.

Each machine runs its real firmware image on the same platform the single-hand
tests use (harness.build_platform, with the env.sh model candidates). Stimulus
goes through the modeled drivers only: flex voltages through the ADC model,
ENABLE and CALIBRATE through GPIO, motion through each hand's own I2C fixtures.
The hands reach the hub only over the simulated radio.

With `drone=True` a fourth machine runs stock ArduCopter on an STM32F405
(Matek F405-Wing board model). The computer bridge between them lives in the
simulation: each hub command line becomes RC channels (simulation/drone/
rc_link.py), sent to ArduCopter's telemetry port as MAVLink by gcs_peer.py.

Run scripts through `palmpilot.py system <script>`, which builds all three
images and sets PALMPILOT_{LEFT,RIGHT,HUB}_ELF.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sys
from pathlib import Path

from harness import ENABLE_GPIO, FLEX, ExternalInputs, build_platform, load_overlay

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
MOTION_FIXTURES = {
    0x6A: FIXTURES_DIR / "lsm6ds3trc.py",
    0x1C: FIXTURES_DIR / "lis3mdl.py",
}
if str(FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(FIXTURES_DIR))
import imu_state                                             # noqa: E402

DRONE_DIR = Path(__file__).resolve().parents[2] / "simulation" / "drone"
if str(DRONE_DIR) not in sys.path:
    sys.path.insert(0, str(DRONE_DIR))
import quad_plant                                           # noqa: E402
import rc_link                                               # noqa: E402

MACHINES = ("left", "right", "hub")
# Distinct factory MACs, one per board, as three physical chips would have.
# Locally administered (bit 1 of the first byte), so never a real vendor's.
FACTORY_MAC = {
    "left": "02:50:50:00:00:10",
    "right": "02:50:50:00:00:20",
    "hub": "02:50:50:00:00:30",
}


class Console:
    """One machine's UART0, captured byte-exact from the model's CharReceived
    event (the SDK's read_uart is not used for assertions, see harness.py)."""

    def __init__(self, name: str, on_line=None):
        self.name = name
        self.stream = bytearray()
        self.on_line = on_line
        self._line_start = 0

    def feed(self, value: int) -> None:
        self.stream.append(value)
        if value == 0x0A and self.on_line:
            line = self.stream[self._line_start:].decode("utf-8", errors="replace").strip()
            self._line_start = len(self.stream)
            self.on_line(line)

    @property
    def text(self) -> str:
        return self.stream.decode("utf-8", errors="replace")

    def records(self, since: int = 0) -> list[dict]:
        """Complete JSON lines only; a line still being written is skipped."""
        text = self.stream[since:].decode("utf-8", errors="replace")
        lines = text.split("\n")
        if not text.endswith("\n"):
            lines.pop()
        out = []
        for line in lines:
            if line.startswith("{"):
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    out.append({"type": "malformed", "line": line})
        return out


def build_drone_platform(out: Path, plant: bool = False) -> Path:
    """STM32F405RG + the Matek F405-Wing board, with the S.Bus receiver replaced by
    the computer's MAVLink link (gcs_peer) and the STM32 UART candidate if set.
    With `plant`, the IMU and barometer report quad_plant's motion."""
    text = Path(os.environ["PALMPILOT_DRONE_PLATFORM"]).read_text()
    overlay = os.environ.get("PALMPILOT_STM32_UART_OVERLAY")
    if overlay:
        load_overlay(overlay, "STM32 UART")
        text = text.replace("UART.STM32_UART", "UartFixed.STM32_UART")
    board_dir = Path(os.environ["PALMPILOT_DRONE_BOARD"])
    board = (board_dir / "f405-wing-v2.board").read_text().replace("{TEST_DIR}", str(board_dir))
    board = re.sub(r"rx: UART\.ScriptedUartPeer[^\n]*\n[^\n]*\n", "", board)
    if plant:
        board = board.replace(f"{board_dir}/peers/icm42688.py", str(DRONE_DIR / "imu_plant.py"))
        board = board.replace(f"{board_dir}/peers/dps310.py", str(DRONE_DIR / "baro_plant.py"))
        board = board.replace(f"{board_dir}/peers/sd_spi.py", str(DRONE_DIR / "sd_card.py"))
    board += f'\ngcs: UART.ScriptedUartPeer @ sysbus 0x60200000\n    file: "{DRONE_DIR / "gcs_peer.py"}"\n'
    out.mkdir(parents=True, exist_ok=True)
    path = out / "platform-drone.repl"
    path.write_text(text + "\n" + board)
    return path


@contextlib.contextmanager
def _serial_execution(enabled: bool):
    """Sets SessionSpec.SerialExecution for the session started inside, which the SDK
    (0.3.1) does not pass on from a scenario's `serialExecution`."""
    if not enabled:
        yield
        return
    import simantic.session as session
    load = session.load

    class Serial:
        def __init__(self, ns):
            self._ns = ns

        def __getattr__(self, name):
            return getattr(self._ns, name)

        def SessionSpec(self):
            spec = self._ns.SessionSpec()
            spec.SerialExecution = True
            return spec

    session.load = lambda *args, **kwargs: Serial(load(*args, **kwargs))
    try:
        yield
    finally:
        session.load = load


def bridge_hub_line(line: str) -> None:
    """The computer bridge: every hub command line updates the drone's RC channels."""
    if line.startswith('{"type":"command"'):
        try:
            rc_link.apply_command(json.loads(line))
        except json.JSONDecodeError:
            rc_link.apply_command(None)


class ControllerSim:
    def __init__(self, out=None, show_logs=False, quantum=None, drone=False, plant=False, serial=None):
        self.elf = {
            "left": Path(os.environ["PALMPILOT_LEFT_ELF"]),
            "right": Path(os.environ["PALMPILOT_RIGHT_ELF"]),
            "hub": Path(os.environ["PALMPILOT_HUB_ELF"]),
        }
        self.out = Path(out or os.environ.get("PALMPILOT_OUT", "."))
        self.platform = Path(os.environ["PALMPILOT_PLATFORM"])
        self.show_logs, self.quantum, self.drone, self.plant = show_logs, quantum, drone, plant
        # Every core of every machine on one host thread, in turn: no cross-thread
        # races or lock-order deadlocks between cores, at the cost of speed.
        self.serial = os.environ.get("PALMPILOT_SERIAL") == "1" if serial is None else serial
        self.console = {name: Console(name, bridge_hub_line if drone and name == "hub" else None)
                        for name in MACHINES}
        self.sim = None
        self._hooks = []

    # -- lifecycle ------------------------------------------------------------
    def __enter__(self) -> "ControllerSim":
        os.environ.setdefault("SIMANTIC_TELEMETRY", "0")
        from simantic.engine import load
        load()
        from Antmicro.Renode.Core import EmulationManager
        from System import Action, Byte
        from simantic import Sim

        for hand in ("left", "right"):
            imu_state.for_hand(hand).reset()
        rc_link.reset()
        machines = {}
        # Per process: simulations run side by side must not read each other's half-written files.
        platforms = self.out / "platforms" / str(os.getpid())
        for name in MACHINES:
            i2c = MOTION_FIXTURES if name != "hub" else None
            platform = build_platform(self.platform, platforms, i2c=i2c,
                                      hand=name if i2c else None,
                                      name=f"platform-{name}.repl",
                                      mac=FACTORY_MAC[name])
            machines[name] = {"repl": str(platform), "elf": str(self.elf[name])}
        scenario = {
            "machines": machines,
            "media": [{"type": "ble", "connect": [f"{n}.radio" for n in MACHINES]}],
        }
        if self.drone:
            quad_plant.PLANT.reset()
            machines["drone"] = {"repl": str(build_drone_platform(platforms, self.plant)),
                                 "elf": os.environ["PALMPILOT_DRONE_ELF"]}
            scenario["media"].append({"type": "uart", "connect": ["drone.usart1", "drone.gcs"]})
        if self.quantum is not None:
            scenario["quantum"] = self.quantum
        with _serial_execution(self.serial):
            self.sim = Sim(scenario=scenario, machine="hub", uart="uart0",
                           show_logs=self.show_logs).__enter__()

        emulation = EmulationManager.Instance.CurrentEmulation
        self.machine = {}
        for machine in emulation.Machines:
            found, name = emulation.TryGetMachineName(machine, None)
            if found and name in self.console:
                self.machine[name] = machine
            elif found and name == "drone":
                self.drone_machine = machine
                quad_plant.BUS_READ = lambda address, _size, bus=machine.SystemBus: int(bus.ReadDoubleWord(address))
        self.inputs = {name: ExternalInputs(m) for name, m in self.machine.items()}
        missing = set(MACHINES) - set(self.machine)
        if missing:
            raise RuntimeError(f"scenario machines not found: {sorted(missing)}")
        for name, machine in self.machine.items():
            uart = machine["sysbus.uart0"]
            handler = Action[Byte](lambda value, c=self.console[name]: c.feed(int(value)))
            event = uart.GetType().GetEvent("CharReceived")
            event.AddEventHandler(uart, handler)
            self._hooks.append((event, uart, handler))
        return self

    def __exit__(self, *exc):
        for event, uart, handler in self._hooks:
            event.RemoveEventHandler(uart, handler)
        self.out.mkdir(parents=True, exist_ok=True)
        for name, console in self.console.items():
            (self.out / f"uart-{name}.txt").write_bytes(bytes(console.stream))
        return self.sim.__exit__(*exc)

    # -- stimulus -------------------------------------------------------------
    def set_flex_uv(self, hand: str, finger: str, microvolts: int) -> None:
        self.inputs[hand].set_voltage(FLEX[finger]["channel"], microvolts)

    def set_hand_uv(self, hand: str, microvolts: int, fingers=None) -> None:
        for finger in fingers or FLEX:
            self.set_flex_uv(hand, finger, microvolts)

    def motion(self, hand: str):
        """The hand's motion state; mutate it and the next I2C read sees it."""
        return imu_state.for_hand(hand)

    def set_enable(self, pressed: bool) -> None:
        """LEFT hand ENABLE, active low."""
        self.inputs["left"].set_level(ENABLE_GPIO, not pressed)

    def set_calibrate(self, pressed: bool) -> None:
        """HUB CALIBRATE, active low, same GPIO7 as the left ENABLE."""
        self.inputs["hub"].set_level(ENABLE_GPIO, not pressed)

    def send_line(self, machine: str, text: str) -> None:
        self.sim.send_bytes(text.encode() + b"\n", machine=machine)

    # -- execution and observation --------------------------------------------
    def run_for(self, seconds: float) -> float:
        return self.sim.run_for(seconds)

    def time(self) -> float:
        return self.sim.time

    def mark(self, machine: str) -> int:
        return len(self.console[machine].stream)

    def wait_for(self, machine: str, predicate, timeout: float = 3.0,
                 step: float = 0.1, since: int = 0):
        """Advance virtual time until predicate(records of `machine`) is truthy."""
        elapsed = 0.0
        while elapsed < timeout:
            self.run_for(step)
            elapsed += step
            found = predicate(self.console[machine].records(since))
            if found:
                return found
        tail = self.console[machine].text[-600:]
        raise AssertionError(f"{machine}: predicate unmet after {timeout}s; tail={tail!r}")

    def wait_for_type(self, machine: str, kind: str, timeout: float = 3.0,
                      since: int = 0, step: float = 0.1) -> dict:
        return self.wait_for(
            machine, lambda rows: next((r for r in rows if r.get("type") == kind), None),
            timeout=timeout, step=step, since=since)

    def query(self, machine: str, line: str, kind: str, timeout: float = 3.0) -> dict:
        mark = self.mark(machine)
        self.send_line(machine, line)
        return self.wait_for_type(machine, kind, timeout=timeout, since=mark, step=0.05)

    # -- procedures ----------------------------------------------------------
    def calibrate(self, hand: str, extended_uv: int, curled_uv: int) -> dict:
        """The bench calibration procedure, over the hand's own UART: capture
        both flex ends and the resting orientation, then validate. Returns the
        hand's `calibration` record."""
        self.set_hand_uv(hand, extended_uv)
        self.run_for(0.1)
        self.query(hand, "cal extended", "capture", timeout=3.0)
        self.set_hand_uv(hand, curled_uv)
        self.run_for(0.1)
        self.query(hand, "cal curled", "capture", timeout=3.0)
        self.set_hand_uv(hand, extended_uv)
        self.run_for(0.1)
        self.query(hand, "cal neutral", "neutral")
        return self.query(hand, "cal finish", "calibration")

    def wait_linked(self, timeout: float = 5.0) -> dict:
        """Until the hub reports both hands linked and delivering packets.
        Returns the hub's status record."""
        start = self.time()
        # Bytes sent before the hub's UART driver is installed are lost, so do
        # not ask before it has said it is ready.
        self.wait_for_type("hub", "ready", timeout=timeout)
        while True:
            status = self.query("hub", "status", "status")
            if all(h["ready"] and h["accepted"] for h in status["hands"]):
                return status
            if self.time() - start > timeout:
                raise AssertionError(f"hands not linked after {timeout}s: {status}")
            self.run_for(0.25)

    def wait_command(self, predicate, timeout: float = 2.0, since: int | None = None) -> dict:
        """Until the newest hub command satisfies predicate(command)."""
        mark = self.mark("hub") if since is None else since

        def found(_rows):
            command = self.latest_command(mark)
            return command if command and predicate(command) else None
        return self.wait_for("hub", found, timeout=timeout, step=0.04)

    def commands(self, since: int = 0) -> list[dict]:
        return [r for r in self.console["hub"].records(since) if r.get("type") == "command"]

    def latest_command(self, since: int = 0) -> dict | None:
        rows = self.commands(since)
        return rows[-1] if rows else None

    def save(self, name: str, payload) -> Path:
        self.out.mkdir(parents=True, exist_ok=True)
        path = self.out / name
        path.write_text(json.dumps(payload, indent=2) + "\n")
        return path
