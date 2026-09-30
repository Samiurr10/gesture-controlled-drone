# Pure controller logic shared by the hand and hub firmware: no ESP-IDF
# dependencies beyond the C library, so it stays host-testable (FW-01).
idf_component_register(
    SRCS "hand_core.c" "packet.c" "hub_core.c"
    INCLUDE_DIRS ".")
