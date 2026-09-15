# Fall 2026 Gantt schedule

[Download the Excel Gantt workbook](PalmPilot_Fall_2026_Gantt.xlsx).

The workbook covers **August 24–December 11, 2026**, a 16-week planning window.
It contains four sheets:

| Sheet | Contents |
|---|---|
| Gantt | Timeline across planning, mechanical, electrical, integration and course work |
| Task plan | Planned task dates and dependencies |
| Course milestones | Course deliverables and milestones |
| BOM coverage | Build-plan coverage of project components |

## Status: original parallel-work baseline

This is the existing planning workbook, preserved unchanged for publication.
It predates the current controller-first implementation order. In particular:

- E13 aircraft harness is scheduled October 6–9.
- E14 FC/ESC startup is scheduled October 12–14.
- E17 controller latency/takeover qualification is scheduled October 22–27
  and depends on E15 aircraft/manual controls.

The current [README checkpoints](../../README.md#full-implementation-checkpoints)
put controller bench qualification C7 before main aircraft assembly and place
flight-controller integration later at A2. **Follow that checkpoint order.**
Revise the workbook's dates and dependencies before using it to schedule the
controller-first execution plan. Planned dates are not completed test results.

Open the XLSX in Excel or another compatible spreadsheet application. It is
self-contained; the generated `.inspect.ndjson` sidecar is local inspection
output and is excluded from the repository.
