#!/usr/bin/env python3
"""Parse and compare Pico CYW43 BT patch records with Broadcom HCD commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_c_array(path: Path) -> bytes:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"cyw43_btfw_43439\[\].*?=\s*\{(.*?)\};", text, re.S)
    if not match:
        raise ValueError(f"could not find cyw43_btfw_43439 array in {path}")
    return bytes(int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{2})", match.group(1)))


def parse_pico(data: bytes) -> dict:
    offset = 0
    version_length = data[offset]
    offset += 1
    version_raw = data[offset : offset + version_length]
    offset += version_length
    record_count = data[offset]
    offset += 1
    records = []
    for index in range(record_count):
        length = data[offset]
        # These compact records retain the big-endian address field used by
        # Intel HEX. The payload itself is binary and is not byte-swapped.
        address = int.from_bytes(data[offset + 1 : offset + 3], "big")
        address_type = data[offset + 3]
        payload = data[offset + 4 : offset + 4 + length]
        records.append(
            {
                "index": index,
                "length": length,
                "address": address,
                "address_type": address_type,
                "payload_hex": payload.hex(),
            }
        )
        offset += 4 + length
    if offset != len(data):
        raise ValueError(f"Pico container has {len(data) - offset} unparsed bytes")
    return {
        "format": "pico-record-container",
        "byte_length": len(data),
        "sha256": sha256(data),
        "version": version_raw.rstrip(b"\0").decode("ascii", errors="replace"),
        "record_count": record_count,
        "records": records,
    }


def parse_hcd(data: bytes) -> dict:
    offset = 0
    commands = []
    while offset < len(data):
        if len(data) - offset < 3:
            raise ValueError(f"truncated HCD command header at {offset:#x}")
        opcode, length = struct.unpack_from("<HB", data, offset)
        payload = data[offset + 3 : offset + 3 + length]
        if len(payload) != length:
            raise ValueError(f"truncated HCD command payload at {offset:#x}")
        entry = {
            "index": len(commands),
            "file_offset": offset,
            "opcode": f"0x{opcode:04x}",
            "length": length,
            "payload_hex": payload.hex(),
        }
        if opcode == 0xFC4C and length >= 4:
            entry["write_address"] = int.from_bytes(payload[:4], "little")
            entry["write_length"] = length - 4
            entry["write_data_hex"] = payload[4:].hex()
        commands.append(entry)
        offset += 3 + length
    return {
        "format": "broadcom-hcd",
        "byte_length": len(data),
        "sha256": sha256(data),
        "command_count": len(commands),
        "opcode_histogram": {
            opcode: sum(command["opcode"] == opcode for command in commands)
            for opcode in sorted({command["opcode"] for command in commands})
        },
        "commands": commands,
    }


def summary(pico: dict, hcd: dict) -> dict:
    pico_lengths = [record["length"] for record in pico["records"]]
    hcd_writes = [command for command in hcd["commands"] if command["opcode"] == "0xfc4c"]
    return {
        "pico": {
            key: pico[key]
            for key in ("byte_length", "sha256", "version", "record_count")
        }
        | {
            "record_length_min": min(pico_lengths),
            "record_length_max": max(pico_lengths),
            "address_types": sorted({record["address_type"] for record in pico["records"]}),
        },
        "hcd": {
            key: hcd[key]
            for key in ("byte_length", "sha256", "command_count", "opcode_histogram")
        }
        | {
            "write_ram_count": len(hcd_writes),
            "write_ram_bytes": sum(command["write_length"] for command in hcd_writes),
            "write_address_min": min(command["write_address"] for command in hcd_writes),
            "write_address_max": max(command["write_address"] for command in hcd_writes),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pico", type=Path, required=True)
    parser.add_argument("--hcd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    pico = parse_pico(extract_c_array(args.pico))
    hcd = parse_hcd(args.hcd.read_bytes())
    result = {"summary": summary(pico, hcd), "pico": pico, "hcd": hcd}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
