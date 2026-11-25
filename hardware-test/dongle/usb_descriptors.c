#include <string.h>

#include "pico/unique_id.h"
#include "tusb.h"

enum {
    ITF_NUM_BTH,
    ITF_NUM_BTH_VOICE,
    ITF_NUM_CDC,
    ITF_NUM_CDC_DATA,
    ITF_NUM_TOTAL
};

enum {
    STRID_LANGID,
    STRID_MANUFACTURER,
    STRID_PRODUCT,
    STRID_SERIAL,
    STRID_BTH,
    STRID_CDC
};

#define USB_VID 0x2E8A
#define USB_PID 0x10C1
#define EP_BTH_EVENT 0x81
#define EP_BTH_ACL_OUT 0x02
#define EP_BTH_ACL_IN 0x82
#define EP_BTH_ISO_OUT 0x03
#define EP_BTH_ISO_IN 0x83
#define EP_CDC_NOTIF 0x85
#define EP_CDC_OUT 0x06
#define EP_CDC_IN 0x86

tusb_desc_device_t const device_descriptor = {
    .bLength = sizeof(tusb_desc_device_t),
    .bDescriptorType = TUSB_DESC_DEVICE,
    .bcdUSB = 0x0200,
    .bDeviceClass = TUSB_CLASS_MISC,
    .bDeviceSubClass = MISC_SUBCLASS_COMMON,
    .bDeviceProtocol = MISC_PROTOCOL_IAD,
    .bMaxPacketSize0 = CFG_TUD_ENDPOINT0_SIZE,
    .idVendor = USB_VID,
    .idProduct = USB_PID,
    .bcdDevice = 0x0100,
    .iManufacturer = STRID_MANUFACTURER,
    .iProduct = STRID_PRODUCT,
    .iSerialNumber = STRID_SERIAL,
    .bNumConfigurations = 1
};

uint8_t const *tud_descriptor_device_cb(void) {
    return (uint8_t const *)&device_descriptor;
}

#define CONFIG_TOTAL_LEN (TUD_CONFIG_DESC_LEN + TUD_BTH_DESC_LEN + TUD_CDC_DESC_LEN)

uint8_t const configuration_descriptor[] = {
    TUD_CONFIG_DESCRIPTOR(1, ITF_NUM_TOTAL, STRID_PRODUCT, CONFIG_TOTAL_LEN,
                          TUSB_DESC_CONFIG_ATT_REMOTE_WAKEUP, 100),
    TUD_BTH_DESCRIPTOR(ITF_NUM_BTH, STRID_BTH,
                       EP_BTH_EVENT, CFG_TUD_BTH_EVENT_EPSIZE, 1,
                       EP_BTH_ACL_IN, EP_BTH_ACL_OUT, CFG_TUD_BTH_DATA_EPSIZE,
                       64),
    TUD_CDC_DESCRIPTOR(ITF_NUM_CDC, STRID_CDC, EP_CDC_NOTIF, 8,
                       EP_CDC_OUT, EP_CDC_IN, CFG_TUD_CDC_EP_BUFSIZE)
};

uint8_t const *tud_descriptor_configuration_cb(uint8_t index) {
    (void)index;
    return configuration_descriptor;
}

static char const *string_descriptors[] = {
    (const char[]){0x09, 0x04},
    "CYW43439 RE Lab",
    "Pico 2 W Bluetooth Adapter",
    NULL,
    "Bluetooth HCI",
    "Diagnostics"
};

static uint16_t descriptor_buffer[33];

uint16_t const *tud_descriptor_string_cb(uint8_t index, uint16_t langid) {
    (void)langid;
    uint8_t count;
    if (index == STRID_LANGID) {
        memcpy(&descriptor_buffer[1], string_descriptors[0], 2);
        count = 1;
    } else if (index == STRID_SERIAL) {
        pico_unique_board_id_t id;
        pico_get_unique_board_id(&id);
        static const char hex[] = "0123456789ABCDEF";
        count = PICO_UNIQUE_BOARD_ID_SIZE_BYTES * 2;
        for (uint8_t i = 0; i < PICO_UNIQUE_BOARD_ID_SIZE_BYTES; ++i) {
            descriptor_buffer[1 + i * 2] = hex[id.id[i] >> 4];
            descriptor_buffer[2 + i * 2] = hex[id.id[i] & 0x0f];
        }
    } else {
        if (index >= sizeof(string_descriptors) / sizeof(string_descriptors[0]) ||
            string_descriptors[index] == NULL) return NULL;
        const char *text = string_descriptors[index];
        count = (uint8_t)strlen(text);
        if (count > 32) count = 32;
        for (uint8_t i = 0; i < count; ++i) descriptor_buffer[1 + i] = text[i];
    }
    descriptor_buffer[0] = (uint16_t)((TUSB_DESC_STRING << 8) | (2 * count + 2));
    return descriptor_buffer;
}
