// SPDX-License-Identifier: MIT
// Flex ADC and ENABLE acquisition behind an explicit interface (FW-01), so the
// sensor path can be replaced without touching the control logic.
#pragma once

#include "esp_err.h"
#include "hand_core.h"

// `has_enable` is true on the LEFT hand only. The right hand has no ENABLE
// button fitted, so GPIO7 is left unconfigured and ENABLE always reads released.
esp_err_t hand_acquire_init(bool has_enable);

// Performs one complete five-channel sweep plus a debounced ENABLE read.
// Increments the acquisition counter on completion, so a caller can detect
// sampling frozen behind a live communications task (FW-04).
void hand_acquire_sweep(struct hand_sample *out);

// True when ADC calibration was created for every channel. Calibrated
// millivolts are otherwise reported as -1.
bool hand_acquire_calibrated(void);
