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
  # A panic (e.g. an interrupt-watchdog trip) reboots the chip and can hide
  # behind passing checks, so any panic in the run's UART fails the suite.
  uart="tmp/palmpilot/$(basename "$app")/uart.txt"
  if [ -f "$uart" ] && grep -q "Guru Meditation" "$uart"; then
    printf '!!! %s PANICKED: %s\n' "$label" "$(grep -m1 'Guru Meditation' "$uart")"
    failed=$((failed + 1))
  fi
}

# Whole controller: LEFT, RIGHT and HUB on one BLE medium. The first run builds
# all three images.
system() {
  script="$1"; label="$2"; build="$3"
  printf '\n=== %s ===\n' "$label"
  if ! $DRIVER system $build "$script" > tmp/palmpilot/system.log 2>&1; then
    printf '!!! %s FAILED\n' "$label"
    failed=$((failed + 1))
  fi
  grep -E 'FAIL|checks passed|Traceback' tmp/palmpilot/system.log || true
  for board in left right hub; do
    uart="tmp/palmpilot/system/uart-$board.txt"
    if [ -f "$uart" ] && grep -q "Guru Meditation" "$uart"; then
      printf '!!! %s PANICKED on %s\n' "$label" "$board"
      failed=$((failed + 1))
    fi
  done
}

run simulation/simantic/hardware-validation/esp32s3-adc firmware/tools/selftest.py "toolchain self-test"
run firmware/apps/hand firmware/tests/s1a_acquisition.py "S1-A acquisition"
run firmware/apps/hand firmware/tests/s1b_calibration.py "S1-B calibration"
run firmware/apps/hand firmware/tests/s1c_control.py "S1-C control and safety"
run firmware/apps/hand firmware/tests/s1d_motion.py "S1-D motion module"
run firmware/apps/hand firmware/tests/s1e_attitude.py "S1-E attitude and gestures"
run firmware/apps/hand firmware/tests/s1f_persistence.py "S1-F persistence"
run firmware/apps/hand firmware/tests/s1g_packet.py "S1-G packet contract"
run firmware/apps/hand firmware/tests/s1h_watchdog.py "S1-H watchdog discipline"
system firmware/tests/s2a_link.py "S2-A hand-hub BLE link" ""
system firmware/tests/s2b_controller.py "S2-B whole controller" --no-build
system firmware/tests/s3a_drone.py "S3-A hands + hub drive ArduCopter" --no-build

printf '\n===========================================\n'
if [ "$failed" -eq 0 ]; then
  printf 'ALL SUITES PASSED\n'
else
  printf '%d SUITE(S) FAILED\n' "$failed"
  exit 1
fi
