idf_component_register(
    SRCS "flow_ui.c"
         "flow_ui_theme.c"
         "flow_ui_connection.c"
         "flow_ui_home.c"
         "flow_ui_carousel.c"
         "flow_ui_gesture.c"
         "flow_carousel_model.c"
         "flow_ui_art.c"
         "flow_ui_transition.c"
         "assets/flow_dancer_assets.c"
    INCLUDE_DIRS "include"
    PRIV_INCLUDE_DIRS "." "assets"
    REQUIRES flow_core lvgl
)
