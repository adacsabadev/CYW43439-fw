#!/usr/bin/env python3
"""Parse and diff BRCMcfgS/BRCMcfgD configuration sections.

Section layout (observed in both the Pico `.0065` and Murata `.0071` images):

- 8-byte magic ``BRCMcfgS`` or ``BRCMcfgD``
- 4 zero bytes
- little-endian 32-bit body length
- body: repeated TLV entries ``[u16 id LE][u8 len][len bytes]`` terminated by
  a first byte of ``0xFE`` (followed by zero padding to the declared length)
- ``BRCMcfgD`` only: a trailing 64-byte signature after the declared body
  (the `.0065` version string advertises ``dl_signed``)

Entry ``0x0300`` in ``BRCMcfgS`` holds the default BD_ADDR. Entry ``0x0303``
in ``BRCMcfgD`` holds the ASCII build identifier, which names the transport
(``SDIO`` for the Pico image, ``UART`` for the Murata image).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

MAGICS = (b"BRCMcfgS", b"BRCMcfgD")


@dataclass
class Section:
    magic: str
    body_length: int
    entries: list[tuple[int, bytes]]
    padding: bytes
    signature: bytes


def parse_section(data: bytes) -> Section:
    if data[:8] not in MAGICS:
        raise ValueError(f"unknown config magic: {data[:8]!r}")
    if data[8:12] != b"\0\0\0\0":
        raise ValueError("nonzero reserved field")
    body_length = int.from_bytes(data[12:16], "little")
    body = data[16 : 16 + body_length]
    if len(body) != body_length:
        raise ValueError("declared body length exceeds container")
    signature = data[16 + body_length :]
    if len(signature) not in (0, 64):
        raise ValueError(f"unexpected trailer length {len(signature)}")

    # Best-effort walk. Some large entries appear to use an encoding this
    # tool does not understand yet, so a desync is reported, not fatal.
    entries = []
    i = 0
    while i < len(body):
        if body[i] == 0xFE:
            break
        item_id = int.from_bytes(body[i : i + 2], "little")
        length = body[i + 2] if i + 3 <= len(body) else len(body)
        value = body[i + 3 : i + 3 + length]
        if len(value) != length:
            entries.append((-1, body[i:]))
            i = len(body)
            break
        entries.append((item_id, value))
        i += 3 + length
    padding = body[i + 1 :] if i < len(body) else b""
    if padding.strip(b"\0"):
        entries.append((-2, padding))
        padding = b""
    return Section(data[:8].decode(), body_length, entries, padding, signature)


def describe(value: bytes) -> str:
    text = value.rstrip(b"\0")
    if text and all(32 <= byte < 127 for byte in text):
        return f"{value.hex()}  {text.decode()!r}"
    return value.hex()


def entry_name(item_id: int) -> str:
    if item_id == -1:
        return "desynced raw tail"
    if item_id == -2:
        return "nonzero post-terminator data"
    return f"id 0x{item_id:04x}"


def diff(name_a: str, a: Section, name_b: str, b: Section) -> None:
    print(f"== {a.magic}: {name_a} ({len(a.entries)} entries) vs {name_b} ({len(b.entries)} entries)")
    ids = []
    for item_id, _ in a.entries + b.entries:
        if item_id not in ids:
            ids.append(item_id)
    map_a = {item_id: value for item_id, value in a.entries}
    map_b = {item_id: value for item_id, value in b.entries}
    if len(map_a) != len(a.entries) or len(map_b) != len(b.entries):
        print("  (duplicate ids present; falling back to positional diff)")
        for index in range(max(len(a.entries), len(b.entries))):
            ea = a.entries[index] if index < len(a.entries) else None
            eb = b.entries[index] if index < len(b.entries) else None
            if ea == eb:
                continue
            print(f"  entry {index}:")
            for name, e in ((name_a, ea), (name_b, eb)):
                if e is None:
                    print(f"    {name}: absent")
                else:
                    print(f"    {name}: {entry_name(e[0])} len={len(e[1])} {describe(e[1][:48])}")
        return
    for item_id in ids:
        va, vb = map_a.get(item_id), map_b.get(item_id)
        if va == vb:
            continue
        print(f"  {entry_name(item_id)}:")
        print(f"    {name_a}: " + ("absent" if va is None else f"len={len(va)} {describe(va[:48])}"))
        print(f"    {name_b}: " + ("absent" if vb is None else f"len={len(vb)} {describe(vb[:48])}"))
    same = sum(1 for item_id in ids if map_a.get(item_id) == map_b.get(item_id))
    print(f"  identical entries: {same}/{len(ids)}")
    if a.signature or b.signature:
        print(f"  signatures: {name_a}={a.signature[:8].hex()}... {name_b}={b.signature[:8].hex()}...")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", type=Path, required=True, help="first config section binary")
    parser.add_argument("--b", type=Path, required=True, help="second config section binary")
    parser.add_argument("--name-a", default="A")
    parser.add_argument("--name-b", default="B")
    parser.add_argument("--dump", action="store_true", help="list every entry of both sections")
    args = parser.parse_args()

    section_a = parse_section(args.a.read_bytes())
    section_b = parse_section(args.b.read_bytes())
    if args.dump:
        for name, section in ((args.name_a, section_a), (args.name_b, section_b)):
            print(f"-- {section.magic} {name}: body={section.body_length} signature={len(section.signature)}")
            for item_id, value in section.entries:
                print(f"  0x{item_id:04x} len={len(value):3d} {describe(value)}")
    diff(args.name_a, section_a, args.name_b, section_b)


if __name__ == "__main__":
    main()
