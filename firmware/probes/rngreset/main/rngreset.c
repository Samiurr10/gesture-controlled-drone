// SPDX-License-Identifier: MIT
// Does the hardware RNG give new values after a software reset?
//
// Boot 1 draws four words from esp_random(), keeps them in NVS and restarts.
// Boot 2 draws four more and compares. A hardware RNG never replays a previous
// boot's values, so any identical word fails. Boot 2 then forgets the stored
// words, so the next power-up runs the test again.
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "esp_random.h"
#include "esp_system.h"
#include "nvs.h"
#include "nvs_flash.h"

#define WORDS 4

static void draw(uint32_t *out, const char *label)
{
    printf("RNG: %s", label);
    for (int i = 0; i < WORDS; ++i) {
        out[i] = esp_random();
        printf(" %08" PRIx32, out[i]);
    }
    printf("\n");
}

void app_main(void)
{
    if (nvs_flash_init() != ESP_OK) {
        nvs_flash_erase();
        nvs_flash_init();
    }
    nvs_handle_t nvs;
    nvs_open("rngreset", NVS_READWRITE, &nvs);
    uint32_t before[WORDS], after[WORDS];
    size_t size = sizeof(before);
    if (nvs_get_blob(nvs, "words", before, &size) != ESP_OK) {
        draw(before, "boot1");
        nvs_set_blob(nvs, "words", before, sizeof(before));
        nvs_commit(nvs);
        printf("RNG: restarting\n");
        fflush(stdout);
        esp_restart();
    }
    draw(after, "boot2");
    int same = 0;
    for (int i = 0; i < WORDS; ++i) same += before[i] == after[i];
    nvs_erase_key(nvs, "words");
    nvs_commit(nvs);
    printf("RESULT: %s repeated=%d reset_reason=%d\n", same ? "FAIL" : "PASS", same, esp_reset_reason());
}
