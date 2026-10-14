"""Write the v1 OpenAPI contract to packages/contracts/openapi.json (run in CI to detect drift)."""
import json
import pathlib

from app.main import create_app

out = pathlib.Path(__file__).resolve().parents[3] / "packages" / "contracts" / "openapi.json"
out.write_text(json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n")
print(f"wrote {out}")
