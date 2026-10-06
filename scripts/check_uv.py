#!/usr/bin/env python3
"""Verify that the local uv can read this repository's lockfile."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys

MINIMUM = (0, 8, 0)


def main() -> int:
    uv = shutil.which("uv")
    if uv is None:
        print(
            "FluxRules requires uv >= 0.8.0, but uv was not found.\n"
            "Install it, then rerun this command:\n"
            "  python -m pip install 'uv>=0.8'",
            file=sys.stderr,
        )
        return 1

    completed = subprocess.run(
        [uv, "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    output = (completed.stdout or completed.stderr).strip()
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", output)
    if completed.returncode != 0 or match is None:
        print(
            "Unable to determine the installed uv version. "
            "Install uv >= 0.8.0 and rerun this command:\n"
            "  python -m pip install 'uv>=0.8'",
            file=sys.stderr,
        )
        return 1

    version = tuple(int(part or 0) for part in match.groups())
    if version < MINIMUM:
        display_version = match.group(0)
        print(
            f"FluxRules requires uv >= 0.8.0, but found uv {display_version}. "
            "This version cannot read the committed lockfile.\n"
            "Upgrade it:\n"
            "  python -m pip install 'uv>=0.8'",
            file=sys.stderr,
        )
        return 1

    print(f"uv {output} satisfies the FluxRules requirement (>= 0.8.0).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
