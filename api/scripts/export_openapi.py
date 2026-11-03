"""Write the API's OpenAPI document to contracts/openapi.json (sorted keys, stable output)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from plandesk.config import Settings
from plandesk.main import create_app

OUT = Path(__file__).resolve().parents[2] / "contracts" / "openapi.json"


def main() -> int:
    app = create_app(Settings(static_dir=""))
    doc = app.openapi()
    OUT.write_text(json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"wrote {OUT.relative_to(OUT.parents[1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
