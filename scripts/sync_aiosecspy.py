"""Sync vendored aiosecspy into the custom component (HACS-friendly)."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "aiosecspy" / "aiosecspy"
DST = ROOT / "custom_components" / "secspy" / "aiosecspy"


def main() -> None:
    if not SRC.is_dir():
        raise SystemExit(f"missing source package: {SRC}")
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)
    print(f"synced {SRC} -> {DST}")


if __name__ == "__main__":
    main()
