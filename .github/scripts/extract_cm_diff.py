#!/usr/bin/env python3
"""Extract the unified diff that `cm fix` prints to stdout.

`cm fix` reliably *prints* the patch (between a "Patch generated successfully"
banner and a box-drawing separator) even when it doesn't write it to disk in a
non-interactive CI shell. This carves out just the diff so the workflow can
`git apply` it deterministically — independent of cm's interactive apply path.

Usage:  extract_cm_diff.py <cm-fix-output.log>   # writes the diff to stdout
Emits nothing (exit 0) if no diff is present.
"""
from __future__ import annotations

import re
import sys

DIFF_START = re.compile(r"^(diff --git |--- a/)")
# Stop at cm's box-drawing separator (U+2500 '─'), the trailing session-log
# line, or any obvious non-diff banner.
STOP = re.compile(r"^(─|=== |\s*✨|\d{4}-\d\d-\d\dT.*Session log)")


def is_diff_line(line: str) -> bool:
    if line == "":
        return True  # tolerate blank lines inside the hunk; trimmed at the end
    return line[0] in " +-@\\" or line.startswith(("diff --git", "--- ", "+++ ", "index "))


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: extract_cm_diff.py <cm-fix-output.log>\n")
        return 0
    with open(sys.argv[1], encoding="utf-8", errors="replace") as fh:
        raw_lines = fh.read().splitlines()

    # Strip runner log timestamps if present while preserving diff whitespace
    lines = [
        re.sub(r"^\d{4}-\d\d-\d\dT[0-9:.]+Z ", "", l) if re.match(r"^\d{4}-\d\d-\d\dT[0-9:.]+Z ", l) else l
        for l in raw_lines
    ]

    # Collect candidate diff blocks. cm fix outputs a terminal UI preview first
    # (with line numbers), followed by the standard git unified diff without line numbers.
    candidates: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if STOP.match(line):
            if current:
                candidates.append(current)
                current = []
            continue
        if DIFF_START.match(line):
            if current:
                candidates.append(current)
                current = []
            current.append(line)
            continue
        if current:
            current.append(line)
    if current:
        candidates.append(current)

    # Filter out blocks that contain line numbers (e.g., ' 31: ' or '-34: ')
    clean_candidates = []
    for block in candidates:
        has_hunk = any(l.startswith("@@") for l in block)
        has_lineno = any(re.search(r"^\s*\d+:", l) or re.search(r"^[+-]\s*\d+:", l) for l in block)
        if has_hunk and not has_lineno:
            clean_candidates.append(block)

    chosen = clean_candidates[-1] if clean_candidates else (candidates[-1] if candidates else [])

    out: list[str] = []
    for line in chosen:
        if STOP.match(line):
            break
        m = re.match(r"^([ +-])\s*\d+:\s?(.*)$", line)
        if m:
            out.append(f"{m.group(1)}{m.group(2)}")
        elif re.match(r"^\s*\d+:\s?(.*)$", line):
            m2 = re.match(r"^\s*\d+:\s?(.*)$", line)
            out.append(f" {m2.group(1)}")
        elif is_diff_line(line):
            out.append(line)
        else:
            break

    # Trim trailing blank lines that aren't real context.
    while out and out[-1] == "":
        out.pop()

    if out:
        sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
