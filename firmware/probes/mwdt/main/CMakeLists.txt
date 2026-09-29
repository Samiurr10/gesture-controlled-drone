idf_component_register(SRCS "mwdt_probe.c" INCLUDE_DIRS "."
    REQUIRES esp_driver_uart esp_timer esp_system hal soc esp_rom esp_hw_support)
