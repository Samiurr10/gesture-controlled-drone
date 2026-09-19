# Simantic project setup

Simulate the **ESP32-S3 hand controller first**. The later drone uses an
**STM32H743** candidate, with MCU motor outputs driving dynamics and display.

- [Controller setup, supported paths and remaining work](../../docs/controller/simantic-plan.md)
- [Controller firmware requirements](../../docs/controller/firmware-plan.md)
- [Physical parts](../../docs/controller/bom.md) and [wiring](../../docs/controller/build-guide.md)
- [Full implementation checkpoints](../../README.md#full-implementation-checkpoints)
- [Later drone simulation](../../docs/drone-simulation.md)

## ADC dependency

[Simantic PR #168](https://github.com/simantic-dev/renode-infrastructure/pull/168)
provides the ADC1 implementation and calibrated-state option used in validation.
Stock engine 0.5.7 does not include it. With the candidate installed, add
`CalibrationEfuse: efuse` to the existing SENS platform declaration to use the
same factory profile as firmware. The PR contains detailed tests and limitations.

The project supplies flex voltages, motion-sensor register fixtures and fault
inputs. Those inputs must pass through the firmware's MCU drivers. The project
also implements the host command bridge, drone dynamics and display.

Keep generated logs, downloaded toolchains and temporary peripheral-debug
experiments in ignored local directories. Commit the executable project
firmware and reusable simulation scenarios as they are implemented.
