#!/bin/sh
# Downloads the F405 drone firmware: stock ArduCopter 4.7.1 for the Matek F405-Wing,
# unmodified, from firmware.ardupilot.org (GPLv3), and checks its hash.
# The Pixhawk 6X firmware is built instead: simulation/drone/pixhawk6x/build.sh.
# Usage: sh simulation/drone/fetch_arducopter.sh   (from the repository root)
set -eu
URL=https://firmware.ardupilot.org/Copter/stable-4.7.1/MatekF405-Wing/arducopter.elf
SHA256=bbefc904fb6ec1b536a16f1ec6e2a2268f76c897a5c8b0e969719d8f9392739e
OUT=tmp/drone/matekf405-wing-arducopter.elf
mkdir -p tmp/drone
curl -sSfL -o "$OUT" "$URL"
echo "$SHA256  $OUT" | shasum -a 256 -c -
