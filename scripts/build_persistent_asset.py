from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from automotive_model import build_persistent_asset


def main() -> None:
    output = Path(os.environ["AUTOMOTIVE_ASSET_OUTPUT"]).resolve()
    profile_path = Path(os.environ["AUTOMOTIVE_PROFILE_PATH"]).resolve()
    metadata = Path(os.environ["AUTOMOTIVE_ASSET_METADATA"]).resolve()
    build_persistent_asset(output, metadata, profile_path)


if __name__ == "__main__":
    main()
