idf_component_register(
    SRCS "hub_main.c" "hub_link.c"
    INCLUDE_DIRS "."
    REQUIRES palmpilot_core console bt esp_timer esp_driver_uart esp_driver_gpio esp_system nvs_flash)
