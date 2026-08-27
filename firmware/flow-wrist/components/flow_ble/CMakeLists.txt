idf_component_register(
    SRCS "flow_ble.c" "flow_link_state.c"
    INCLUDE_DIRS "include"
    REQUIRES bt flow_protocol freertos
)
