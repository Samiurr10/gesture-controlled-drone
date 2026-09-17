# Historical nRF52840 SAADC request

**Superseded controller target — September 16, 2026.** The controller now uses ESP32-S3. This Nordic-specific specification remains for reproducing the previous audit or contributing nRF support; it is not an active controller requirement. Use the [ESP32 plan](simantic-plan.md) and [migration record](esp32-migration.md). ESP32 ADC requires its own model and driver qualification.

---

# nRF52840 SAADC model handoff

Prepared September 16, 2026 for the PalmPilot controller. This is a requested
capability and acceptance specification, not an implemented model or test result.
The recorded CLI snapshot is `sim 0.5.7`. This capability is needed for S0/S1,
before the physical controller prototype. Firmware/model implementation is not
part of this documentation update. Only the controller will be built physically;
the later drone is simulated in Simantic and displayed through dynamics.

**Immediate scope: one hand unit.** The first ADC milestone covers five flex
inputs and one battery-monitor input on a single Feather Sense. The right hand
and hub follow once the first hand passes; drone simulation is the second goal.
Radio/trainer work is an optional historical extension, not a later required
stage. The ADC requirements below apply directly to the first hand.

## First check: implementation versus platform registration

The retrieved `NRF52840QIAA` platform definition has no SAADC entry. We have not
established whether a compatible SAADC implementation already exists inside the
new engine. Check that first: an existing implementation might need registration
and validation rather than a new model.

