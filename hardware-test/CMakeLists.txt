cmake_minimum_required(VERSION 3.13)

set(PICO_BOARD pico2_w CACHE STRING "Target board")
include(${PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(cyw43439_pico_test C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(cyw43439_pico_test main.c)
target_link_libraries(cyw43439_pico_test
    pico_stdlib
    pico_cyw43_arch_none
)
target_compile_definitions(cyw43439_pico_test PRIVATE CYW43_ENABLE_BLUETOOTH=1)
pico_enable_stdio_usb(cyw43439_pico_test 1)
pico_enable_stdio_uart(cyw43439_pico_test 0)
pico_add_extra_outputs(cyw43439_pico_test)
