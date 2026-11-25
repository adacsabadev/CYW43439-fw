#!/usr/bin/env python3
"""Byte-patch a Pico Bluetooth firmware container for integrity probing.

Renders a new header whose container is byte-identical to the template except
for one unique find/replace, leaving record framing untouched. Used to test
whether the CYW43439 ROM enforces the BRCMcfgD signature: if a one-byte change
inside the signed config body still boots, only the per-chunk patch hashes are
verified and spliced configurations become viable.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from analyze_firmware import extract_c_array
from convert_hcd_to_pico import render_header


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--find", required=True, help="hex bytes that occur exactly once")
    parser.add_argument("--replace", required=True, help="hex bytes of equal length")
    args = parser.parse_args()

    find = bytes.fromhex(args.find)
    replace = bytes.fromhex(args.replace)
    if len(find) != len(replace):
        raise ValueError("find/replace must be the same length")

    container = bytes(extract_c_array(args.template))
    occurrences = container.count(find)
    if occurrences != 1:
        raise ValueError(f"pattern occurs {occurrences} times; need exactly 1")
    patched = container.replace(find, replace)
    assert len(patched) == len(container)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_header(patched), encoding="utf-8", newline="\n")
    offset = container.index(find)
    changed = sum(1 for a, b in zip(container, patched) if a != b)
    print(f"generated {args.output}: {changed} byte(s) changed at container offset {offset:#x}")


if __name__ == "__main__":
    main()
