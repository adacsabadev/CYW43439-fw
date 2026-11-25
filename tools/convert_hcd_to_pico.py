#!/usr/bin/env python3
"""Convert a CYW4343A2 HCD patch into the Pico shared-bus record container.

The HCD Write_RAM payloads translate directly to Intel-HEX-style Pico records.
HCD Launch_RAM cannot be issued before the Bluetooth shared bus is running, so
the converter copies the two activation writes from a known-good Pico image.
This is experimental and deliberately requires that activation template.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from analyze_firmware import extract_c_array, parse_hcd, parse_pico


def resolved_writes(pico: dict) -> list[tuple[int, bytes]]:
    high = 0
    mode = None
    writes = []
    for record in pico["records"]:
        payload = bytes.fromhex(record["payload_hex"])
        kind = record["address_type"]
        if kind == 4:
            high = int.from_bytes(payload, "big")
            mode = 4
        elif kind == 2:
            high = int.from_bytes(payload, "big")
            mode = 2
        elif kind == 5:
            high = int.from_bytes(payload, "big")
            mode = 5
        elif kind == 0:
            low = record["address"]
            address = low + (high << 16 if mode == 4 else high << 4 if mode == 2 else high)
            writes.append((address, payload))
    return writes


def record(address: int, kind: int, payload: bytes) -> bytes:
    if len(payload) > 255:
        raise ValueError("record payload exceeds 255 bytes")
    return bytes([len(payload)]) + address.to_bytes(2, "big") + bytes([kind]) + payload


CONFIG_BASE = 0x21E000
CONFIG_LIMIT = 0x220000


def make_container(
    hcd: dict, template: dict, version: str, config_from_template: bool
) -> tuple[bytes, list[tuple[int, bytes]], list[tuple[int, bytes]]]:
    hcd_writes = [
        (command["write_address"], bytes.fromhex(command["write_data_hex"]))
        for command in hcd["commands"]
        if command["opcode"] == "0xfc4c"
    ]
    launches = [command for command in hcd["commands"] if command["opcode"] == "0xfc4e"]
    if len(launches) != 1 or launches[0]["payload_hex"] != "ffffffff":
        raise ValueError("expected one Launch_RAM(0xffffffff) command")

    # Known Pico images end with two 4-byte activation writes in 0x20xxxx.
    # They are stable across the public .0031 and .0065 gSPI images.
    template_writes = resolved_writes(template)
    activation = [(address, data) for address, data in template_writes if address >> 16 == 0x20 and len(data) == 4]
    if activation != [
        (0x2038D4, bytes.fromhex("00e02100")),
        (0x204164, bytes.fromhex("edf70500")),
    ]:
        raise ValueError(f"unexpected activation template: {activation!r}")

    if config_from_template:
        # Hybrid: keep the HCD executable patch but take both BRCMcfgS/BRCMcfgD
        # sections from the shared-bus template, replacing the HCD's
        # UART-transport configuration at its original position in the stream.
        template_config = [
            (address, data)
            for address, data in template_writes
            if CONFIG_BASE <= address < CONFIG_LIMIT
        ]
        if not template_config:
            raise ValueError("template contains no config-region writes")
        writes = []
        replaced = False
        for address, data in hcd_writes:
            if CONFIG_BASE <= address < CONFIG_LIMIT:
                if not replaced:
                    writes.extend(template_config)
                    replaced = True
                continue
            writes.append((address, data))
        if not replaced:
            raise ValueError("HCD contains no config-region writes to replace")
        writes.extend(activation)
    else:
        writes = hcd_writes + activation

    records = []
    current_high = None
    for address, payload in writes:
        high = address >> 16
        if high != current_high:
            records.append(record(0, 4, high.to_bytes(2, "big")))
            current_high = high
        records.append(record(address & 0xFFFF, 0, payload))
    records.append(record(0, 1, b""))
    if len(records) > 255:
        raise ValueError("container has too many records")

    version_bytes = version.encode("ascii") + b"\0"
    if len(version_bytes) > 255:
        raise ValueError("version string is too long")
    container = bytes([len(version_bytes)]) + version_bytes + bytes([len(records)]) + b"".join(records)
    return container, activation, writes


def render_header(container: bytes) -> str:
    lines = [
        "// EXPERIMENTAL: Murata UART HCD adapted for CYW43439 shared-bus download.",
        "// Activation records are inherited from the public Pico .0065 image.",
        "const unsigned char cyw43_btfw_43439[] CYW43_RESOURCE_ATTRIBUTE = {",
    ]
    for offset in range(0, len(container), 12):
        chunk = container[offset : offset + 12]
        lines.append("  " + ", ".join(f"0x{byte:02x}" for byte in chunk) + ",")
    lines.extend(
        [
            "};",
            f"const unsigned int cyw43_btfw_43439_len = {len(container)};",
            "",
            "const uint8_t *btfw_data = &cyw43_btfw_43439[0];",
            "const size_t btfw_len = cyw43_btfw_43439_len;",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hcd", type=Path, required=True)
    parser.add_argument("--activation-template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--config-from-template",
        action="store_true",
        help="replace the HCD BRCMcfgS/BRCMcfgD writes with the template's shared-bus config sections",
    )
    parser.add_argument("--version", default=None)
    args = parser.parse_args()
    if args.version is None:
        args.version = (
            "CYW4343A2_001.003.016.0071.0017_Murata_1YN_HCD_to_SDIO_HYBRID_0065_CFG"
            if args.config_from_template
            else "CYW4343A2_001.003.016.0071.0017_Murata_1YN_HCD_to_SDIO_EXPERIMENTAL"
        )

    hcd = parse_hcd(args.hcd.read_bytes())
    template = parse_pico(extract_c_array(args.activation_template))
    container, activation, expected = make_container(
        hcd, template, args.version, args.config_from_template
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_header(container), encoding="utf-8", newline="\n")

    # Round-trip validation: the generated records must resolve to exactly the
    # write list the container was built from.
    generated = parse_pico(extract_c_array(args.output))
    actual = resolved_writes(generated)
    if actual != expected:
        raise RuntimeError("round-trip validation failed")
    print(f"generated {args.output} ({len(container)} bytes, {generated['record_count']} records)")
    patch_writes = sum(1 for address, _ in expected if address < CONFIG_BASE and address >> 16 != 0x20)
    config_writes = sum(1 for address, _ in expected if CONFIG_BASE <= address < CONFIG_LIMIT)
    source = "template (.0065 shared-bus)" if args.config_from_template else "HCD"
    print(
        f"validated {patch_writes} patch writes from HCD, {config_writes} config writes from {source},"
        f" plus {len(activation)} known Pico activation writes"
    )


if __name__ == "__main__":
    main()
