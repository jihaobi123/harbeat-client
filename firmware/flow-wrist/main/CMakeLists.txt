idf_component_register(
    SRCS "app_main.c"
    INCLUDE_DIRS "."
    REQUIRES flow_core flow_ui nvs_flash
)
