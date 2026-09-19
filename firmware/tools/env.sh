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
export PATH="$IDF_PYTHON_ENV_PATH/bin:$PALMPILOT_XTENSA_BIN:$PATH"

# --- Simantic engine 0.5.7 / SDK 0.3.1 ---------------------------------------
export SIMANTIC_HOME="$PALMPILOT_ROOT/tmp/simantic/runtime"
export SIMANTIC_TELEMETRY=0
export PALMPILOT_SIM_PYTHON="$PALMPILOT_ROOT/.venv-simantic/bin/python"

# --- Simulation assets --------------------------------------------------------
export PALMPILOT_PLATFORM="$PALMPILOT_ROOT/tmp/simantic/audit/esp32s3/ESP32-S3-WROOM-1-N8R2.repl"
export PALMPILOT_ROM="$PALMPILOT_ROOT/tmp/simantic/esp-idf-tools/esp32s3_rev0_rom.bin"
export PALMPILOT_ADC_OVERLAY="$PALMPILOT_ROOT/tmp/simantic/adc-s3-validation/repro/model/bin/Debug/net10.0/S3AdcUnderTest.dll"
export PALMPILOT_IMAGE_PACKER="$PALMPILOT_ROOT/tmp/simantic/audit/source-review/esp32s3_build_image.py"

# --- Build output root (gitignored) ------------------------------------------
export PALMPILOT_BUILD_ROOT="$PALMPILOT_ROOT/tmp/palmpilot"

export PALMPILOT_ENV=1
