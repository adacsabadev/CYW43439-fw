#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "cyw43.h"
#include "pico/cyw43_arch.h"
#include "pico/stdlib.h"
#include "pico/bootrom.h"

#define HCI_HEADER_SIZE 4u
#define HCI_PACKET_COMMAND 0x01u
#define HCI_PACKET_EVENT 0x04u

static volatile bool hci_work_pending;
static bool radio_initialized;
static bool hci_reset_passed;
static int radio_init_result = -999;
static int hci_write_result = -999;
static uint8_t last_event[64];
static uint32_t last_event_length;

/* CYW43 arch requires these integration callbacks when Bluetooth is enabled. */
bool btstack_cyw43_init(async_context_t *context) {
    (void)context;
    return true;
}

void btstack_cyw43_deinit(async_context_t *context) {
    (void)context;
}

void cyw43_bluetooth_hci_process(void) {
    hci_work_pending = true;
}

static void led(bool on) {
    if (radio_initialized) {
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, on);
    }
}

static void print_hex(const uint8_t *data, uint32_t length) {
    for (uint32_t i = 0; i < length; ++i) printf("%02x", data[i]);
}

static void print_status(void) {
    printf("STATUS radio_init=%d radio=%s hci_write=%d hci_reset=%s event_len=%lu event=",
           radio_init_result,
           radio_initialized ? "OK" : "FAIL",
           hci_write_result,
           hci_reset_passed ? "PASS" : "FAIL",
           (unsigned long)last_event_length);
    print_hex(last_event, last_event_length);
    printf("\r\n");
}

static void poll_hci(void) {
    if (!radio_initialized || !hci_work_pending) return;
    hci_work_pending = false;

    uint8_t buffer[HCI_HEADER_SIZE + sizeof(last_event)] __attribute__((aligned(4)));
    uint32_t length = 0;
    const int result = cyw43_bluetooth_hci_read(buffer, sizeof(buffer), &length);
    if (result != 0 || length <= HCI_HEADER_SIZE) return;

    const uint8_t type = buffer[3];
    const uint32_t payload_length = length - HCI_HEADER_SIZE;
    const uint32_t copy_length = payload_length < sizeof(last_event) ?
                                 payload_length : sizeof(last_event);
    memcpy(last_event, buffer + HCI_HEADER_SIZE, copy_length);
    last_event_length = copy_length;

    /* Command Complete for HCI Reset: 0e 04 01 03 0c 00 */
    if (type == HCI_PACKET_EVENT && payload_length >= 6 &&
        buffer[4] == 0x0e && buffer[6] == 0x01 &&
        buffer[7] == 0x03 && buffer[8] == 0x0c && buffer[9] == 0x00) {
        hci_reset_passed = true;
        led(true);
        printf("HCI_RESET PASS\r\n");
    } else {
        printf("HCI_RX type=%02x length=%lu data=", type, (unsigned long)payload_length);
        print_hex(buffer + HCI_HEADER_SIZE, payload_length);
        printf("\r\n");
    }
}

static void send_hci_reset(void) {
    uint8_t command[HCI_HEADER_SIZE + 3] __attribute__((aligned(4))) = {
        0, 0, 0, HCI_PACKET_COMMAND,
        0x03, 0x0c, 0x00
    };
    hci_reset_passed = false;
    last_event_length = 0;
    hci_write_result = cyw43_bluetooth_hci_write(command, sizeof(command));
    printf("HCI_RESET sent result=%d\r\n", hci_write_result);
}

static void process_console(void) {
    static char line[32];
    static size_t used;
    int value;
    while ((value = getchar_timeout_us(0)) != PICO_ERROR_TIMEOUT) {
        const char ch = (char)value;
        if (ch == '\r' || ch == '\n') {
            if (used == 0) continue;
            line[used] = '\0';
            if (strcmp(line, "status") == 0) print_status();
            else if (strcmp(line, "hci-reset") == 0 && radio_initialized) send_hci_reset();
            else if (strcmp(line, "bootsel") == 0) reset_usb_boot(0, 0);
            else if (strcmp(line, "led-on") == 0) led(true);
            else if (strcmp(line, "led-off") == 0) led(false);
            else printf("COMMANDS status hci-reset led-on led-off bootsel\r\n");
            used = 0;
        } else if (used + 1 < sizeof(line)) {
            line[used++] = ch;
        }
    }
}

int main(void) {
    stdio_init_all();
    sleep_ms(1500);
    printf("\r\nCYW43439 PICO2W TEST v1\r\n");
    printf("BOOT rp2350 firmware=stock-sdk-0065\r\n");

    radio_init_result = cyw43_arch_init();
    radio_initialized = radio_init_result == 0;
    printf("CYW43_INIT %s result=%d\r\n", radio_initialized ? "PASS" : "FAIL", radio_init_result);
    if (radio_initialized) send_hci_reset();

    absolute_time_t next_status = make_timeout_time_ms(5000);
    bool heartbeat = false;
    while (true) {
        cyw43_arch_poll();
        poll_hci();
        process_console();
        if (absolute_time_diff_us(get_absolute_time(), next_status) <= 0) {
            heartbeat = !heartbeat;
            if (!hci_reset_passed) led(heartbeat);
            print_status();
            next_status = make_timeout_time_ms(5000);
        }
        sleep_ms(1);
    }
}
