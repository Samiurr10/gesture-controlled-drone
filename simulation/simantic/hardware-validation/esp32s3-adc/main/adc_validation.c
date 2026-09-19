// SPDX-License-Identifier: MIT
// Public ESP-IDF driver validation. Same application on silicon and Simantic.
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "driver/uart.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_chip_info.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "soc/sens_struct.h"

static adc_oneshot_unit_handle_t adc;
static uint32_t sequence;

static void error(const char *operation, esp_err_t status)
{
    printf("{\"type\":\"error\",\"op\":\"%s\",\"status\":%d}\n", operation, status);
}

static void info(void)
{
    esp_chip_info_t chip;
    esp_chip_info(&chip);
    printf("{\"type\":\"info\",\"fixture\":\"palmpilot-adc-v1\",\"idf\":\"%s\","
           "\"chip_model\":%d,\"revision\":%d,\"cores\":%d,\"reset_reason\":%d}\n",
           esp_get_idf_version(), chip.model, chip.revision, chip.cores, esp_reset_reason());
}

static void registers(void)
{
    // Read-only observation: lets hardware settle the force-power discrepancy.
    printf("{\"type\":\"registers\",\"reader1\":%" PRIu32 ",\"meas1\":%" PRIu32
           ",\"mux1\":%" PRIu32 ",\"atten1\":%" PRIu32 ",\"power\":%" PRIu32
           ",\"clock\":%" PRIu32 ",\"reset\":%" PRIu32 "}\n",
           SENS.sar_reader1_ctrl.val, SENS.sar_meas1_ctrl2.val,
           SENS.sar_meas1_mux.val, SENS.sar_atten1, SENS.sar_power_xpd_sar.val,
           SENS.sar_peri_clk_gate_conf.val, SENS.sar_peri_reset_conf.val);
}

static void read_samples(int channel, int attenuation, int count)
{
    const uint32_t batch = ++sequence;
    printf("{\"type\":\"begin\",\"batch\":%" PRIu32 ",\"channel\":%d,\"gpio\":%d,"
           "\"attenuation\":%d,\"count\":%d}\n", batch, channel, channel + 1, attenuation, count);
    fflush(stdout);
    const adc_oneshot_chan_cfg_t config = {
        .atten = (adc_atten_t)attenuation, .bitwidth = ADC_BITWIDTH_12,
    };
    esp_err_t status = adc_oneshot_config_channel(adc, channel, &config);
    if (status != ESP_OK) { error("config_channel", status); return; }
    adc_cali_handle_t calibration = NULL;
    const adc_cali_curve_fitting_config_t calibration_config = {
        .unit_id = ADC_UNIT_1, .chan = channel, .atten = attenuation,
        .bitwidth = ADC_BITWIDTH_12,
    };
    esp_err_t calibration_status = adc_cali_create_scheme_curve_fitting(&calibration_config, &calibration);
    printf("{\"type\":\"configured\",\"batch\":%" PRIu32 ",\"calibration_status\":%d}\n",
           batch, calibration_status);
    registers();
    fflush(stdout);
    int successful = 0;
    for (int i = 0; i < count; ++i) {
        int raw = -1, millivolts = -1;
        const int64_t start = esp_timer_get_time();
        status = adc_oneshot_read(adc, channel, &raw);
        const int64_t elapsed = esp_timer_get_time() - start;
        esp_err_t cal_status = calibration_status;
        if (status == ESP_OK) {
            ++successful;
            if (calibration) cal_status = adc_cali_raw_to_voltage(calibration, raw, &millivolts);
        }
        printf("{\"type\":\"sample\",\"batch\":%" PRIu32 ",\"index\":%d,\"t_us\":%" PRId64
               ",\"read_us\":%" PRId64 ",\"status\":%d,\"raw\":%d,\"cal_status\":%d,\"mv\":%d}\n",
               batch, i, start, elapsed, status, raw, cal_status, millivolts);
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    if (calibration) adc_cali_delete_scheme_curve_fitting(calibration);
    printf("{\"type\":\"end\",\"batch\":%" PRIu32 ",\"successful\":%d,\"requested\":%d}\n",
           batch, successful, count);
    fflush(stdout);
}

static void command(const char *line)
{
    int channel, attenuation, count;
    char extra;
    if (!strcmp(line, "info")) info();
    else if (!strcmp(line, "regs")) registers();
    else if (sscanf(line, "read %d %d %d %c", &channel, &attenuation, &count, &extra) == 3
             && channel >= 0 && channel <= 9 && attenuation >= 0 && attenuation <= 3
             && count >= 1 && count <= 1024) read_samples(channel, attenuation, count);
    else printf("{\"type\":\"error\",\"op\":\"command\",\"help\":\"info | regs | read CHANNEL ATTEN COUNT\"}\n");
    fflush(stdout);
}

void app_main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    info();
    const adc_oneshot_unit_init_cfg_t config = {
        .unit_id = ADC_UNIT_1, .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    esp_err_t status = adc_oneshot_new_unit(&config, &adc);
    if (status != ESP_OK) { error("new_unit", status); return; }
    status = uart_driver_install(UART_NUM_0, 1024, 0, 0, NULL, 0);
    if (status != ESP_OK) { error("uart_install", status); return; }
    printf("{\"type\":\"ready\",\"commands\":\"info | regs | read CHANNEL ATTEN COUNT\"}\n");
    char line[96];
    size_t used = 0;
    bool discard = false;
    for (;;) {
        unsigned char c;
        if (uart_read_bytes(UART_NUM_0, &c, 1, pdMS_TO_TICKS(100)) != 1) continue;
        if (c == '\r' || c == '\n') {
            if (discard) error("line_too_long", ESP_ERR_INVALID_SIZE);
            else if (used) { line[used] = 0; command(line); }
            used = 0; discard = false;
        } else if (used < sizeof(line) - 1 && !discard) {
            line[used++] = c;
        } else discard = true;
    }
}
