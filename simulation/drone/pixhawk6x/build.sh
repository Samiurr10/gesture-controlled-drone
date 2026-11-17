#!/bin/sh
# Builds tmp/drone/pixhawk6x-arducopter.elf: ArduCopter 4.7.1 (tag Copter-4.7.1, the commit
# of the stock release) for the Pixhawk6X board, with defaults.parm built in. The stock
# release defaults to BRD_IO_ENABLE 1 and stops at boot on "Failed to update IO firmware"
# when no IOMCU answers, before MAVLink starts, so the parameter cannot be set over the link.
# Toolchain: gcc-arm-none-eabi 10-2020-q4, the one ArduPilot's release builds use.
# The checkout and defaults.parm need paths without spaces: ChibiOS's make splits on them.
#   sh simulation/drone/pixhawk6x/build.sh <ardupilot checkout at Copter-4.7.1> <toolchain bin dir>
set -eu
AP=${1:?ardupilot checkout}; GCC=${2:?arm-none-eabi bin dir}
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../.." && pwd)
export PATH="$GCC:$PATH"
PARM="$AP/palmpilot-defaults.parm"
cp "$HERE/defaults.parm" "$PARM"
cd "$AP"
./waf configure --board Pixhawk6X --default-parameters="$PARM"
./waf copter
mkdir -p "$ROOT/tmp/drone"
cp build/Pixhawk6X/bin/arducopter "$ROOT/tmp/drone/pixhawk6x-arducopter.elf"
