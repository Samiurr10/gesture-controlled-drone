# Aircraft integration — replaced by drone simulation

**Scope changed September 16, 2026.** The project will physically build only the hand gesture controller. It will not construct or fly a physical drone.

The former A0–A5 aircraft assembly, power, propulsion, navigation and flight milestones are retired. Physical Kakute/ESC/motor/propeller/airframe procurement, a Pocket/ELRS radio chain and a props-off flight-controller fixture are not prerequisites for controller completion.

Follow this sequence:

1. [Simulate the hand controller in Simantic](controller/simantic-plan.md), S0–S3.
2. [Build and qualify the physical hand controller](controller/README.md), C0–C7.
3. [Simulate drone hardware and MCU execution in Simantic](drone-simulation.md), D1.
4. Feed its motor/actuator output signals into a mechanical/dynamics simulation, return sensor feedback and show the resulting motion on screen, D2–D4.

The [current architecture](architecture.md) defines the controller-to-computer and virtual-drone boundaries. The [project checklist](../README.md#full-implementation-checkpoints) is the current execution plan.

This path remains so older links resolve. Earlier wiring and component decisions remain available as explicitly historical [aircraft research](schematic-research-aircraft.md), [Rev A drawings](../hardware/schematics/README.md) and the [source BOM](reference/README.md). Those references may inform virtual models; they do not define a later physical-aircraft phase.
