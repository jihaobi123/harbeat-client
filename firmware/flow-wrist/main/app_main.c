#include "bsp/esp-bsp.h"
#include "esp_err.h"
#include "lvgl.h"
#include "nvs_flash.h"

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    lv_display_t *display = bsp_display_start();
    ESP_ERROR_CHECK(display == NULL ? ESP_FAIL : ESP_OK);
    ESP_ERROR_CHECK(bsp_display_lock(0) ? ESP_OK : ESP_FAIL);

    lv_obj_t *screen = lv_screen_active();
    lv_obj_set_style_bg_color(screen, lv_color_hex(0xFFF8ED), 0);

    lv_obj_t *label = lv_label_create(screen);
    lv_label_set_text(label, "FLOW WRIST\nBRING-UP");
    lv_obj_set_style_text_color(label, lv_color_hex(0x11110F), 0);
    lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_center(label);

    bsp_display_unlock();
}
