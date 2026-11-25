cmake_minimum_required(VERSION 3.13)

set(PICO_BOARD pico2_w CACHE STRING "Target board")
include(${PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(cyw43439_pico_test C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(TEST_BT_FIRMWARE_DIR "" CACHE PATH
    "Optional directory containing an overriding cyw43_btfw_43439.h")

pico_sdk_init()

add_executable(cyw43439_pico_test main.c)
target_link_libraries(cyw43439_pico_test
    pico_stdlib
    pico_cyw43_arch_none
)
target_compile_definitions(cyw43439_pico_test PRIVATE CYW43_ENABLE_BLUETOOTH=1)
if(TEST_BT_FIRMWARE_DIR)
    if(NOT EXISTS "${TEST_BT_FIRMWARE_DIR}/cyw43_btfw_43439.h")
        message(FATAL_ERROR
            "TEST_BT_FIRMWARE_DIR lacks cyw43_btfw_43439.h: ${TEST_BT_FIRMWARE_DIR}")
    endif()
    target_include_directories(cyw43439_pico_test BEFORE PRIVATE "${TEST_BT_FIRMWARE_DIR}")
    target_compile_definitions(cyw43439_pico_test PRIVATE TEST_FIRMWARE_0071=1)
    message(WARNING "Using experimental Bluetooth firmware from ${TEST_BT_FIRMWARE_DIR}")
endif()
pico_enable_stdio_usb(cyw43439_pico_test 1)
pico_enable_stdio_uart(cyw43439_pico_test 0)
pico_add_extra_outputs(cyw43439_pico_test)

add_executable(cyw43439_usb_dongle
    dongle/main.c
    dongle/usb_descriptors.c
    ${PICO_SDK_PATH}/lib/tinyusb/src/class/bth/bth_device.c
)
target_include_directories(cyw43439_usb_dongle PRIVATE dongle)
target_link_libraries(cyw43439_usb_dongle
    pico_stdlib
    pico_unique_id
    pico_cyw43_arch_none
    tinyusb_device
    tinyusb_board
)
target_compile_definitions(cyw43439_usb_dongle PRIVATE CYW43_ENABLE_BLUETOOTH=1)
pico_enable_stdio_usb(cyw43439_usb_dongle 0)
pico_enable_stdio_uart(cyw43439_usb_dongle 0)
pico_add_extra_outputs(cyw43439_usb_dongle)
