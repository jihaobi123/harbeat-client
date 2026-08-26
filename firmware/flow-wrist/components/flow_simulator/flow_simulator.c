#include "flow_simulator.h"

#include <stdbool.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

static QueueHandle_t s_command_queue;
static flow_snapshot_handler_t s_handler;
static void *s_handler_context;
static flow_snapshot_t s_snapshot;

static void emit_snapshot(void)
{
    ++s_snapshot.revision;
    s_handler(&s_snapshot, s_handler_context);
}

static uint16_t bpm_for_energy(uint8_t energy)
{
    static const uint16_t bpm[] = {78, 88, 96, 108, 118};
    return bpm[energy - 1];
}

static void set_target(const flow_command_t *command)
{
    s_snapshot.target = s_snapshot.current;
    if (command->operation == FLOW_OPERATION_SET_ENERGY) {
        s_snapshot.target.energy = command->energy;
        s_snapshot.target.bpm = bpm_for_energy(command->energy);
    } else {
        strcpy(s_snapshot.target.style, command->style);
    }
}

static void drain_busy_commands(void)
{
    flow_command_t ignored;
    while (xQueueReceive(s_command_queue, &ignored, 0) == pdTRUE) {
        strcpy(s_snapshot.error, "busy");
        emit_snapshot();
        s_snapshot.error[0] = '\0';
    }
}

static void simulator_task(void *context)
{
    (void)context;
    s_handler(&s_snapshot, s_handler_context);

    flow_command_t command;
    while (true) {
        if (xQueueReceive(s_command_queue, &command, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        if (!flow_protocol_validate_command(&command)) {
            continue;
        }

        set_target(&command);
        s_snapshot.ack_id = command.id;
        s_snapshot.phase = FLOW_PHASE_ACCEPTED;
        s_snapshot.locked = true;
        s_snapshot.eta_ms = 12000;
        emit_snapshot();

        for (uint32_t remaining = 11000; remaining >= 1000; remaining -= 1000) {
            vTaskDelay(pdMS_TO_TICKS(1000));
            drain_busy_commands();
            s_snapshot.phase = remaining >= 6000
                ? FLOW_PHASE_PREPARING
                : FLOW_PHASE_TRANSITIONING;
            s_snapshot.eta_ms = remaining;
            emit_snapshot();
        }

        vTaskDelay(pdMS_TO_TICKS(1000));
        drain_busy_commands();
        s_snapshot.current = s_snapshot.target;
        s_snapshot.phase = FLOW_PHASE_COMPLETED;
        s_snapshot.locked = false;
        s_snapshot.eta_ms = 0;
        emit_snapshot();
    }
}

esp_err_t flow_simulator_start(flow_snapshot_handler_t handler, void *context)
{
    if (handler == NULL || s_command_queue != NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    s_handler = handler;
    s_handler_context = context;
    memset(&s_snapshot, 0, sizeof(s_snapshot));
    strcpy(s_snapshot.session_id, "8f3a19d04b7c221e");
    s_snapshot.revision = 1;
    s_snapshot.phase = FLOW_PHASE_IDLE;
    s_snapshot.current.energy = 3;
    strcpy(s_snapshot.current.style, "hiphop");
    s_snapshot.current.bpm = 96;
    s_snapshot.target = s_snapshot.current;

    s_command_queue = xQueueCreate(4, sizeof(flow_command_t));
    if (s_command_queue == NULL) {
        return ESP_ERR_NO_MEM;
    }
    if (xTaskCreate(simulator_task, "flow_hub_sim", 4096, NULL, 5, NULL) != pdPASS) {
        vQueueDelete(s_command_queue);
        s_command_queue = NULL;
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}

esp_err_t flow_simulator_submit(const flow_command_t *command)
{
    if (s_command_queue == NULL || !flow_protocol_validate_command(command)) {
        return ESP_ERR_INVALID_ARG;
    }
    return xQueueSend(s_command_queue, command, 0) == pdTRUE
        ? ESP_OK
        : ESP_ERR_TIMEOUT;
}
