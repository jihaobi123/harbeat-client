idf_component_register(
    SRCS "app_main.c"
    INCLUDE_DIRS "."
    REQUIRES flow_ble flow_core flow_power flow_protocol flow_simulator flow_ui nvs_flash
)
