# Fall 2026 project plan

**Controller baseline: ESP32-S3 hands and hub.** The workbook follows S0–S3/C0–C7/D1–D4. Use the [controller simulation plan](../../docs/controller/simantic-plan.md) for current firmware, sensor and power-design dependencies. Blank dates and unchecked milestones remain pending.

**Scope revised September 16, 2026:** fabricate the hand controller only. The
drone's hardware and microcontroller will be simulated in Simantic; their output
signals will drive a mechanical/dynamics simulation that displays the moving
drone on screen.

Follow the [project checkpoints](../../README.md#full-implementation-checkpoints)
in this order:

1. **S0–S3:** simulate and qualify the hand controller, including sensing,
   calibration, both hands, the hub, commands and fault handling.
2. **C0–C7:** build and qualify the physical hand-controller prototype and its
   computer interface.
3. **D1–D4:** simulate the drone hardware/MCU, use its actuator outputs to drive
   mechanics, integrate the screen display and qualify the complete demo.

The physical controller connects through the hub/computer interface.
Physical drone procurement, fabrication, assembly, propulsion tests and flight
are outside the project scope. S0 records the Simantic version and verifies
first-hand peripheral models. S2 verifies both-hand and BLE modeling; S3 proves
the host command interface. Drone MCU and output support is checked at D1.
Behavioral substitutes and unverified capabilities must be labeled.

[Open the Excel planning workbook](PalmPilot_Fall_2026_Gantt.xlsx).
The four original sheet names are retained:

| Sheet | Current contents |
|---|---|
| Gantt | Ordered S0–S3, C0–C7 and D1–D4 checkpoints plus the fixed course calendar |
| Task plan | Required dependencies, editable duration/start inputs and completion evidence |
| Course milestones | All 30 original course events and dates/times, with revised preparation guidance |
| BOM coverage | Physical controller items, simulation work, optional legacy items and explicit exclusions |

The **August 24–December 11, 2026** calendar and its course deadlines are retained.
The earlier aircraft task dates are retired. **Technical durations and start
dates are unconfirmed**, so those inputs and Gantt bars are intentionally blank.
Enter agreed positive whole workday estimates in the amber cells and an earliest
start for S0. Later earliest starts are optional lower bounds. Required
predecessors drive subsequent planned dates on the next available workday.
Weekend and listed holiday exclusions remain in the workbook.

Dates are planning windows, not completion records. Complete each checkpoint's
evidence before progressing. No completed hardware or simulation results are
asserted. Course deadlines remain fixed regardless of entered technical
estimates; compare the resulting plan with those deadlines before committing to
delivery dates. The source's November 25 break/prototype-update conflict remains
flagged for advisor confirmation.

The [brief PNG](PalmPilot_Brief_Gantt.png) and [editable SVG](PalmPilot_Brief_Gantt.svg)
show the same three-stage scope, final signal path and key course deadlines.
Their filenames are retained for existing references; the brief now shows the
required sequence rather than unconfirmed calendar allocations.

Open the XLSX in Excel or a compatible application. The generated
`.inspect.ndjson` sidecar is local inspection output and is excluded from the
repository. Earlier schedule content remains available in version history.
