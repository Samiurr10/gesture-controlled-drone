idf_component_register(
    SRCS "hand_main.c" "acquire.c" "hand_core.c" "motion.c" "persist.c" "packet.c"
    INCLUDE_DIRS "."
    REQUIRES esp_adc esp_timer esp_driver_uart esp_driver_gpio esp_driver_i2c esp_system nvs_flash)
