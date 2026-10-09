idf_component_register(
    SRCS "hand_main.c" "acquire.c" "motion.c" "persist.c" "hand_link.c"
    INCLUDE_DIRS "."
    REQUIRES palmpilot_core console bt esp_adc esp_timer esp_driver_uart esp_driver_gpio
             esp_driver_i2c esp_system nvs_flash)
