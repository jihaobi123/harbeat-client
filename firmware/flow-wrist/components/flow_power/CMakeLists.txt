idf_component_register(
    SRCS "flow_power.c" "flow_power_policy.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_driver_gpio esp_driver_i2c esp_timer freertos
             waveshare__esp32_s3_touch_amoled_2_06
)
