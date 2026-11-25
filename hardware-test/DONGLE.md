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

```powershell
cd .\hardware-test
.\build.ps1 -Dongle
```

Output:

`build/dongle-stock-0065/cyw43439_usb_dongle.uf2`

## Interfaces

- USB Bluetooth HCI class: Windows `Generic Bluetooth Adapter`
- USB CDC diagnostics: commands `status`, `events`, and `bootsel`
- Bluetooth voice alternate interface: required by the Windows USB Bluetooth
  class driver; SCO forwarding is intentionally not implemented

The CYW43-controlled onboard LED emits 35 ms traffic pulses separated by a
minimum 35 ms dark interval. Commands, events and ACL traffic all count as
activity, so sustained A2DP produces a visible blink rather than a solid LED.

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
