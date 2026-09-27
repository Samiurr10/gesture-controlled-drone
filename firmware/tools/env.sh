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

# --- Simantic engine 0.5.14 / SDK 0.3.1 --------------------------------------
# Pinned explicitly: runtime/engine also still holds 0.5.7 for comparison runs.
export SIMANTIC_HOME="$PALMPILOT_ROOT/tmp/simantic/runtime"
export SIMANTIC_ENGINE_DIR="${SIMANTIC_ENGINE_DIR:-$SIMANTIC_HOME/engine/0.5.14}"
export SIMANTIC_TELEMETRY=0
export PALMPILOT_SIM_PYTHON="$PALMPILOT_ROOT/.venv-simantic/bin/python"

# --- Simulation assets --------------------------------------------------------
# Stock mcu-lib ESP32-S3 platform as served to CLI 0.5.14, unmodified
# (sha256 508f13ad...). Its SENS wires CalibrationEfuse, so ADC1 raw counts
# follow the modeled die's factory calibration, as on silicon.
export PALMPILOT_PLATFORM="${PALMPILOT_PLATFORM:-$PALMPILOT_ROOT/tmp/simantic/platform/ESP32-S3-WROOM-1-N8R2-0.5.14.repl}"
export PALMPILOT_ROM="$PALMPILOT_ROOT/tmp/simantic/esp-idf-tools/esp32s3_rev0_rom.bin"
# Upstream candidates, built from the local renode-infrastructure branches and
# kept until they ship in an engine release (CLAUDE.md section 4):
#  - SYSTIMER: arm on WORK_EN/PERIOD_MODE edges. Without it the FreeRTOS tick
#    dies whenever esp_timer re-arms faster than the tick period.
#  - ESP32S3_Timg with the MWDT modeled, wired as mcu-lib #222 plus resets.
# Set either to an empty string to run the engine's own model.
export PALMPILOT_SYSTIMER_OVERLAY="${PALMPILOT_SYSTIMER_OVERLAY-$PALMPILOT_ROOT/tmp/simantic/upstream-candidates/systimer-work-en/bin/Debug/net10.0/SystFixed.dll}"
export PALMPILOT_S3_MWDT_OVERLAY="${PALMPILOT_S3_MWDT_OVERLAY-$PALMPILOT_ROOT/tmp/simantic/upstream-candidates/s3-mwdt/bin/Debug/net10.0/S3MwdtUnderTest.dll}"
# Superseded local timer-group overlay (hangs esp_restart); used only when
# PALMPILOT_S3_MWDT_OVERLAY is empty.
export PALMPILOT_TIMG_OVERLAY="$PALMPILOT_ROOT/tmp/simantic/timg-overlay/bin/Debug/net10.0/TimgUnderTest.dll"
export PALMPILOT_IMAGE_PACKER="$PALMPILOT_ROOT/tmp/simantic/audit/source-review/esp32s3_build_image.py"

# --- Build output root (gitignored) ------------------------------------------
export PALMPILOT_BUILD_ROOT="$PALMPILOT_ROOT/tmp/palmpilot"

export PALMPILOT_ENV=1
