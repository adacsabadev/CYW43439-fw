# Pico 2 W USB Bluetooth dongle

`cyw43439_usb_dongle` exposes the Pico 2 W CYW43439 controller as a standard
USB Bluetooth Primary Controller. Windows owns the Bluetooth host stack and
profiles; firmware transports HCI commands, events and ACL data between USB
and the controller.

## Supported host functionality

- Bluetooth Classic discovery, pairing and ACL links
- Bluetooth Low Energy through the Microsoft Bluetooth LE Enumerator
- A2DP stereo playback and AVRCP through the Windows Bluetooth stack
- Bluetooth Classic HID keyboards, mice and gamepads
- BLE HID-over-GATT devices
- RFCOMM and other Windows-supported profiles

Bluetooth HID does not require a separate USB HID interface on the Pico. Once
paired, Windows creates the appropriate HID device for the remote peripheral.
Presenting an additional local USB keyboard/mouse interface would misidentify
the adapter itself and would not add Bluetooth HID capability.

The stock CYW43439 `.0065` firmware has the previously documented SCO/eSCO
voice limitation. A2DP stereo uses ACL and is unaffected. Hands-free microphone
support is therefore not claimed.

## Build

The dongle requires `patches/pico-sdk-cybt-propagate-write-errors.patch`
applied to `.tools/pico-sdk`. Stock Pico SDK `cyw43_btbus_write()` always
returns 0, which hides controller write failures. `build.ps1` refuses to build
against an unpatched SDK.

```powershell
git -C ..\.tools\pico-sdk apply ..\..\patches\pico-sdk-cybt-propagate-write-errors.patch
```

```powershell
cd .\hardware-test
.\build.ps1 -Dongle
```

Output:

`build/dongle-stock-0065/cyw43439_usb_dongle.uf2`

The checked-in, hardware-validated `.0065` baseline UF2 is
`hardware-test/firmware/cyw43439_usb_dongle_stock_0065.uf2` (SHA-256
`5FCF37645BB391533F08F33FC9B071F965DB5CADFFB34CDEAFEEBED91FEA04FD`).
This preserves a directly flashable baseline independently of the ignored
build directory.

## Interfaces

- USB Bluetooth HCI class: Windows `Generic Bluetooth Adapter`
- USB CDC diagnostics: commands `status`, `events`, and `bootsel`
- Bluetooth voice alternate interface: required by the Windows USB Bluetooth
  class driver; SCO forwarding is intentionally not implemented

The CYW43-controlled onboard LED emits 35 ms traffic pulses separated by a
minimum 35 ms dark interval. Commands, events and ACL traffic all count as
activity, so sustained A2DP produces a visible blink rather than a solid LED.

## Controller write flow control

Host commands and ACL packets are queued and written to the controller's
4 KiB host-to-BT shared-bus ring. `CYBT_ERR_QUEUE_FULL` leaves the packet at
the queue head and retries it on the next loop pass. Any other write error
drops that packet and increments `errors`, so one failed packet cannot block
the bridge.

`status` prints a second line:

```text
FLOW backpressure=<stall episodes> host_cmd_q=<n> host_acl_q=<n> dev_evt_q=<n> dev_acl_q=<n>
```

`backpressure` counts stall episodes (transitions into a full ring), not
individual retries.

## Live validation

The adapter enumerated with Status OK alongside the Microsoft Bluetooth and
Bluetooth LE enumerators. A direct 44.1 kHz stereo waveOut stream targeted the
paired RACE TX10 A2DP endpoint for ten seconds. Bridge counters changed from:

```text
acl_host=197/197 evt=190/190 acl_dev=44/44 drops=0 errors=0
```

to:

```text
acl_host=1100/1100 evt=644/644 acl_dev=48/48 drops=0 errors=0
```

All 903 additional outbound ACL packets reached the controller. No queue drop
or controller transport error occurred. Windows reported both RACE TX10 AVRCP
transports and the stereo Headphones endpoint as Status OK.

That run predates the SDK write-error patch, so `errors=0` could not observe
shared-bus write failures. With the patch and backpressure handling, a
15-second 660 Hz stereo stream to the same endpoint moved the counters from:

```text
cmd=69/69 acl_host=60/60 evt=119/119 acl_dev=54/54 drops=0 errors=0
FLOW backpressure=0 host_cmd_q=0 host_acl_q=0 dev_evt_q=0 dev_acl_q=0
```

to:

```text
cmd=72/72 acl_host=760/760 evt=476/476 acl_dev=56/56 drops=0 errors=0
FLOW backpressure=0 host_cmd_q=0 host_acl_q=0 dev_evt_q=0 dev_acl_q=0
```

All 700 additional ACL packets were accepted by the controller with real
error reporting enabled. Windows HCI flow control kept the controller ring
from filling, so the `CYBT_ERR_QUEUE_FULL` retry path was not exercised.
