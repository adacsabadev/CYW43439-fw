# CYW43439 Bluetooth firmware lab

This repository compares the Raspberry Pi Pico W/Pico 2 W CYW43439 Bluetooth
PatchRAM image with a newer Murata Type-1YN image. Everything required for the
analysis stays under this project root.

## Inputs

- `firmware/cyw43_btfw_43439_0065_pico.h`: Pico SDK gSPI/SDIO container,
  version `001.003.016.0065.0000`.
- `firmware/CYW4343A2_001.003.016.0071.0017.1YN.hcd`: Murata Type-1YN HCD
  command stream, version `001.003.016.0071.0017`.

The `.hcd` file is not a drop-in replacement for the Pico header. It contains
HCI vendor commands intended for the UART download path. The Pico file contains
a version string followed by compact address records consumed by the gSPI
transport. No generated firmware should be flashed until the address mapping
and transport-specific configuration records are understood and validated.

## Reproduce the structural analysis

```powershell
python .\tools\analyze_firmware.py `
  --pico .\firmware\cyw43_btfw_43439_0065_pico.h `
  --hcd .\firmware\CYW4343A2_001.003.016.0071.0017.1YN.hcd `
  --output .\analysis\firmware.json
```

The next milestone is to establish the exact mapping between HCD `Write_RAM`
addresses and Pico record `(address_type, address)` pairs using the Pico SDK
loader source. That mapping is now established: Pico records are compact
Intel-HEX-style records and preserve the HCD addresses exactly.

## Generate the experimental `.0071` Pico header

```powershell
python .\tools\convert_hcd_to_pico.py `
  --hcd .\firmware\CYW4343A2_001.003.016.0071.0017.1YN.hcd `
  --activation-template .\firmware\cyw43_btfw_43439_0065_pico.h `
  --output .\generated\cyw43_btfw_43439_0071_experimental.h
```

The converter verifies that all 29 HCD `Write_RAM` payloads round-trip with
identical addresses and bytes. It then appends the two activation writes used
by both public Pico gSPI images examined (`.0031` and `.0065`):

- `0x2038d4 <- 0x0021e000` (PatchRAM base pointer)
- `0x204164 <- ed f7 05 00` (ROM activation hook)

The stability of these writes across two Pico firmware generations, identical
CYW4343A2 silicon, and the unchanged `.0071` patch base provide strong evidence
for the conversion. It remains an experimental Murata-UART-to-Pico-gSPI port;
live validation must start with boot, HCI reset, version, and basic LE/Classic
tests before attempting SCO.

## Static reverse-engineering artifacts

```powershell
python .\tools\extract_re.py `
  --pico .\firmware\cyw43_btfw_43439_0065_pico.h `
  --hcd .\firmware\CYW4343A2_001.003.016.0071.0017.1YN.hcd `
  --output .\re-output
```

This produces address-named binary segments, string inventories, SHA-256
manifests and ARM Thumb listings using `arm-none-eabi-objdump`. Configuration
segments and the executable patch at `0x000d0200` remain separate so a reverse
engineering tool can load each at its real address without filling the large
address gaps.

## Independent Pico 2 W hardware test

`hardware-test/` is a clean diagnostic image independent of the dongle code.
It boots with the stock Pico SDK `.0065` Bluetooth patch, exposes USB CDC,
initializes CYW43439, sends a raw HCI Reset and requires the matching Command
Complete event before reporting `HCI_RESET PASS`.

```powershell
cd .\hardware-test
.\build.ps1
```

Serial commands:

- `status`: radio initialization and last HCI event
- `hci-reset`: repeat the controller reset probe
- `led-on`, `led-off`: verify the CYW43-controlled onboard LED
- `bootsel`: reboot into ROM USB BOOTSEL without using the physical button

The firmware prints `CYW43439 PICO2W TEST v1` and a status line every five
seconds. A working board must report both `CYW43_INIT PASS` and
`HCI_RESET PASS`; USB enumeration alone proves only the RP2350/flash/USB path.

The same project also contains the tested USB Bluetooth dongle target. See
`hardware-test/DONGLE.md` and build it with `hardware-test/build.ps1 -Dongle`.
