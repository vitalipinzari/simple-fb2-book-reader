#!/usr/bin/env python3
"""Writes the verbatim files of ai/files/*.md into a repository and checks them against ai/files/checksums.sha256.

    python -I ai/tools/unpack_files.py [target-root] [--check]

target-root defaults to the folder that contains ai/. With --check nothing is written: the files already in
target-root are compared with the bundles. Standard library only (Python 3.8+).

Each bundle section looks like this (see make_bundles.py, which writes them):

    ## `path/of/the/file`

    <encoding>, <line endings>, <ends with a newline | no newline at the end>[, contains tabs].

    ```lang
    ...content...
    ```
"""
import hashlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = HERE.parent / "files"
HEADING = re.compile(r"^## `([^`]+)`$")
FENCE = re.compile(r"^(`{3,})[A-Za-z0-9_+-]*$")


def parse(bundle: Path):
    lines = bundle.read_text(encoding="utf-8").split("\n")
    i = 0
    while i < len(lines):
        m = HEADING.match(lines[i])
        if not m:
            i += 1
            continue
        rel = m.group(1)
        desc = lines[i + 2]
        f = FENCE.match(lines[i + 4])
        if not f:
            sys.exit(f"{bundle.name}: no code fence after the heading of {rel}")
        fence = f.group(1)
        j = i + 5
        body = []
        while lines[j] != fence:
            body.append(lines[j])
            j += 1
        yield rel, desc, body
        i = j + 1


def build(desc: str, body):
    """Rebuilds the exact bytes from the content lines and the description line."""
    n = len(body)
    newline_at_end = "ends with a newline" in desc
    ends = ["\n"] * n
    m = re.search(r"CRLF line endings except LF after line (\d+(?:, \d+)*)", desc)
    if m:
        lf = {int(x) for x in re.findall(r"\d+", m.group(1))}
        ends = ["\n" if k + 1 in lf else "\r\n" for k in range(n)]
    else:
        m = re.search(r"LF line endings except CRLF after line (\d+(?:, \d+)*)", desc)
        if m:
            crlf = {int(x) for x in re.findall(r"\d+", m.group(1))}
            ends = ["\r\n" if k + 1 in crlf else "\n" for k in range(n)]
        elif "CRLF line endings" in desc:
            ends = ["\r\n"] * n
    if not newline_at_end:
        ends[-1] = ""
    text = "".join(line + end for line, end in zip(body, ends))
    data = text.encode("utf-8")
    if "with BOM" in desc:
        data = b"\xef\xbb\xbf" + data
    return data


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check = "--check" in sys.argv
    root = Path(args[0]).resolve() if args else HERE.parents[1]
    expected = {}
    for line in (FILES / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            h, rel = line.split("  ", 1)
            expected[rel] = h
    bad = 0
    count = 0
    for bundle in sorted(FILES.glob("*.md")):
        for rel, desc, body in parse(bundle):
            data = build(desc, body)
            h = hashlib.sha256(data).hexdigest()
            if expected.get(rel) != h:
                print(f"MISMATCH (bundle vs checksums): {rel}")
                bad += 1
                continue
            target = root / rel
            if check:
                if not target.exists():
                    print(f"missing: {rel}")
                    bad += 1
                elif hashlib.sha256(target.read_bytes()).hexdigest() != h:
                    print(f"differs: {rel}")
                    bad += 1
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            count += 1
    print(f"{'checked' if check else 'wrote'} {count} files under {root}, {bad} problem(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
