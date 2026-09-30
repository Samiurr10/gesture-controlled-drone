# Gesture mapping — proposed v1

**Status: PROPOSED, not frozen.** [FW-05](firmware-plan.md) requires this table
to be frozen at S3 from measured behavior, and re-measured on the prototype at
C5 (CTRL-051). Every numeric value below is a **starting candidate selected for
implementation**, not a qualified limit. No value here is evidence.

This fills the gap left open by [architecture.md](../architecture.md): "exact
gesture mapping, throttle interpretation, serialization, sample rate and
accepted age/skew limits must be frozen in S3."

## Design principle: two hands, two sticks

The controller has ten flex channels and two 9-DoF modules. The mapping assigns
each hand the role of one stick on a **Mode 2 RC transmitter**, because that
layout is the one most drone operators already have muscle memory for.

| Transmitter | PalmPilot |
|---|---|
| Left stick: throttle (vertical), yaw (horizontal) | **Left hand:** finger curl = throttle, hand roll = yaw |
| Right stick: pitch (vertical), roll (horizontal) | **Right hand:** hand pitch = pitch, hand roll = roll |

Right-hand tilt is spatially direct — the hand leans the way the drone leans.
Left-hand curl is an absolute, self-holding quantity, which is what throttle
needs; a tilt would have to be held against gravity for the whole flight.

## Command table

| Source | Sensor | Command | Range | Centering |
|---|---|---|---|---|
| Right hand roll tilt | accelerometer gravity vector | `roll` | [-1, 1] | self-centering, level = 0 |
| Right hand pitch tilt | accelerometer gravity vector | `pitch` | [-1, 1] | self-centering, level = 0 |
| Left hand roll tilt | accelerometer gravity vector | `yaw` | [-1, 1] | self-centering, level = 0 |
| Left hand index+middle+ring+little mean curl | flex | `throttle` | [0, 1] | **absolute, holds position** |

Candidate response, all provisional:

| Parameter | Candidate | Note |
|---|---|---|
| Tilt saturation | ±30° | full command at 30° from calibrated neutral |
| Tilt deadband | ±3° | measure actual hand tremor before freezing |
| Throttle deadband | 3% of calibrated travel | at the open-hand end |
| Slew limit, attitude | 4.0 /s | full -1→+1 sweep takes ≥ 0.5 s |
| Slew limit, throttle | 1.5 /s | |
| Low-pass corner | 5 Hz | select from measured hand noise |

**Open hand = 0 throttle, full curl = 1.0.** The relaxed resting hand is
therefore the zero-thrust state, and a half-curl — a comfortable sustained
posture — is roughly hover.

## Yaw is gravity-referenced, never magnetic

Yaw comes from **left-hand roll tilt against gravity**, not from hand heading.
Neither the magnetometer nor an integrated gyro yaw may produce a command.

The proposed mapping avoids hand heading because an operator
turning their body would command an unintended rotation. Gravity-referenced
roll and pitch have a fixed external reference and cannot drift.

The magnetometer may be read and logged. It must not reach the command path
until it is separately calibrated and qualified.

## Discrete gestures

| Gesture | Detection | Effect |
|---|---|---|
| **ENABLE** | left GPIO7 held, active low, debounced | deadman. Commands are valid only while held |
| **HOLD** | right hand all five fingers curled past 80% | zeroes roll/pitch/yaw, freezes throttle at its current value |
| **PRECISION** | left thumb curled past 60% | halves roll, pitch and yaw; throttle unchanged |
| **CALIBRATE** | hub GPIO7, output inhibited | captures neutral for both hands |

HOLD is a positive action that only ever *reduces* authority, so a false
positive is safe and a false negative leaves the operator with normal control.
A clenched fist is unlikely to occur accidentally while tilting. Thumb curl is
independent of the four-finger throttle average, so PRECISION does not disturb
throttle.

## Safety interlocks

These are requirements on the firmware, not suggestions.

1. **Throttle-low to enable.** A new ENABLE press is refused unless throttle is
   below 5%. Enabling with a closed left fist must never be possible.
2. **ENABLE held at boot is ineffective** until released and newly pressed.
   A held button is never recovery consent; a short to ground can imitate a
   press.
3. **Either hand invalid invalidates the whole command** — stale, uncalibrated,
   sensor-faulted, wrong session or wrong side.
4. **Near-rail flex readings are faults, not commands.** An unplugged sensor
   pulls toward GND through 47 kΩ and a shorted one saturates at 3V3; neither
   may be normalized into maximum travel.
5. **Fault latches.** Recovery requires ENABLE release, a new deliberate press,
   fresh valid data from both hands, and explicit host restart.
6. **No axis exceeds its bound after mapping**, and the slew limits above are
   applied after deadband and filtering.
7. ENABLE grants gesture input inside an already-started run. It never arms,
   starts or resumes the virtual drone on its own.

## What this does not settle

Serialization, packet rates, `T_hand` maximum age, left/right skew, watchdog
period and fault-to-invalid latency remain **UNSET** and are frozen in S3 from
measurement. Sign conventions must be re-verified against the drone model's
body frame at D2 — this table fixes the controller's output frame only.

Flex channels currently unassigned to a command: right thumb (HOLD only), left
index/middle/ring/little contribute to throttle as a mean. Per-finger commands
are deliberately avoided in v1; a single finger is a poor continuous control and
a good discrete one.
