idf_component_register(SRCS "nvs_probe.c" INCLUDE_DIRS "."
    REQUIRES esp_driver_uart esp_timer esp_system nvs_flash)
