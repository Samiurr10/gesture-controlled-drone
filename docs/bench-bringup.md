# Physical bring-up: from simulation to boards

This is the record of moving PalmPilot from Simantic onto real boards: what was
simulated first, what carried over to hardware unchanged, and what the bench
found that simulation could not. It covers 2026-11-11 to 2026-11-17. It is a log
of observations, not a qualification: none of the physical test-plan steps (B0–B7,
C1–C4 in [test-plan.md](test-plan.md)) is claimed passed.

## The approach: simulate first, then wire

Every firmware feature was written and tested in Simantic before a sensor was
connected ([simantic.md](simantic.md)). The simulator ran the exact bootloader,
partition table and application images that were later flashed, so the first
physical flash was not a port: the same `hand:left`, `hand:right` and `hub` builds
went onto three ESP32-S3 DevKits, and the bench work was wiring sensors to them
and reading what the firmware reported.

By the time the boards were wired, simulation had already exercised the ADC
driver, calibration, persistence, the IMU driver, the control state machine, the
BLE link between three chips, the hub's mixing and interlocks, and the hub driving
ArduCopter ([simulation.md](simulation.md), `firmware/tests/`).

## What carried over unchanged

These worked on hardware the first time, with the firmware as it ran in
simulation (no code change for that behaviour):

| Area | Simulation | Physical bench (observed) |
|---|---|---|
| Flash and boot | images booted through the real mask ROM | the same images flashed with esptool and booted on all three boards |
| Flex acquisition | calibrated mV from the `esp_adc` driver, open/short classification | straight fingers read about 2.0–2.1 V, as the 47 kΩ divider predicts; bending lowered it; a missing ground rail showed as SHORT and a missing 3.3 V as OPEN, as designed |
| Calibration and persistence | capture, finish, NVS save, restore after reboot | LEFT captured with 585–709 counts of travel (limit 200); saved, and restored after a reset |
| BLE link | three chips on one medium, 50 Hz, no rejected packets | both hands connected to the hub about 1.3 s after boot; 50 packets/s each; 0 rejected and 0 drops over 20 s (2026-11-11) |
| Packet format | 59-byte packet with CRC, decoded independently | the hub accepted every packet from both hands (0 format, side or replay rejections) |
| Hub interlocks | invalid command on any unready, stale or missing hand | the hub reported `left_not_ready`, `right_stale`, `not_enabled` and so on exactly when those conditions held |
| Hub → drone | hub lines through `rc_link` into ArduCopter | the physical hub's USB lines drove ArduCopter SITL, and the emulated F405, through the same `rc_link`; take-off, ALT HOLD flight, and the radio failsafe (RTL, land, disarm) when a hand went stale |

## What the bench found