We need a model attached at **0x40007000**, with its interrupt routed to **NVIC
IRQ 7**, and an interface to set analog input voltages independently for each
simulated MCU. Do not assume that adding a platform declaration alone implements
the peripheral. Obtain the actual model class name and loading procedure from
the Simantic implementation. [Nordic register map](https://raw.githubusercontent.com/NordicSemiconductor/nrfx/v3.14.0/mdk/nrf52840.h)

## What to provide

1. Engine release or model source/build commit, compatible CLI/SDK versions, and
   installation/loading instructions. For a custom model, document whether it
   requires an engine rebuild or a supported extension mechanism.
2. The platform registration/overlay for `NRF52840QIAA`, including IRQ wiring.
3. A documented input-control API: machine identity, AIN index, volts or millivolts,
   timing of changes, and any virtual supply/reference settings.
4. Supported register/mode coverage, reset behavior, conversion timing, and
   explicit unsupported features.
5. A minimal firmware test ELF and source, with expected UART output or assertions,
   proving that a voltage becomes a result in guest RAM through the actual driver.

The installed Python SDK exposes GPIO and radio injection, but no public analog
input helper was found in its `Sim` interface. Supplying the model **and** the
documented way to change its voltages is therefore important. A proposed input
contract is `(machine, AIN, volts, virtual_time)`; this is not an existing API name.

## Physical input mapping for our controller

| Role | Feather label | GPIO | SAADC input | PSELP selector |
|---|---|---|---|---:|
| Thumb | A0 | P0.04 | AIN2 | 3 |
| Index | A1 | P0.05 | AIN3 | 4 |
| Middle | A2 | P0.30 | AIN6 | 7 |
| Ring | A3 | P0.28 | AIN4 | 5 |
| Little | A4 | P0.02 | AIN0 | 1 |
| Battery monitor | A6 | P0.29 | AIN5 | 6 |

The first hand uses all six listed inputs. The second hand will use the same map
with independent inputs and peripheral state. AIN number, ADC channel slot and
Feather A-number are different identifiers. Adafruit's initial driver repeatedly
uses **CH[0]** while changing its selected AIN.

Mapping evidence: [Feather variant](https://raw.githubusercontent.com/adafruit/Adafruit_nRF52_Arduino/master/variants/feather_nrf52840_sense/variant.cpp),
[ADC input selectors](https://raw.githubusercontent.com/NordicSemiconductor/nrfx/v3.14.0/mdk/nrf52840_bitfields.h).

## Minimum driver-compatible implementation

Our initial firmware configuration is 12-bit, single-ended, internal 0.6 V
reference, gain 1/6 and 10 µs acquisition, with oversampling disabled. The nominal
conversion span is 3.6 V. At a 3.3 V supply, physical inputs must still stay within
the board's pin limits.

Support the enable/configuration registers and all eight channel-selection
register sets so the driver can disconnect unused slots. Implement START,
SAMPLE, STOP and offset-calibration tasks, sticky completion events cleared by
software, and **one-sample EasyDMA writes**.

The current Adafruit driver performs this sequence:

```text
configure CH[0], RESULT.PTR and MAXCNT=1
START → STARTED → clear STARTED
SAMPLE → write signed 16-bit result to guest RAM → END → clear END
STOP → STOPPED → clear STOPPED → disable
```

It polls without a timeout. Missing completion events cause a hang. In
single-ended mode, ignore PSELN: this driver writes the same selected input into
both PSELP and PSELN. Offset calibration also needs CALIBRATEDONE completion;
an ideal zero-offset model still needs the task/event transaction.

**EasyDMA is required even for this basic polling driver.** Interrupts and a
multi-channel scan are separate later capabilities. [Adafruit driver source](https://raw.githubusercontent.com/adafruit/Adafruit_nRF52_Arduino/master/cores/nRF5/wiring_analog_nRF52.c)

### Register address checklist

Offsets are relative to `0x40007000`; use the linked Nordic header as the source
of truth for fields, access rules and reset values.

| Register group | Offset(s) |
|---|---|
| START / SAMPLE / STOP / CALIBRATEOFFSET tasks | 0x000 / 0x004 / 0x008 / 0x00C |
| STARTED / END / DONE / RESULTDONE / CALIBRATEDONE / STOPPED events | 0x100–0x114, step 4 |
| INTEN / INTENSET / INTENCLR | 0x300 / 0x304 / 0x308 |
| STATUS / ENABLE | 0x400 / 0x500 |
| CH[n] PSELP / PSELN / CONFIG / LIMIT | 0x510 + 0x10*n, with offsets +0/+4/+8/+12 |
| RESOLUTION / OVERSAMPLE / SAMPLERATE | 0x5F0 / 0x5F4 / 0x5F8 |
| RESULT.PTR / MAXCNT / AMOUNT | 0x62C / 0x630 / 0x634 |

### Initial configuration values

For the configuration above: RESOLUTION=2; REFSEL=0; GAIN=0; TACQ=2; MODE=0;
RESP=RESN=0; BURST=0; OVERSAMPLE=0; task-controlled sampling. The combined channel
CONFIG value is `0x00020000`. These are hardware encodings, not the units passed
to Arduino helper functions. [Nordic bitfields](https://raw.githubusercontent.com/NordicSemiconductor/nrfx/v3.14.0/mdk/nrf52840_bitfields.h)

## Calculated input vectors

Use an ideal model first, with the rounding rule documented. Approximate counts
follow `Vin * 4096 / 3.6`. Allow a one-count rounding difference for these model
checks; real hardware tolerances require separate measured limits.

| Input case | Voltage presented to ADC | Approximate 12-bit count |
|---|---:|---:|
| Ground / settled unplugged flex | 0 V | 0 |
| Known voltage | 0.9 V | 1024 |
| Known voltage | 1.8 V | 2048 |
| Known voltage | 2.7 V | 3072 |
| Local rail / shorted flex | 3.3 V | 3755 |
| 25 kΩ flex with 47 kΩ shunt, 3.3 V supply | 2.154167 V | 2451 |
| 100 kΩ flex with 47 kΩ shunt, 3.3 V supply | 1.055102 V | 1200 |
| 4.2 V battery through board's 1:2 monitor divider | 2.1 V at A6 | 2389 |

These are calculated stimuli, not measured sensor ranges. Supply battery
**half-voltage** to AIN5; do not supply 4.2 V directly to an ADC pin.

## Acceptance checks

- [ ] Unmodified selected ADC driver completes start/sample/stop and calibration.
- [ ] Every listed AIN responds independently; rapidly alternating low/high inputs
  proves the mux is not returning an old channel's result.
- [ ] Single-sample writes use little-endian signed 16-bit results in guest RAM.
  Buffer guards remain unchanged; AMOUNT and MAXCNT use sample counts, not bytes.
- [ ] Cleared events do not remain stuck; repeated conversions and reset work.
- [ ] Completion timing follows virtual time and is stated explicitly. Instant
  ideal conversions must not be presented as validated acquisition timing.
- [ ] Different hand/hub instances never share channel state or stimuli.
- [ ] A scripted ramp and open/short cases reach the real driver through the
  modeled ADC rather than by overwriting application variables.

### Subsequent coverage

Add IRQ7 mask/clear behavior, multi-channel scan and larger buffers, partial stop,
timer/PPI triggers, other resolution/reference modes, and any oversampling/burst
features used by the eventual firmware. Test event ordering, DMA completion and
buffer boundaries before enabling those driver paths. Unsupported configurations
must be visible rather than silently producing plausible values.

Voltage stimulus alone does not prove RC settling, input loading, regulator
dropout or physical calibration. Initially supply those effects as explicit,
labeled voltage traces; validate physical behavior separately.

## Hand-unit requirements beyond ADC

For the first milestone we need one firmware ELF, the exact motion-sensor models,
I2C driver compatibility, ENABLE input and diagnostic assertions. The full-system
table below records later dependencies. BLE/hub follow in S2/S3; PPM and Pocket
are optional historical work outside controller acceptance.

| Requirement | What is still needed |
|---|---|
| Firmware | Reproducible ELF targets for left, right and hub; selected board core/BLE stack and boot layout |
| Motion sensors | Correct Sense revision and compatible LSM6DS3TR-C (or older LSM6DS33) plus LIS3MDL models, with controllable motion traces |
| I2C | Compatibility with the chosen driver's TWI/TWIM and EasyDMA usage |
| BLE | Tested two-peripheral/one-central scenario and deterministic loss/delay/reconnect cases |
| Buttons, commands and watchdog | Active-low inputs, timers, versioned hub-to-host commands, expiry and watchdog/reset checks |
| Host transport | Verify chosen USB serial support, or label a simulator-only UART adapter; test the real transport during C6 |
| Test infrastructure | Compatible SDK engine, assertion-based tests, versioned traces and coverage reports |
| Physical prototype | Later bench measurements for battery/rail behavior, ADC performance, sensing, BLE and host commands |
| Optional trainer extension | PPM edges, buffer levels and Pocket takeover are separate optional tests, not controller acceptance gates |

The software stage needs no new physical components. A real Feather Sense,
USB data cable, DMM and known voltage/divider inputs are useful reference equipment
for later model comparison. The existing flex/47 kΩ/100 nF circuit supplies the
project-specific reference behavior.

See the [controller Simantic plan](simantic-plan.md) for the implementation order.
No firmware builds, peripheral instantiations or simulation runs were performed
to prepare this handoff.
