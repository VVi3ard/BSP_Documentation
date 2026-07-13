"""Build the distributable BSP demo source archive."""

from __future__ import annotations

import argparse
from pathlib import Path
import zipfile


EXCLUDED_SUFFIXES = {".addin"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)

    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or path.suffix.lower() in EXCLUDED_SUFFIXES:
                continue
            archive_path = Path("src") / path.relative_to(source)
            package.write(path, archive_path.as_posix())
    temporary.replace(output)


if __name__ == "__main__":
    main()
