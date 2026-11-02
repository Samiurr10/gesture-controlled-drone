# PalmPilot ESP32-S3 toolchain — single source of truth for pinned paths.
# Usage:  . firmware/tools/env.sh     (from the repository root)
#
# Everything here lives in gitignored tmp/ and is NOT reproducible from a clean
# checkout. See CLAUDE.md section 3. Do not delete tmp/simantic/.

if [ ! -f CLAUDE.md ] || [ ! -d tmp/simantic ]; then
  echo "env.sh: run from the repository root (needs ./CLAUDE.md and ./tmp/simantic)" >&2
  return 1 2>/dev/null || exit 1
fi

PALMPILOT_ROOT="$PWD"

# --- ESP-IDF v5.5.2 -----------------------------------------------------------
export IDF_PATH="$PALMPILOT_ROOT/tmp/simantic/adc-s3-validation/esp-idf-5.5.2"
export IDF_TOOLS_PATH="$PALMPILOT_ROOT/tmp/simantic/esp-idf-tools"
export IDF_PYTHON_ENV_PATH="$PALMPILOT_ROOT/tmp/simantic/esp-idf-python"
export IDF_COMPONENT_MANAGER=0
PALMPILOT_XTENSA_BIN="$PALMPILOT_ROOT/tmp/simantic/audit/esp32s3/toolchain/xtensa-esp-elf/bin"
# RISC-V toolchain (C3/C6/P4), used only by the cross-chip SYSTIMER probe.
PALMPILOT_RISCV_BIN="$(ls -d "$IDF_TOOLS_PATH"/tools/riscv32-esp-elf/*/riscv32-esp-elf/bin 2>/dev/null | head -1)"
export PATH="$IDF_PYTHON_ENV_PATH/bin:$PALMPILOT_XTENSA_BIN${PALMPILOT_RISCV_BIN:+:$PALMPILOT_RISCV_BIN}:$PATH"

# --- Simantic engine 0.6.6 / SDK 0.4.0 ---------------------------------------
# Pinned explicitly: runtime/engine also holds older engines for comparison runs.
export SIMANTIC_HOME="$PALMPILOT_ROOT/tmp/simantic/runtime"
export SIMANTIC_ENGINE_DIR="${SIMANTIC_ENGINE_DIR:-$SIMANTIC_HOME/engine/0.6.6}"
export SIMANTIC_TELEMETRY=0
export PALMPILOT_SIM_PYTHON="$PALMPILOT_ROOT/.venv-simantic/bin/python"
# The engine's scripted peers run on CPython: point it at the venv's own libpython.
export SIMANTIC_PYTHON_DLL="${SIMANTIC_PYTHON_DLL:-$("$PALMPILOT_SIM_PYTHON" -c 'import sys, sysconfig; print(sys.base_prefix + "/lib/" + sysconfig.get_config_var("LDLIBRARY"))')}"

# --- Simulation assets --------------------------------------------------------
# Stock mcu-lib ESP32-S3 platform as served to CLI 0.5.14, unmodified
# (sha256 508f13ad...). Its SENS wires CalibrationEfuse, so ADC1 raw counts
# follow the modeled die's factory calibration, as on silicon.
export PALMPILOT_PLATFORM="${PALMPILOT_PLATFORM:-$PALMPILOT_ROOT/tmp/simantic/platform/ESP32-S3-WROOM-1-N8R2-0.6.6.repl}"
export PALMPILOT_ROM="$PALMPILOT_ROOT/tmp/simantic/esp-idf-tools/esp32s3_rev0_rom.bin"
# Model candidates (simulation/simantic/model-candidates), kept until an engine
# release ships them. Set one to an empty string to run the engine's own model.
#  - RNG: a new boot draws new random values. renode-infrastructure#271
# Shipped, so these stay empty: SYSTIMER (#257) and S3 MWDT (#258) in 0.5.15,
# BLE radio (#270) and STM32 UART TX DMA (#325) in 0.6.6.
export PALMPILOT_SYSTIMER_OVERLAY="${PALMPILOT_SYSTIMER_OVERLAY-}"
export PALMPILOT_S3_MWDT_OVERLAY="${PALMPILOT_S3_MWDT_OVERLAY-}"
export PALMPILOT_BLE_RADIO_OVERLAY="${PALMPILOT_BLE_RADIO_OVERLAY-}"
export PALMPILOT_STM32_UART_OVERLAY="${PALMPILOT_STM32_UART_OVERLAY-}"
export PALMPILOT_RNG_OVERLAY="${PALMPILOT_RNG_OVERLAY-$PALMPILOT_ROOT/tmp/simantic/upstream-candidates/rng-reset/bin/Debug/net10.0/RngFixed.dll}"

# --- Drone (Goal 2): stock ArduCopter 4.7.1 -----------------------------------
# PALMPILOT_DRONE=f405 (default): Matek F405-Wing, STM32F405. About 3x faster to simulate.
# PALMPILOT_DRONE=h7: Holybro Pixhawk 6X, STM32H753, the mcu-lib Pixhawk6X model.
# ELFs: simulation/drone/fetch_arducopter.sh. Board overlays and sensor scripts come
# from a local sim-fixtures checkout (private, not copied here).
export PALMPILOT_DRONE="${PALMPILOT_DRONE:-f405}"
case "$PALMPILOT_DRONE" in
  h7)
    export PALMPILOT_DRONE_ELF="$PALMPILOT_ROOT/tmp/drone/pixhawk6x-arducopter.elf"
    export PALMPILOT_DRONE_PLATFORM="$PALMPILOT_ROOT/tmp/simantic/platform/Pixhawk6X-0.6.6.repl"
    export PALMPILOT_DRONE_BOARD="${PALMPILOT_DRONE_BOARD:-$PALMPILOT_ROOT/tmp/simantic/sim-fixtures/tests/stm/pixhawk6x/arducopter-valkyrie}" ;;
  f405)
    export PALMPILOT_DRONE_ELF="$PALMPILOT_ROOT/tmp/drone/matekf405-wing-arducopter.elf"
    export PALMPILOT_DRONE_PLATFORM="$PALMPILOT_ROOT/tmp/simantic/platform/STM32F405RG-0.6.6.repl"
    export PALMPILOT_DRONE_BOARD="${PALMPILOT_DRONE_BOARD:-$PALMPILOT_ROOT/tmp/simantic/sim-fixtures/tests/stm/matek-f405-wing}" ;;
  *) echo "env.sh: PALMPILOT_DRONE must be h7 or f405" >&2; return 1 2>/dev/null || exit 1 ;;
esac
# Superseded local timer-group overlay (hangs esp_restart); used only when
# PALMPILOT_S3_MWDT_OVERLAY is empty.
export PALMPILOT_TIMG_OVERLAY="$PALMPILOT_ROOT/tmp/simantic/timg-overlay/bin/Debug/net10.0/TimgUnderTest.dll"
export PALMPILOT_IMAGE_PACKER="$PALMPILOT_ROOT/tmp/simantic/audit/source-review/esp32s3_build_image.py"

# --- Build output root (gitignored) ------------------------------------------
export PALMPILOT_BUILD_ROOT="$PALMPILOT_ROOT/tmp/palmpilot"

export PALMPILOT_ENV=1
