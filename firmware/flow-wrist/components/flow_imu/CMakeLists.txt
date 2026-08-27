idf_component_register(
    SRCS "flow_imu.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_driver_i2c esp_timer freertos
             waveshare__esp32_s3_touch_amoled_2_06 waveshare__qmi8658
)
