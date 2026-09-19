#!/bin/sh
# Run every PalmPilot firmware simulation test. From the repository root:
#   sh firmware/tests/run_all.sh
set -eu
cd "$(dirname "$0")/../.."
DRIVER="python3 firmware/tools/palmpilot.py"
failed=0

run() {
  app="$1"; script="$2"; label="$3"
  printf '\n=== %s ===\n' "$label"
  if $DRIVER run "$app" "$script" 2>&1 | grep -E 'PASS|FAIL|checks passed|ENGINE ABORTED'; then :; fi
  if ! $DRIVER sim "$app" "$script" >/dev/null 2>&1; then
    printf '!!! %s FAILED\n' "$label"
    failed=$((failed + 1))
  fi
}

run simulation/simantic/hardware-validation/esp32s3-adc firmware/tools/selftest.py "toolchain self-test"
run firmware/apps/hand firmware/tests/s1a_acquisition.py "S1-A acquisition"
run firmware/apps/hand firmware/tests/s1b_calibration.py "S1-B calibration"
run firmware/apps/hand firmware/tests/s1c_control.py "S1-C control and safety"

printf '\n===========================================\n'
if [ "$failed" -eq 0 ]; then
  printf 'ALL SUITES PASSED\n'
else
  printf '%d SUITE(S) FAILED\n' "$failed"
  exit 1
fi
