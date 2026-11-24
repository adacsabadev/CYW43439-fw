#!/usr/bin/env python3
"""Create address-preserving RE artifacts from Pico and Broadcom HCD patches."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from analyze_firmware import extract_c_array, parse_hcd, parse_pico
from convert_hcd_to_pico import resolved_writes


def printable_strings(data: bytes, minimum: int = 4) -> list[dict]:
    results = []
    for match in re.finditer(rb"[\x20-\x7e]{%d,}" % minimum, data):
        results.append({"offset": match.start(), "text": match.group().decode("ascii")})
    return results


def contiguous_segments(writes: list[tuple[int, bytes]]) -> list[tuple[int, bytes]]:
    segments: list[tuple[int, bytearray]] = []
    for address, payload in writes:
        if segments and segments[-1][0] + len(segments[-1][1]) == address:
            segments[-1][1].extend(payload)
        else:
            segments.append((address, bytearray(payload)))
    return [(address, bytes(data)) for address, data in segments]


def classify(address: int, data: bytes) -> str:
    if data.startswith(b"BRCMcfgS"):
        return "static_config"
    if data.startswith(b"BRCMcfgD"):
        return "dynamic_config"
    if address >> 16 == 0x0D:
        return "thumb_patch"
    if len(data) == 4 and address >> 16 == 0x20:
        return "activation"
    return "unknown"


def disassemble(objdump: str, binary: Path, address: int, output: Path) -> None:
    command = [
        objdump,
        "-D",
        "-b", "binary",
        "-m", "arm",
        "-M", "force-thumb",
        f"--adjust-vma=0x{address:x}",
        str(binary),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    output.write_text(result.stdout, encoding="utf-8", newline="\n")


def emit(name: str, writes: list[tuple[int, bytes]], root: Path, objdump: str | None) -> dict:
    target = root / name
    target.mkdir(parents=True, exist_ok=True)
    manifest = {"image": name, "segments": []}
    for index, (address, data) in enumerate(contiguous_segments(writes)):
        kind = classify(address, data)
        stem = f"{index:02d}_{address:08x}_{kind}"
        binary = target / f"{stem}.bin"
        binary.write_bytes(data)
        entry = {
            "index": index,
            "address": address,
            "end_address_exclusive": address + len(data),
            "length": len(data),
            "classification": kind,
            "sha256": hashlib.sha256(data).hexdigest(),
            "file": binary.name,
            "strings": printable_strings(data),
        }
        if objdump and kind == "thumb_patch":
            listing = target / f"{stem}.thumb.lst"
            disassemble(objdump, binary, address, listing)
            entry["disassembly"] = listing.name
        manifest["segments"].append(entry)
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pico", type=Path, required=True)
    parser.add_argument("--hcd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    pico = parse_pico(extract_c_array(args.pico))
    hcd = parse_hcd(args.hcd.read_bytes())
    pico_writes = resolved_writes(pico)
    hcd_writes = [
        (command["write_address"], bytes.fromhex(command["write_data_hex"]))
        for command in hcd["commands"]
        if command["opcode"] == "0xfc4c"
    ]
    objdump = shutil.which("arm-none-eabi-objdump")
    manifests = {
        "0065_pico": emit("0065_pico", pico_writes, args.output, objdump),
        "0071_murata": emit("0071_murata", hcd_writes, args.output, objdump),
    }
    summary = {
        name: [
            {key: segment[key] for key in ("address", "length", "classification", "sha256")}
            for segment in manifest["segments"]
        ]
        for name, manifest in manifests.items()
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
