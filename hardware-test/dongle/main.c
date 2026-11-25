#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "bsp/board.h"
#include "cyw43.h"
#include "cybt_shared_bus_driver.h"
#include "pico/bootrom.h"
#include "pico/cyw43_arch.h"
#include "pico/stdlib.h"
#include "tusb.h"

#define HCI_HEADER_SIZE 4u
#define HCI_COMMAND 0x01u
#define HCI_ACL 0x02u
#define HCI_EVENT 0x04u
#define HCI_COMMAND_MAX 260u
#define HCI_ACL_MAX 1030u
#define HOST_COMMAND_QUEUE 8u
#define HOST_ACL_QUEUE 16u
#define DEVICE_EVENT_QUEUE 64u
#define DEVICE_ACL_QUEUE 16u

typedef struct {
    uint16_t length;
    uint8_t data[HCI_COMMAND_MAX];
} command_packet_t;

typedef struct {
    uint16_t length;
    uint8_t data[HCI_ACL_MAX];
} acl_packet_t;

typedef struct {
    uint16_t length;
    uint8_t data[HCI_COMMAND_MAX];
} event_packet_t;

static command_packet_t host_commands[HOST_COMMAND_QUEUE];
static acl_packet_t host_acl[HOST_ACL_QUEUE];
static event_packet_t device_events[DEVICE_EVENT_QUEUE];
static acl_packet_t device_acl[DEVICE_ACL_QUEUE];
static uint8_t hc_in, hc_out, hc_count;
static uint8_t ha_in, ha_out, ha_count;
static uint8_t de_in, de_out, de_count;
static uint8_t da_in, da_out, da_count;
static acl_packet_t acl_assembly;
static uint16_t acl_expected;
static bool usb_event_busy, usb_acl_busy;
static volatile bool controller_work;
static volatile bool activity_pending;
static bool radio_ok;
static bool activity_led_on;
static absolute_time_t activity_led_off;
static absolute_time_t activity_led_ready;
static uint32_t command_rx, command_tx, acl_host_rx, acl_host_tx;
static uint32_t event_rx, event_tx, acl_device_rx, acl_device_tx;
static uint32_t drops, controller_errors;
static uint32_t backpressure;
static bool controller_stalled;
static uint32_t event_histogram[256];

bool btstack_cyw43_init(async_context_t *context) {
    (void)context;
    return true;
}

void btstack_cyw43_deinit(async_context_t *context) {
    (void)context;
}

void cyw43_bluetooth_hci_process(void) {
    controller_work = true;
}

static void log_line(const char *format, ...) {
    if (!tud_cdc_connected()) return;
    char line[256];
    va_list args;
    va_start(args, format);
    int length = vsnprintf(line, sizeof(line), format, args);
    va_end(args);
    if (length < 0) return;
    if ((size_t)length > sizeof(line) - 3) length = sizeof(line) - 3;
    line[length++] = '\r';
    line[length++] = '\n';
    tud_cdc_write(line, (uint32_t)length);
    tud_cdc_write_flush();
}

static void print_status(void) {
    log_line("STATUS radio=%s usb=%u cmd=%lu/%lu acl_host=%lu/%lu evt=%lu/%lu acl_dev=%lu/%lu drops=%lu errors=%lu",
             radio_ok ? "OK" : "FAIL", tud_mounted(),
             (unsigned long)command_rx, (unsigned long)command_tx,
             (unsigned long)acl_host_rx, (unsigned long)acl_host_tx,
             (unsigned long)event_rx, (unsigned long)event_tx,
             (unsigned long)acl_device_rx, (unsigned long)acl_device_tx,
             (unsigned long)drops, (unsigned long)controller_errors);
    log_line("FLOW backpressure=%lu host_cmd_q=%u host_acl_q=%u dev_evt_q=%u dev_acl_q=%u",
             (unsigned long)backpressure, hc_count, ha_count, de_count, da_count);
}

void tud_mount_cb(void) {
    activity_pending = true;
}

void tud_umount_cb(void) {
    cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, false);
}

