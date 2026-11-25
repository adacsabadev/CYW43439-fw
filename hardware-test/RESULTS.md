# Live hardware results

Test board: Raspberry Pi Pico 2 W, RP2350 USB serial `61EDF42ACD25F7A0`.
Test date: 2026-11-25 (Europe/Bucharest).

## Stock Pico SDK `.0065`

Windows enumerated USB CDC as COM16. The CYW43 shared-bus firmware initialized,
the raw HCI Reset write succeeded and the controller returned the expected
Command Complete event:

```text
STATUS radio_init=0 radio=OK hci_write=0 hci_reset=PASS event_len=6 event=0e0401030c00
```

Result: **known-good recovery image**.

UF2: `build/stock-0065/cyw43439_pico_test.uf2`

SHA-256: `56B057D3625AA82152471BD58504E7E063EFDE1B2F1EF77796CA93CCECC99A76`

## Converted Murata `.0071`

Windows enumerated the same USB CDC interface. `cyw43_arch_init()` returned
zero, but the first raw HCI Reset write returned decimal `180` (`0xB4`,
`CYBT_ERR_HCI_INIT_FAILED`) and no controller event arrived:

```text
STATUS radio_init=0 radio=OK hci_write=180 hci_reset=FAIL event_len=0 event=
```

Result: **not usable yet**. Patch download and the coarse ready path progress
far enough for `cyw43_arch_init()` to return, but Bluetooth shared-bus HCI is
not initialized. This is consistent with retaining UART/Murata transport
configuration inside `BRCMcfgD`; it is evidence against treating the HCD
payload as a complete drop-in shared-bus image.

UF2: `build/experimental-0071/cyw43439_pico_test.uf2`

SHA-256: `E3CB121AC613DAD092DC1AD5CB847136AE81354E93AB09064282E9C93E47219A`

## Final board state

The stock `.0065` recovery image was restored after the `.0071` experiment.
COM16 again reported `CYW43_INIT PASS` and `HCI_RESET PASS`.

## USB Bluetooth dongle

The final stock `.0065` dongle image enumerated as:

- `Generic Bluetooth Adapter`, Status OK
- `Microsoft Bluetooth Enumerator`, Status OK
- `Microsoft Bluetooth LE Enumerator`, Status OK
- USB CDC diagnostics on COM17

A five-second, 44.1 kHz stereo tone was sent directly to the paired RACE TX10
A2DP waveOut endpoint after the final activity-LED change. Final counters were:

```text
STATUS radio=OK usb=1 cmd=73/73 acl_host=1100/1100 evt=646/646 acl_dev=48/48 drops=0 errors=0
```

Windows also exposed the RACE TX10 AVRCP transports and stereo Headphones
endpoint. Pixel 7 appeared through both Classic and BLE enumeration, confirming
that both host paths are alive. Bluetooth HID Classic and HID-over-GATT use
those same transparent HCI/ACL paths; no separate local USB HID interface is
needed or desirable for an adapter.

Final UF2:

`build/dongle-stock-0065/cyw43439_usb_dongle.uf2`

SHA-256:

`EDE1E710D87DAD657C1AC0451C9D8F8FB209030210CACCF748479630903570CA`
