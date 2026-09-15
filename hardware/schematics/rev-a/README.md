# PalmPilot schematic package — Rev A

**Controller-first build baseline, 14 September 2026.** This directory preserves the existing full-system wiring package while the project starts with the hand controllers and hub. Follow the [controller-first drawing index](../README.md) and the [repository implementation checklist](../../../README.md).

## Contents

| File | Purpose |
|---|---|
| [Full schematic and build guide](PalmPilot_Full_Schematic_and_Build_Guide.pdf) | 29 landscape pages, including wiring, connector orientation, component values, assembly checks and 39 source references. |
| [Connection list](connection-list.md) | Human-readable schedule of all 142 connection records. |
| [Connection JSON](connection-netlist.json) | The same connection records, including status fields identifying the trainer prototype. |
| [Schematic sheets](schematic-sheets/) | 11 editable SVG drawings. Open in a browser or vector editor. |
| [Page manifest](render-manifest.json) | Page numbers, titles and authored text from the existing generator run. This is not a test report. |
| [Source figures](../sources/README.md) | Original manufacturer images needed to regenerate the PDF, with attribution. |

Use the PDF and wirelist together. Connection records include local component leads, battery leads and all twelve motor phase leads. A shared net label means those points must have an actual electrical connection.

## Design status

- **Hands:** two Feather nRF52840 Sense boards, five flex inputs each, independent batteries, and a left-hand enable button.
- **Hub:** Feather nRF52840 Express, its own battery, calibration button and a buffered PPM trainer prototype.
- **Radio/aircraft:** Pocket/ELRS and full-size Kakute H7 v1.5/4S architecture. Older XIAO/H7 Mini documents describe earlier work.
- **Open interface gate:** keep JP301 open until Pocket trainer electrical compatibility is established. The proposed waveform, heartbeat logic, hand-data timeout and radio fallback must be implemented and tested on the received hardware and installed firmware.

These are **module-level interconnect drawings**. The SVGs and connection JSON are not a KiCad schematic or an ERC-checked PCB design. They specify a development build; the acceptance records must be completed on real hardware.

## Provenance

The design baseline is the user's [PalmPilot_BOM.pdf](../../../docs/reference/PalmPilot_BOM.pdf), 34 pages. The [source register](connection-list.md#sources) identifies manufacturer documents and reviewed firmware sources. Supporting project notes cover the [hands](../../../docs/schematic-research-hands.md), [trainer](../../../docs/schematic-research-trainer.md) and [aircraft](../../../docs/schematic-research-aircraft.md).

The PDF, SVG sheets, JSON and page manifest were copied byte-for-byte from the previously delivered package in `output/pdf/`. The connection Markdown was copied with its machine-specific Downloads reference replaced by a repository-relative BOM link and a relative PDF link. No electrical assignment changed during repository integration. The original output files remain available for existing local links.

## Regenerate for review

Run from the repository root with Python 3.10 or later:

```sh
python3 -m venv .venv-schematics
.venv-schematics/bin/python -m pip install -r tools/requirements-schematics.txt
.venv-schematics/bin/python tools/build_palmpilot_schematic.py --output-dir output/schematic-review
python3 tools/verify_schematic_package.py --package-dir output/schematic-review --paths output/schematic-review
```

On Windows, use `.venv-schematics/Scripts/python.exe` for the virtual-environment commands. The builder's `--help` command works without installing PDF dependencies. Omitting `--output-dir` writes to `output/pdf/`; use a separate review directory to preserve an existing export.

The generator reads committed figures from `hardware/schematics/sources/`. It uses installed Arial when available and ReportLab's bundled Vera fonts otherwise; no system font file is redistributed. Font substitution can change text wrapping. Render every regenerated PDF page and inspect text, wire junctions, connector orientation and page bounds before promoting an export to a schematic revision. Update the source, connection table and JSON together.

The standard-library verifier checks local Markdown link targets, JSON fields/unique connection IDs, agreement between the table and JSON, and SVG well-formedness. Its intentional Rev A expectations are 142 connection records, 11 SVG sheets and 29 page-manifest entries. `--package-dir` selects the package to check; the default is the committed `hardware/schematics/rev-a` package. `--paths` selects the Markdown files whose links are checked, so use both options to validate a regenerated review export. It does not test electronics, validate remote URLs, run ERC or establish PDF visual correctness. To check the committed package and additional documentation:

```sh
python3 tools/verify_schematic_package.py --paths README.md docs hardware/schematics
```