void tud_bt_hci_cmd_cb(void *data, size_t length) {
    activity_pending = true;
    command_rx++;
    if (length > HCI_COMMAND_MAX || hc_count == HOST_COMMAND_QUEUE) {
        drops++;
        return;
    }
    host_commands[hc_in].length = (uint16_t)length;
    memcpy(host_commands[hc_in].data, data, length);
    hc_in = (uint8_t)((hc_in + 1) % HOST_COMMAND_QUEUE);
    hc_count++;
}

void tud_bt_acl_data_received_cb(void *data, uint16_t length) {
    activity_pending = true;
    if (acl_assembly.length + length > HCI_ACL_MAX) {
        acl_assembly.length = 0;
        acl_expected = 0;
        drops++;
        return;
    }
    memcpy(acl_assembly.data + acl_assembly.length, data, length);
    acl_assembly.length += length;
    if (acl_expected == 0 && acl_assembly.length >= 4) {
        acl_expected = (uint16_t)(4 + acl_assembly.data[2] +
                                 ((uint16_t)acl_assembly.data[3] << 8));
        if (acl_expected > HCI_ACL_MAX || acl_expected < 4) {
            acl_assembly.length = 0;
            acl_expected = 0;
            drops++;
            return;
        }
    }
    if (acl_expected != 0 && acl_assembly.length == acl_expected) {
        acl_host_rx++;
        if (ha_count == HOST_ACL_QUEUE) {
            drops++;
        } else {
            host_acl[ha_in] = acl_assembly;
            ha_in = (uint8_t)((ha_in + 1) % HOST_ACL_QUEUE);
            ha_count++;
        }
        acl_assembly.length = 0;
        acl_expected = 0;
    } else if (acl_expected != 0 && acl_assembly.length > acl_expected) {
        acl_assembly.length = 0;
        acl_expected = 0;
        drops++;
    }
}

void tud_bt_event_sent_cb(uint16_t sent_bytes) {
    (void)sent_bytes;
    if (usb_event_busy && de_count) {
        de_out = (uint8_t)((de_out + 1) % DEVICE_EVENT_QUEUE);
        de_count--;
        event_tx++;
    }
    usb_event_busy = false;
}

void tud_bt_acl_data_sent_cb(uint16_t sent_bytes) {
    (void)sent_bytes;
    if (usb_acl_busy && da_count) {
        da_out = (uint8_t)((da_out + 1) % DEVICE_ACL_QUEUE);
        da_count--;
        acl_device_tx++;
    }
    usb_acl_busy = false;
}

static int controller_write(uint8_t type, const uint8_t *payload, uint16_t length) {
    static uint8_t buffer[HCI_HEADER_SIZE + HCI_ACL_MAX] __attribute__((aligned(4)));
    memset(buffer, 0, HCI_HEADER_SIZE);
    buffer[3] = type;
    memcpy(buffer + HCI_HEADER_SIZE, payload, length);
    return cyw43_bluetooth_hci_write(buffer, HCI_HEADER_SIZE + length);
}

/*
 * Returns true when the queue head should be released. A full controller
 * ring keeps the packet queued for retry; any other error drops it so one bad
 * packet cannot stall the bridge. backpressure counts stall episodes, not
 * individual retries.
 */
static bool controller_write_result(int result) {
    if (result == CYBT_ERR_QUEUE_FULL) {
        if (!controller_stalled) backpressure++;
        controller_stalled = true;
        return false;
    }
    controller_stalled = false;
    if (result != 0) controller_errors++;
    return true;
}

static void send_host_queues(void) {
    if (hc_count) {
        command_packet_t *packet = &host_commands[hc_out];
        int result = controller_write(HCI_COMMAND, packet->data, packet->length);
        if (controller_write_result(result)) {
            hc_out = (uint8_t)((hc_out + 1) % HOST_COMMAND_QUEUE);
            hc_count--;
            if (result == 0) command_tx++;
        }
        return;
    }
    if (ha_count) {
        acl_packet_t *packet = &host_acl[ha_out];
        int result = controller_write(HCI_ACL, packet->data, packet->length);
        if (controller_write_result(result)) {
            ha_out = (uint8_t)((ha_out + 1) % HOST_ACL_QUEUE);
            ha_count--;
            if (result == 0) acl_host_tx++;
        }
    }
}

