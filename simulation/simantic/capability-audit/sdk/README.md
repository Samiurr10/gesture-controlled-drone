# SDK, user-owned inputs and timestamped outputs

> **Report snapshot:** this documentation package includes audit reports and concise results. Test sources, setup scripts and detailed traces referenced below remain local bench material; reproduction commands require that separate harness and are not runnable from this documentation checkout alone.

Tested with Python SDK 0.3.1 and Renode engine 0.5.7 on macOS arm64. These are
diagnostic fixtures, not controller or flight application firmware. See
[results.json](results.json) for assertions, observed values and hashes.

## Runtime results

| Path | Result and boundary |
|---|---|
| nRF ELF boot, UARTE DMA TX/RX | PASS: ready message, injected `Q`, RAM result 81, one receive and exact echo |
| Left ENABLE GPIO input | PASS: SDK drives P1.08 high/low; firmware records both transitions |
| Virtual time | PASS: a requested 5 ms step advances the clock by 5 ms; reads do not advance it. `run_for()` returns the cumulative elapsed time in this version; use `sim.time` differences for step duration |
| UART timestamps | PASS for completed lines. `expect()` sees partial text earlier; `uart_records()` did not expose the lone `Q` until its newline arrived |
| GPIO output observation | PASS: firmware sets/clears P0.13; an engine GPIO callback captures rising/falling edges at 1.1/3.1 ms. This is an engine adapter below `Sim`, not a first-class Python SDK helper; sub-microsecond accuracy is not established |
| User-provided SPI responses | PASS: H7 firmware talks to `SPI.ScriptedSpiSlave` and receives the expected byte |
| User-provided I2C responses | PASS: H7 firmware talks to `I2C.ScriptedI2cSlave` and reads expected register data |
| Mutable Python input provider | PASS at slave-interface boundary: host changes shared Python values; direct slave calls return the new values. The second transactions bypass the MCU bus; this does not claim a second firmware-driven dynamic-input test |

The H7 firmware used for scripted-bus checks also prints its known PWM/DMA
failures. Those are preserved in the transcript and do not become passes here.
The scripted fixtures imitate only the minimal register exchange needed by the
bus diagnostic; they are not BME280, Feather IMU or aircraft IMU models.

## Input ownership

The project can own flex-voltage traces, accelerometer/gyro samples, sensor
register maps, physics and display. Scripted bus devices are already available.
`scripted_i2c.py` implements `Slave(ctx)`, `on_write(bytes)`, `on_read(count)` and
optional `on_finish()`; `scripted_spi.py` implements `on_transmit(byte)` and
`on_finish()`. The engine supplies the actual MCU bus behavior. Their provider
module is deliberately tiny to demonstrate custom inputs without implementing
project sensors.

H7 ADC injection is separately proven in [the H7 audit](../stm32h7/README.md)
through `IADCExtensions.SetVoltage(adc, microvolts, channel)`. The nRF SAADC still
needs a model and an equivalent documented input setter.

For output hooks, `output_hook.py` uses the running Renode machine's GPIO
`AddStateChangedHook` and virtual timestamp. This adapter relies on engine types
and pythonnet reflection because the SDK returns generic peripheral interfaces.
Pin versions; a stable SDK wrapper would improve maintenance but a new display
or co-simulation framework is not necessary from Simantic.

## Reproduce

From repository root, after obtaining the two authenticated platform files in
`tmp/simantic/models/` and installing the engine under `tmp/simantic/runtime/`:

```sh
export SIMANTIC_HOME="$PWD/tmp/simantic/runtime"
export SIMANTIC_TELEMETRY=0
export DOTNET_BUNDLE_EXTRACT_BASE_DIR=/private/tmp/palmpilot-simantic-dotnet
.venv-simantic/bin/python simulation/simantic/capability-audit/sdk/build.py
.venv-simantic/bin/python simulation/simantic/capability-audit/sdk/probe.py
.venv-simantic/bin/python simulation/simantic/capability-audit/sdk/output_hook.py
```

For the scripted bus test, first run the H7 build/audit to create
`tmp/simantic/audit/stm32h7/full-probe.elf` and `io-fixtures.repl`, then:

```sh
.venv-simantic/bin/python simulation/simantic/capability-audit/sdk/scripted_buses.py
```

`inspect_runtime.py` and `inspect_io.py` are read-only runtime metadata probes.
Presence in their output is not behavioral test evidence. The engine requires
access to its normal Renode configuration lock outside this repository; a
sandbox lock failure is an environment issue, not a peripheral failure.
