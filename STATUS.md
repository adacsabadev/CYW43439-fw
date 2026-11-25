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

## Config section structure (established 2026-11-25)

`BRCMcfgS`/`BRCMcfgD` layout: 8-byte magic, 4 zero bytes, little-endian u32
body length, then TLV entries `[u16 id LE][u8 len][value]` terminated by
`0xFE`. `BRCMcfgD` additionally carries a 64-byte trailing signature
(`dl_signed` in the `.0065` version string).

- cfgS entry `0x0300`: default BD_ADDR (the only cfgS difference between
  images).
- cfgD entry `0x0303`: build identifier — `SDIO 37_4M wlbga_BU RPI` in `.0065`
  versus `UART 4343A2 wlbga_BU Murata Type-1YN-0071` in `.0071`.
- cfgD tail entries `0x0133` (40 bytes each): per-chunk patch descriptors
  `[u32 address][u32 length][SHA-256]` matching the exact download chunk
  layout (251-byte chunks in `.0065`, 240-byte in the `.0071` HCD).

Tools: `tools/parse_config.py` (TLV parse/diff, best-effort for large
entries), `tools/patch_container_byte.py` (single-byte container tamper),
`convert_hcd_to_pico.py --config-from-template` (hybrid builder, also exposed
as `hardware-test/build.ps1 -Hybrid0071`).

## Hardware boundary

On 2026-11-25 the RP2350 was recovered through ROM BOOTSEL and flashed with the
independent `hardware-test` stock `.0065` image. Windows enumerated USB CDC as
COM16. Live output proved both CYW43 initialization and controller HCI:

```text
STATUS radio_init=0 radio=OK hci_write=0 hci_reset=PASS event_len=6 event=0e0401030c00
```

This establishes a known-good recovery baseline independent of the dongle
application.

The converted `.0071` image was then tested with the identical application.
USB CDC enumerated, and `cyw43_arch_init()` returned zero, but the first HCI
Reset write returned `180` (`0xB4`, `CYBT_ERR_HCI_INIT_FAILED`) with no event:

```text
STATUS radio_init=0 radio=OK hci_write=180 hci_reset=FAIL event_len=0 event=
```

The board was restored to stock `.0065` and reconfirmed passing. This narrowed the `.0071` problem to shared-bus runtime
initialization/configuration rather than RP2350 boot, USB, the HCD address
translation, or a permanently damaged board.

Two follow-up experiments on 2026-11-25 resolved the cause (details in
`hardware-test/RESULTS.md`):

1. A hybrid image (`.0071` patch + byte-identical `.0065` config sections)
   failed identically, ruling out plain config substitution.
2. A single-byte tamper inside the signed `BRCMcfgD` body of the known-good
   `.0065` image reproduced the identical failure, proving the BT firmware
   verifies the cfgD signature before signalling shared-bus readiness.

Conclusion: the `.0071` HCD-to-shared-bus port is blocked by firmware
signature enforcement. `BRCMcfgD` is signed over a body that both names the
transport (`UART` vs `SDIO`) and hash-binds the exact patch chunk layout, so
no locally modified combination of `.0071` code and shared-bus configuration
can pass verification without the vendor signing key. The practical paths to
SCO/eSCO support are a vendor-signed shared-bus `.0071` image, or host-side
workarounds that avoid controller SCO entirely.