Simulation cannot show wiring, mounting, power glitches or pins left floating
([simantic.md §7](simantic.md#7-what-simulation-cannot-tell-you)). The bench found
these. Each row says what was seen, the cause where it is known, and what changed.

| # | Seen | Cause | Change |
|---|---|---|---|
| 1 | LEFT: every flex channel 0 mV, IMU silent | no 3.3 V on the breadboard rail | rewired |
| 2 | RIGHT: four channels SHORT (3.17 V), IMU silent | the resistor/capacitor row had no ground: the bottom-to-top ground jumper was missing | rewired the rail jumpers |
| 3 | RIGHT index flex jumping 0.3–0.9 V | loose flex lead | re-seated |
| 4 | IMU reporting "no new data" after a wire was moved | the breakout lost power briefly and restarted powered down; the hand configures the IMU only at boot | reboot the hand |
| 5 | LEFT IMU answering at 0x6A but WHO_AM_I read 0x00; ESP32 reboot did not help | the LSM6DS3TR-C locked up after a supply glitch; an ESP32 reboot does not power-cycle the breakout | firmware: at boot, a wrong identity triggers a software reset of the chip and one retry. New console commands `i2c` (bus scan) and `i2c recover` |
| 6 | LEFT I2C: SDA and SCL idle low, no device answers | the breakout's pull-ups were unpowered: VIN/GND came loose | rewired |
| 7 | Hub command always invalid: `calibrating` | the hub's CALIBRATE button was not built, and GPIO7 floated low; a jumper to 3V3 did not clear it (not resolved) | bench profile: the hub ignores CALIBRATE |
| 8 | ENABLE refused with the left hand open | the open hand read up to about 17% curl on its saved calibration; ENABLE requires under 5% | bench profile: limit 20% |
| 9 | Holding ENABLE for a whole flight was impractical | deadman by design | bench profile: ENABLE toggles (press on, press again off); a lost hand, fault or reset still ends permission |
| 10 | Thumb gestures not wanted | operator decision | bench profile: no thumb gestures (HOLD uses four fingers; PRECISION never raised) |
| 11 | Leaning the right hand forward flew the drone backward | on that glove the breakout's x axis points the other way | bench profile: right-hand pitch inverted in the hub |
| 12 | The drone kept turning | small left-hand rolls past the 3° deadband gave yaw | bench profile: yaw deadband widened to about 9°, half authority; SITL `PILOT_Y_RATE` 90°/s |
| 13 | A hand stops sending while the hub still shows it connected (LEFT about 29 s after boot; RIGHT after 62 packets, repeatedly) | open. The radio link stays up and the hub sees no disconnect, so the hand's application stopped notifying. RIGHT did not recur after it was reflashed with current firmware; LEFT was not caught in the act | under investigation: `firmware/tools/bench/hand_logger.py` keeps a hand's console open and logs its link and sample counters every 2 s |
| 14 | Opening a board's USB serial port resets it, even with DTR/RTS held low | the CP2102N bridge toggles the lines on open on macOS (not confirmed) | tools open each port once and keep it open |
| 15 | The hub's USB serial dropped once; the demo runner stopped reading | the port disappeared from the host | restart the runner; it does not yet reopen the port |

The bench profile (rows 7–12) is a build option, not the default. The default
firmware keeps the designed behaviour, which the simulation suites test.

## The bench profile

`CONFIG_PALMPILOT_BENCH` (in `firmware/components/palmpilot_core/Kconfig`) builds
the settings above. Build and flash it with:

```sh
python3 firmware/tools/palmpilot.py build hand:left_bench    # also hand:right_bench, hub:bench
cd tmp/palmpilot/hand-left_bench && python -m esptool --chip esp32s3 -p PORT -b 460800 \
    --before default_reset --after hard_reset write_flash "@flash_args"
```

| Setting | Default (designed, tested in simulation) | Bench profile |
|---|---|---|
| ENABLE | held deadman; release ends permission | toggle; second press ends permission |
| Throttle limit for ENABLE | 5% | 20% |
| Thumb gestures | left thumb = PRECISION; HOLD = all five right fingers | none; HOLD = four right fingers |
| Hub CALIBRATE (GPIO7) | read, inhibits output while held | ignored |
| Right-hand pitch | as reported | inverted |
| Yaw | left-hand roll, 1:1 | wider deadband, half authority |

Adopting any of these into the default design means changing
[gesture-mapping.md](gesture-mapping.md) and the suites that test it (S1-C, S1-E,
S1-G and S2-B) together.

## Bench tools

| Tool | What it does |
|---|---|
| `firmware/tools/bench/hands_ui.py` + `hands.html` | Live 3D view of a hand driven by its flex sensors and IMU, over each hand's USB or over Bluetooth through the hub (`hub` `hands` command); per-finger calibration metrics and buttons |
| `firmware/tools/bench/hand_logger.py` | Keeps one board's console open and logs `link` and `stats` every 2 s |
| hand console `cal set E*5 C*5` | Re-enters both calibration ends from an earlier capture (Finish still validates them) |
| hand console `i2c`, `i2c recover` | I2C line levels and bus scan; software reset of the accelerometer |
| hub console `hands` | Each hand's newest packet as the hub received it |
| `simulation/drone/demo_view.py --hub PORT` | The SITL drone (or `--drone f405`) flown by the physical hub, with both hands' telemetry in the side panel |

## Not established

- No physical step of the test plan is passed. B1 meter checks, B2 axis tests with
  recorded evidence, B3 ENABLE timing and B6 USB-serial behaviour remain.
- Calibration persistence was seen to restore after a reset; it is not qualified.
- The packet stall (row 13) is unexplained.
- The bench profile settings were chosen by feel during flights on 2026-11-17;
  none is measured.
