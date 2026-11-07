"""Writes the OpenAPI schema to backend/openapi.json for frontend type generation (`make gen-api`)."""

import json
from pathlib import Path

from app.main import create_app

OUT = Path(__file__).resolve().parents[1] / "openapi.json"

if __name__ == "__main__":
    OUT.write_text(json.dumps(create_app().openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OpenAPI → {OUT}")
