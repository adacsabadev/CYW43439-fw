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

### Backpressure build (SDK write-error patch)

Rebuilt against the patched Pico SDK 2.3.1 so controller write failures
are reported. The bridge now retries on `CYBT_ERR_QUEUE_FULL` and drops on
other errors. Re-enumerated with the Generic Bluetooth Adapter and both
Microsoft enumerators Status OK on COM17. A 15-second A2DP stream to the RACE
TX10 finished with:

```text
STATUS radio=OK usb=1 cmd=72/72 acl_host=760/760 evt=476/476 acl_dev=56/56 drops=0 errors=0
FLOW backpressure=0 host_cmd_q=0 host_acl_q=0 dev_evt_q=0 dev_acl_q=0
```

Checked-in baseline UF2: `hardware-test/firmware/cyw43439_usb_dongle_stock_0065.uf2`
(the earlier image remains in `build/dongle-stock-0065.pre-backpressure/`)

SHA-256:

`5FCF37645BB391533F08F33FC9B071F965DB5CADFFB34CDEAFEEBED91FEA04FD`

## Converted Murata `.0071` retest (radio-fw-0071 rebuild)

Test date: 2026-11-25, same board (`61EDF42ACD25F7A0`). The `.0071` test image
was rebuilt from a clean checkout on branch `radio-fw-0071` and flashed via
`picotool load -x`. USB CDC enumerated as COM16. The result reproduces the
original failure exactly, including after a manual `hci-reset` retry:

```text
STATUS radio_init=0 radio=OK hci_write=180 hci_reset=FAIL event_len=0 event=
HCI_RESET sent result=180
```

This confirms the failure is deterministic and not a build or flash artifact.
The shared-bus HCI bring-up suspect (`BRCMcfgD` UART transport configuration)
remains unchanged.

UF2: `build/experimental-0071/cyw43439_pico_test.uf2`

SHA-256: `1251EED9332C9C0247C4BD529CD5E4C44AC1EA770258D1C38CE94F7B730B53FD`

The board was then restored to the checked-in stock `.0065` dongle baseline
(`firmware/cyw43439_usb_dongle_stock_0065.uf2`). It re-enumerated as the
Generic Bluetooth Adapter with CDC on COM17 and immediately resumed live HCI
traffic with the Windows host:

```text
STATUS radio=OK usb=1 cmd=70/70 acl_host=44/44 evt=104/104 acl_dev=43/43 drops=0 errors=0
FLOW backpressure=0 host_cmd_q=0 host_acl_q=0 dev_evt_q=0 dev_acl_q=0
```

## Hybrid `.0071` patch + `.0065` config

Test date: 2026-11-25, same board. `build.ps1 -Hybrid0071` builds the `.0071`
executable patch combined with the byte-identical `.0065` `BRCMcfgS`/`BRCMcfgD`
sections (verified segment-for-segment against the extracted `.0065` binaries,
including the 64-byte cfgD trailer). Result: identical failure.

```text
STATUS radio_init=0 radio=OK hci_write=180 hci_reset=FAIL event_len=0 event=
```

UF2: `build/hybrid-0071/cyw43439_pico_test.uf2`

SHA-256: `68F08A2A92499A927EA2E37027006B246C9AC75C1E8E2E65CD793BDBC711EC59`

This falsified the plain "swap in shared-bus config" hypothesis and pointed at
the `BRCMcfgD` tail entries, which decode as per-chunk patch descriptors
`[u32 address][u32 length][SHA-256]` bound to the exact download chunking.

## One-byte `BRCMcfgD` tamper test on `.0065`

`tools/patch_container_byte.py` changed exactly one byte of the known-good
`.0065` image, inside the cfgD build-identifier string (`RPI` to `RPJ`,
container offset 0xC0). Everything else, including record framing, chunking
and the patch, stayed byte-identical. Result: the previously passing image now
fails exactly like the `.0071` conversions:

```text
STATUS radio_init=0 radio=OK hci_write=180 hci_reset=FAIL event_len=0 event=
```

UF2: `build/tamper-0065/cyw43439_pico_test.uf2`

Conclusion: the CYW43439 BT firmware verifies the `BRCMcfgD` body against its
64-byte trailing signature before signalling shared-bus readiness. Any locally
modified configuration section is rejected, so spliced or re-signed configs are
not achievable without the vendor signing key.

## Final board state

The stock `.0065` dongle baseline was restored and verified live after the
hybrid and tamper experiments: Generic Bluetooth Adapter Status OK, CDC on
COM17, active HCI traffic with the Windows host, `drops=0 errors=0`.
