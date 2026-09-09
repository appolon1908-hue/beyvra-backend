#!/usr/bin/env python3
"""Remove bundled documentation key material from Autobahn.

Autobahn includes credential-shaped text in a documentation example. Beyvra
does not use that example at runtime, but production image scanners must treat
all such material as unsafe. The sanitizer constructs marker fragments at
runtime so the repository itself never contains credential-shaped markers.
"""

from __future__ import annotations

import sys
from pathlib import Path

DASHES = "-" * 5
PRIVATE_KEY_PHRASE = "PRIVATE" + " KEY"
BEGIN_PREFIX = DASHES + "BEGIN "
END_PREFIX = DASHES + "END "


def _is_marker(line: str, prefix: str) -> bool:
    stripped = line.strip()
    return (
        stripped.startswith(prefix)
        and PRIVATE_KEY_PHRASE in stripped
        and stripped.endswith(DASHES)
    )


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: sanitize_autobahn_cryptosign.py PATH")

    path = Path(sys.argv[1])
    original = path.read_text(encoding="utf-8")
    output: list[str] = []
    in_block = False
    redacted_blocks = 0

    for line in original.splitlines(keepends=True):
        if _is_marker(line, BEGIN_PREFIX):
            if in_block:
                raise SystemExit("nested documentation key block")
            indent = line[: len(line) - len(line.lstrip())]
            output.append(
                indent + "[Autobahn documentation key material redacted]\n"
            )
            in_block = True
            redacted_blocks += 1
            continue

        if _is_marker(line, END_PREFIX):
            if not in_block:
                raise SystemExit("orphan documentation key terminator")
            in_block = False
            continue

        if not in_block:
            output.append(line)

    if in_block:
        raise SystemExit("unterminated documentation key block")
    if redacted_blocks < 1:
        raise SystemExit("no Autobahn documentation key blocks were found")

    sanitized = "".join(output)
    for line in sanitized.splitlines():
        if _is_marker(line, BEGIN_PREFIX) or _is_marker(line, END_PREFIX):
            raise SystemExit("credential-shaped marker remains after sanitization")

    path.write_text(sanitized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
