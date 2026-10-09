# The hand's own BLE peripheral, so the hub sees the same link as from a hand.
idf_component_register(
    SRCS "replay_main.c" "../../hand/main/hand_link.c"
    INCLUDE_DIRS "." "../../hand/main"
    REQUIRES palmpilot_core console bt esp_timer esp_driver_uart esp_system nvs_flash)
