import json

from scripts.export_openapi import export_openapi


def test_export_openapi_writes_schema(tmp_path):
    output = tmp_path / "openapi.json"

    export_openapi(output)

    schema = json.loads(output.read_text(encoding="utf-8"))
    assert schema["openapi"].startswith("3.")
    assert "/runs/{run_id}.json" in schema["paths"]
    assert "/runs/{run_id}/validation" in schema["paths"]
