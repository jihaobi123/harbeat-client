idf_component_register(
    SRCS "flow_ui.c"
         "flow_ui_theme.c"
         "flow_ui_home.c"
         "flow_ui_carousel.c"
         "flow_ui_art.c"
         "flow_ui_transition.c"
    INCLUDE_DIRS "include"
    PRIV_INCLUDE_DIRS "."
    REQUIRES flow_core lvgl
)
