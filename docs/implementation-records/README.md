# Implementation evidence

No physical build or firmware qualification results have been recorded yet.
The checked documentation items in the root README do not count as completed
bench tests.

For each checkpoint, create a dated Markdown record in this directory using the
[test record template](../controller/test-record-template.md). A useful filename
is `YYYY-MM-DD_CTRL-xx_short-description.md`; use the exact test ID from the
[controller validation plan](../controller/validation.md).

Include the hardware revision, firmware commit and configuration, measurement
method, expected behavior, observed result, supporting logs/captures and pass or
fail decision. Record failures too. Every checked physical implementation item
in the [root README](../../README.md) should link to its evidence record.

Keep small reproducible logs and calibration files alongside their record.
Reference large raw recordings by stable storage URL and checksum. Avoid putting
disposable renders, virtual environments or unreviewed exports into Git.

After any change to a pin assignment, packet format, mapping, radio model,
battery configuration or enclosure, identify affected tests and repeat them
before reusing an earlier release claim.
