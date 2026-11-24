# CYW43439 firmware reverse-engineering status

## Inputs and provenance

| Image | Container | Payload SHA-256 |
|---|---|---|
| Pico SDK `.0065.0000` | Compact shared-bus/Intel-HEX-style C array | `d974384d0aa8124d30084f30d13519a3ed3b9f759f7ddd6a34ef3dcf1441bcf7` |
| Murata Type-1YN `.0071.0017` | Broadcom HCD command stream | `429fb4766443c96e1ab96ac7eb65c2566349a3ee28d3af118645ed935e0b61c3` |

## Address map

| Address | `.0065` | `.0071` | Interpretation |
|---:|---:|---:|---|
| `0x000d0200` | 3,472 bytes | 3,472 bytes | ARM Thumb PatchRAM code/data |
| `0x0021e000` | 66 bytes | 66 bytes | `BRCMcfgS` static configuration |
| `0x0021f000` | 3,200 bytes | 3,231 bytes | `BRCMcfgD` dynamic configuration |
| `0x002038d4` | 4 bytes | HCD launch semantics | Pico PatchRAM base activation write |
| `0x00204164` | 4 bytes | HCD launch semantics | Pico ROM activation hook |

The `.0065` and `.0071` executable segments have equal size. Direct offsets
match for 428 of 3,472 bytes (12.3%), but sequence alignment reports 89.2%
shared content across 171 matching blocks. Most apparent byte displacement is
caused by inserted/reordered code and changed PC-relative branches/literals.

## Established container conversion

The Pico loader source proves that its records retain Intel HEX semantics:
big-endian 16-bit record addresses plus extended-address records. HCD
`Write_RAM` addresses therefore translate without address relocation. The
converter round-trips all 29 `.0071` writes byte-for-byte and appends the two
activation writes that are identical in public Pico `.0031` and `.0065`
images. The result builds successfully, but has not been hardware-tested.

## Current artifacts

- `tools/analyze_firmware.py`: strict parsers and JSON inventory.
- `tools/convert_hcd_to_pico.py`: validated experimental HCD-to-Pico converter.
- `tools/extract_re.py`: real-address binary extraction, strings and Thumb
  listings.
- `re-output/*/manifest.json`: generated address maps and hashes.
- `re-output/*/*.thumb.lst`: generated disassembly at the correct virtual
  address.

## Next reverse-engineering targets

1. Parse `BRCMcfgS`/`BRCMcfgD` TLVs and distinguish UART/SDIO transport fields
   from radio patch metadata.
2. Align Thumb functions using branch targets and literal pools rather than raw
   file offsets.
3. Identify code unique to `.0071`, then search for SCO/eSCO setup, PCM routing,
   packet-status and connection-state changes.
4. Resolve ROM calls by comparing common call sites. ROM symbols remain
   `unknown` until corroborated by a symbol map, SDK metadata, or live traces.
5. Import the two `0x000d0200` binaries into Ghidra as ARM little-endian Cortex-M
   Thumb images when a project-local Ghidra distribution is installed.

## Hardware boundary

No `.0071` image has been flashed. The Pico was unavailable because the dongle
work damaged its current boot/power behavior. Static work does not depend on
the board and can proceed independently.
