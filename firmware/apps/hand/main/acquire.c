// SPDX-License-Identifier: MIT
#include "acquire.h"

#include "driver/gpio.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_timer.h"

// ENABLE fits its external 10 kOhm pull-up; internal pulls stay off so the
// inactive level is defined by the fitted network, not by firmware (CTRL-030).
static adc_oneshot_unit_handle_t s_adc;
static adc_cali_handle_t s_cali[HAND_FLEX_COUNT];
static struct debounce s_enable;
static uint32_t s_acquisition;
static bool s_calibrated;

esp_err_t hand_acquire_init(void)
{
    const adc_oneshot_unit_init_cfg_t unit = {
        .unit_id = ADC_UNIT_1,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    esp_err_t status = adc_oneshot_new_unit(&unit, &s_adc);
    if (status != ESP_OK) return status;

    const adc_oneshot_chan_cfg_t channel = {
        .atten = (adc_atten_t)HAND_ADC_ATTENUATION,
        .bitwidth = HAND_ADC_BITWIDTH,
    };
    s_calibrated = true;
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
        status = adc_oneshot_config_channel(s_adc, HAND_FLEX_ADC_CHANNEL[i], &channel);
        if (status != ESP_OK) return status;
        const adc_cali_curve_fitting_config_t cali = {
            .unit_id = ADC_UNIT_1,
            .chan = HAND_FLEX_ADC_CHANNEL[i],
            .atten = HAND_ADC_ATTENUATION,
            .bitwidth = HAND_ADC_BITWIDTH,
        };
        if (adc_cali_create_scheme_curve_fitting(&cali, &s_cali[i]) != ESP_OK) {
            s_cali[i] = NULL;
            s_calibrated = false;
        }
    }

    const gpio_config_t enable_pin = {
        .pin_bit_mask = 1ULL << HAND_ENABLE_GPIO,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    status = gpio_config(&enable_pin);
    if (status != ESP_OK) return status;

    // Boot assumption is released. A button held through boot therefore has to
    // produce a release and a new press before it can mean anything (FW-03).
    debounce_init(&s_enable, HAND_ENABLE_DEBOUNCE_SAMPLES, false);
    return ESP_OK;
}

bool hand_acquire_calibrated(void) { return s_calibrated; }

void hand_acquire_sweep(struct hand_sample *out)
{
    out->timestamp_us = esp_timer_get_time();
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
        int raw = -1;
        struct flex_channel *channel = &out->flex[i];
        if (adc_oneshot_read(s_adc, HAND_FLEX_ADC_CHANNEL[i], &raw) != ESP_OK) raw = -1;
        channel->raw = raw;
        channel->millivolts = -1;
        if (raw >= 0 && s_cali[i]) {
            int millivolts = -1;
            if (adc_cali_raw_to_voltage(s_cali[i], raw, &millivolts) == ESP_OK) {
                channel->millivolts = millivolts;
            }
        }
        channel->status = hand_classify_flex(raw);
    }
    out->fault_mask = hand_fault_mask(out->flex, HAND_FLEX_COUNT);

    // Active low: a pressed button pulls the node to ground.
    out->enable_raw = debounce_update(&s_enable, gpio_get_level(HAND_ENABLE_GPIO) == 0);
    out->acquisition = ++s_acquisition;
}
