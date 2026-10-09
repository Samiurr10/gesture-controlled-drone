#!/usr/bin/env python3
"""Write the controller wiring files (pinplanner JSON) from the frozen pin map.

Each hand's circuits sit on its own full (830-hole) breadboard, the hub's on a half one. The
board's 3V3 and GND go to the bottom rails, next to the DevKit, and two jumpers at the right
end carry them to the top rails. One column strip per circuit node (rows a-e); the parts go
from the node strip to a top rail, and one jumper takes the node (row e) to the GPIO. Strips
fed from the DevKit's J1 header sit left of those fed from J3, so the jumpers don't cross.
Run from this folder:

    python3 gen_wiring.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# frozen pin map: CLAUDE.md section 2, docs/wiring/README.md
# (finger, GPIO, ADC channel, jumper colour, node column)
FLEX = [("middle", "GPIO4", "ADC1_CH3", "purple", 5), ("ring", "GPIO5", "ADC1_CH4", "teal", 14),
        ("little", "GPIO6", "ADC1_CH5", "pink", 23), ("thumb", "GPIO1", "ADC1_CH0", "orange", 45),
        ("index", "GPIO2", "ADC1_CH1", "green", 54)]
BUTTON_COL = 33                     # GPIO7 node; its 1k goes to the switch strip at BUTTON_COL + 5


# breadboard id -> (columns, holes per rail)
BOARDS = {"breadboard-full": (63, 50), "breadboard-half": (30, 25)}


class Rails:
    """Hands out rail holes nearest a column, one lead per hole."""
    def __init__(self, board="breadboard-full"):
        self.used = set()
        self.cols, self.holes = BOARDS[board]

    def col(self, k):
        """Column position of rail hole k: groups of five with a one-pitch gap, centred on the columns."""
        last = self.holes - 1 + (self.holes - 1) // 5
        return 1 + ((self.cols - 1) - last) / 2 + (k - 1) + (k - 1) // 5

    def near(self, rail, col):
        k = min((k for k in range(1, self.holes + 1) if (rail, k) not in self.used), key=lambda k: (abs(self.col(k) - col), k))
        self.used.add((rail, k))
        return f"bb:{rail}{k}"


def part(frm, to, kind, value=None, label=None):
    c = {"from": frm, "to": to, "component": kind}
    if value: c["value"] = value
    if label: c["label"] = label
    return c


def wire(frm, to, color, label):
    return {"from": frm, "to": to, "color": color, "label": label}


def power(rails, side, far=62):
    return [wire("esp:J1-1", rails.near("BP", 3), "red", f"{side} 3V3 -> bottom + rail"),
            wire("esp:J3-1", rails.near("BN", 12), "black", f"{side} GND -> bottom - rail"),
            wire(rails.near("BP", far), rails.near("TP", far), "red", "bottom + rail -> top + rail"),
            wire(rails.near("BN", far), rails.near("TN", far), "black", "bottom - rail -> top - rail")]


def flex_channel(rails, side, name, gpio, adc, color, c):
    # flex leans left, 47k and 100nF fan out to the right so their values stay readable
    return [part(rails.near("TP", c - 2), f"bb:{c}a", "flex", name, f"{side} 3V3 -> {name} flex -> node"),
            part(f"bb:{c}b", rails.near("TN", c + 2), "resistor", "47k", f"{name} node -> 47k -> GND"),
            part(f"bb:{c}d", rails.near("TN", c + 6), "capacitor", "100nF", f"{name} node -> 100nF -> GND"),
            wire(f"bb:{c}e", f"esp:{gpio}", color, f"{name} node -> {gpio} ({adc})")]


def button(rails, side, name, c=BUTTON_COL):
    sw = c + 5
    return [part(rails.near("TP", c - 2), f"bb:{c}a", "resistor", "10k", f"{side} 3V3 -> 10k -> {name} node (pull-up)"),
            part(f"bb:{c}b", rails.near("TN", c + 2.5), "capacitor", "100nF", f"{name} node -> 100nF -> GND (debounce)"),
            part(f"bb:{c}d", f"bb:{sw}d", "resistor", "1k", f"{name} node -> 1k -> switch"),
            part(f"bb:{sw}a", rails.near("TN", sw + 1), "button", name, f"normally-open {name} switch -> GND"),
            wire(f"bb:{c}e", "esp:GPIO7", "lime", f"{name} node -> GPIO7, active low")]


def imu(rails, side):
    return [wire(rails.near("BP", 34), "imu:VIN", "red", f"{side} 3V3 -> IMU VIN"),
            wire(rails.near("BN", 36), "imu:GND", "black", f"{side} GND -> IMU GND"),
            wire("esp:GPIO8", "imu:SDA", "blue", "I2C SDA <-> GPIO8 (breakout pull-ups)"),
            wire("esp:GPIO9", "imu:SCL", "yellow", "I2C SCL GPIO9 -> IMU (100 kHz)")]


DONT = ("Do not use GPIO0/3/45/46 (strapping), GPIO19/20 (native USB), GPIO43/44 (UART0 bridge). "
        "GPIO10 is reserved for battery sense: leave it disconnected.")


FINGERS = [f[0] for f in FLEX]


def hand(side, title, enable, fingers=FINGERS, with_imu=True):
    """One hand. A bench stage leaves parts out, but every part keeps the holes it has
    on the finished hand, so going to the next stage only ever adds parts."""
    r = Rails()
    groups = [("power", power(r, side)), ("imu", imu(r, side))]
    for name, gpio, adc, color, c in FLEX:
        groups.append((name, flex_channel(r, side, name, gpio, adc, color, c)))
    if enable:
        groups.append(("enable", button(r, side, "ENABLE")))
    keep = {"power", "enable", *fingers} | ({"imu"} if with_imu else set())
    conns = [c for group, cs in groups if group in keep for c in cs]
    parts = [{"id": "bb", "board": "breadboard-full", "x": 0, "y": 0},
             {"id": "esp", "board": "esp32-s3-devkitc-1", "x": 4, "y": 62, "label": f"{side} hand ESP32-S3-DevKitC-1"}]
    if with_imu:
        parts.append({"id": "imu", "board": "adafruit-5543", "x": 82, "y": 68, "label": f"{side} Adafruit #5543 (0x6A / 0x1C)"})
    return {"version": 1, "title": title,
            "notes": f"PalmPilot {side} hand, bench plan on a full breadboard. Pins match PalmPilot CLAUDE.md section 2 and "
                     "docs/wiring/README.md; not checked on hardware. + rails = this board's 3V3, - rails = its GND; "
                     "the right-end jumpers join the bottom rails to the top ones. Never join supplies across boards. The flex sensors sit on the glove: their two leads come to the rail hole and "
                     "the node hole shown. IMU: leave 3Vo, INT1/INT2/INTM/DRDY and the address pads unconnected. " + DONT
                     + (" ENABLE on GPIO7 is LEFT only." if enable
                        else " RIGHT has no ENABLE button: GPIO7 stays unconnected." if side == "RIGHT"
                        else " The ENABLE button is added at bench 05; GPIO7 stays unconnected until then."),
            "parts": parts, "connections": conns}


def hub(title="PalmPilot HUB: CALIBRATE button, USB-UART to laptop"):
    r = Rails("breadboard-half")
    conns = power(r, "HUB", far=29) + button(r, "HUB", "CALIBRATE", c=14)
    return {"version": 1, "title": title,
            "notes": "PalmPilot HUB, bench plan on a half breadboard. Pins match PalmPilot CLAUDE.md section 2; not checked on hardware. "
                     "Laptop link: USB data cable from the DevKit port labelled UART (on-board USB-to-UART bridge on UART0, 115200 baud) "
                     "to the laptop; it also powers the hub. GPIO43 (U0TXD) and GPIO44 (U0RXD) are highlighted because the bridge uses "
                     "them: do not wire them. No flex sensors and no motion sensor on the hub. Hands reach the hub over BLE only. " + DONT,
            "parts": [{"id": "bb", "board": "breadboard-half", "x": 0, "y": 0},
                      {"id": "esp", "board": "esp32-s3-devkitc-1", "x": 4, "y": 62, "label": "HUB ESP32-S3-DevKitC-1 (USB-UART port -> laptop, 115200)"}],
            "connections": conns, "highlight": ["esp:GPIO43", "esp:GPIO44"]}


FILES = {
    "left-hand": hand("LEFT", "PalmPilot LEFT hand: 5 flex + LSM6DS3TR-C/LIS3MDL + ENABLE", True),
    "right-hand": hand("RIGHT", "PalmPilot RIGHT hand: 5 flex + LSM6DS3TR-C/LIS3MDL", False),
    "hub": hub(),
}

# One wiring per bench stage (docs/bench/<stage>/), in build order.
FULL_LEFT = dict(enable=True)   # stages 05-09 share the finished LEFT wiring
BOARD_CHECK = {
    "version": 1, "title": "Bench 00 / board check: bare DevKit, GPIO1 to GND for the ADC ground check",
    "notes": "One DevKit, nothing else connected. The single jumper is only for the ADC reference app's ground check "
             "(simulation/simantic/hardware-validation/esp32s3-adc); remove it before bench 01. GPIO1 is an ADC input "
             "there and is never driven, so tying it to GND is safe.",
    "parts": [{"id": "esp", "board": "esp32-s3-devkitc-1", "x": 0, "y": 0, "label": "ESP32-S3-DevKitC-1 (record its markings)"}],
    "connections": [{"from": "esp:GPIO1", "to": "esp:J3-1", "color": "black", "label": "GPIO1 -> GND, ADC ground check only"}],
}

BENCH = {
    "00-board-check": BOARD_CHECK,
    "01-s1a-one-flex": hand("LEFT", "Bench 01 / S1-A: one flex channel (LEFT thumb, GPIO1)", False,
                            fingers=["thumb"], with_imu=False),
    "02-s1a-five-flex": hand("LEFT", "Bench 02 / S1-A: five flex channels (LEFT)", False, with_imu=False),
    "03-s1d-motion": hand("LEFT", "Bench 03 / S1-D: five flex + Adafruit #5543 motion (LEFT)", False),
    "04-s1b-calibration": hand("LEFT", "Bench 04 / S1-B: calibration (LEFT, five flex + motion)", False),
    "05-s1c-enable-control": hand("LEFT", "Bench 05 / S1-A + S1-C: ENABLE and control (full LEFT hand)", **FULL_LEFT),
    "06-s1e-attitude": hand("LEFT", "Bench 06 / S1-E: tilt and gestures (full LEFT hand)", **FULL_LEFT),
    "07-s1f-persistence": hand("LEFT", "Bench 07 / S1-F: calibration persistence (full LEFT hand)", **FULL_LEFT),
    "08-s1g-packet": hand("LEFT", "Bench 08 / S1-G: hand packet (full LEFT hand)", **FULL_LEFT),
    "09-s1h-watchdog": hand("LEFT", "Bench 09 / S1-H: watchdog (full LEFT hand)", **FULL_LEFT),
    "10-right-hand": hand("RIGHT", "Bench 10 / S1 on RIGHT: five flex + motion, no ENABLE", False),
    "11-s2a-link": hub("Bench 11 / S2-A: HUB for the two-hand BLE link"),
    "12-s2b-controller": hub("Bench 12 / S2-B: HUB with CALIBRATE, whole controller"),
    "13-s3-host": hub("Bench 13 / S3: HUB to the laptop over the UART USB port"),
}

if __name__ == "__main__":
    for name, doc in FILES.items():
        (HERE / f"{name}.wiring.json").write_text(json.dumps(doc, indent=2) + "\n")
        print(name, len(doc["connections"]), "connections")
    bench = HERE.parent / "bench"
    for stage, doc in BENCH.items():
        (bench / stage).mkdir(parents=True, exist_ok=True)
        (bench / stage / "wiring.json").write_text(json.dumps(doc, indent=2) + "\n")
        print(stage, len(doc["connections"]), "connections")