static void receive_controller(void) {
    if (!controller_work) return;
    controller_work = false;
    static uint8_t buffer[HCI_HEADER_SIZE + HCI_ACL_MAX] __attribute__((aligned(4)));
    for (unsigned attempt = 0; attempt < 8; ++attempt) {
        uint32_t length = 0;
        int result = cyw43_bluetooth_hci_read(buffer, sizeof(buffer), &length);
        if (result != 0) {
            controller_errors++;
            return;
        }
        if (length <= HCI_HEADER_SIZE) return;
        const uint8_t type = buffer[3];
        const uint16_t payload_length = (uint16_t)(length - HCI_HEADER_SIZE);
        if (type == HCI_EVENT && payload_length <= HCI_COMMAND_MAX) {
            activity_pending = true;
            event_rx++;
            if (payload_length) event_histogram[buffer[HCI_HEADER_SIZE]]++;
            if (de_count == DEVICE_EVENT_QUEUE) drops++;
            else {
                device_events[de_in].length = payload_length;
                memcpy(device_events[de_in].data, buffer + HCI_HEADER_SIZE, payload_length);
                de_in = (uint8_t)((de_in + 1) % DEVICE_EVENT_QUEUE);
                de_count++;
            }
        } else if (type == HCI_ACL && payload_length <= HCI_ACL_MAX) {
            activity_pending = true;
            acl_device_rx++;
            if (da_count == DEVICE_ACL_QUEUE) drops++;
            else {
                device_acl[da_in].length = payload_length;
                memcpy(device_acl[da_in].data, buffer + HCI_HEADER_SIZE, payload_length);
                da_in = (uint8_t)((da_in + 1) % DEVICE_ACL_QUEUE);
                da_count++;
            }
        } else {
            drops++;
        }
    }
    controller_work = true;
}

static void service_activity_led(void) {
    if (!radio_ok) return;
    if (activity_led_on &&
        absolute_time_diff_us(get_absolute_time(), activity_led_off) <= 0) {
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, false);
        activity_led_on = false;
        activity_led_ready = make_timeout_time_ms(35);
    }
    if (!activity_led_on && activity_pending &&
        absolute_time_diff_us(get_absolute_time(), activity_led_ready) <= 0) {
        activity_pending = false;
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, true);
        activity_led_on = true;
        activity_led_off = make_timeout_time_ms(35);
    }
}

static void service_usb_transmit(void) {
    if (!usb_event_busy && de_count) {
        event_packet_t *packet = &device_events[de_out];
        if (tud_bt_event_send(packet->data, packet->length)) usb_event_busy = true;
    }
    if (!usb_acl_busy && da_count) {
        acl_packet_t *packet = &device_acl[da_out];
        if (tud_bt_acl_data_send(packet->data, packet->length)) usb_acl_busy = true;
    }
}

static void process_console(void) {
    static char command[32];
    static uint8_t used;
    while (tud_cdc_available()) {
        char ch;
        if (tud_cdc_read(&ch, 1) != 1) break;
        if (ch == '\r' || ch == '\n') {
            if (!used) continue;
            command[used] = '\0';
            if (strcmp(command, "status") == 0) print_status();
            else if (strcmp(command, "events") == 0) {
                for (unsigned i = 0; i < 256; ++i) {
                    if (event_histogram[i]) log_line("EVENT %02x count=%lu", i,
                                                    (unsigned long)event_histogram[i]);
                }
            }
            else if (strcmp(command, "bootsel") == 0) reset_usb_boot(0, 0);
            else log_line("COMMANDS status events bootsel");
            used = 0;
        } else if (used + 1 < sizeof(command)) {
            command[used++] = ch;
        }
    }
}

int main(void) {
    board_init();
    radio_ok = cyw43_arch_init() == 0;
    tusb_init();
    absolute_time_t next_status = make_timeout_time_ms(5000);
    while (true) {
        tud_task();
        cyw43_arch_poll();
        receive_controller();
        send_host_queues();
        service_usb_transmit();
        process_console();
        service_activity_led();
        if (absolute_time_diff_us(get_absolute_time(), next_status) <= 0) {
            print_status();
            next_status = make_timeout_time_ms(5000);
        }
    }
}
