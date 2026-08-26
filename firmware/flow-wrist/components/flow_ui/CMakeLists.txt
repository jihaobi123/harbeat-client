idf_component_register(
    SRCS "flow_ui.c" "flow_ui_theme.c"
    INCLUDE_DIRS "include"
    PRIV_INCLUDE_DIRS "."
    REQUIRES flow_core lvgl
)
