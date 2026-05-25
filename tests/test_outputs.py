import json
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RUNS_DIR = DATA_DIR / "runs"
PDF_DIR = DATA_DIR / "pdfs"

MIN_ENTRIES = 10

# Maps each output file to the medallion layer it lives in.
FILE_LAYERS: dict[str, str] = {
    "catalog.json": "brz",
    "metadata.json": "brz",
    "hashes.json": "brz",
    "descriptions.json": "slv",
    "translations.json": "slv",
    "description_translations.json": "slv",
    "covers.json": "slv",
    "localized_catalog.json": "gld",
    "universal_metadata.json": "gld",
}


def _run_dir() -> Path:
    """Resolve the latest completed run directory via the 'latest' symlink.

    Falls back to the most recently created run directory if the symlink is absent,
    so that individual-step runs (make download, etc.) can still be tested.
    """
    latest = RUNS_DIR / "latest"
    if latest.is_symlink():
        return latest.resolve()
    candidates = [d for d in RUNS_DIR.iterdir() if d.is_dir()]
    if candidates:
        return max(candidates, key=lambda d: d.name)
    raise FileNotFoundError("No run directories found under data/runs/")


def load_json(name: str) -> dict | list:
    layer = FILE_LAYERS[name]
    path = _run_dir() / layer / name
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --- output file presence ---

@pytest.mark.parametrize("filename", list(FILE_LAYERS.keys()))
def test_output_file_exists(filename):
    layer = FILE_LAYERS[filename]
    path = _run_dir() / layer / filename
    assert path.exists() and path.stat().st_size > 0, f"{filename} missing or empty"


# --- minimum volume ---

def test_minimum_pdfs():
    assert len(list(PDF_DIR.glob("*.pdf"))) >= MIN_ENTRIES


# --- gold layer correctness ---

def test_localized_catalog():
    data = load_json("localized_catalog.json")
    assert len(data) >= MIN_ENTRIES
    for entry in data:
        assert entry.get("id") and entry.get("title", {}).get("pt")


def test_universal_metadata():
    data = load_json("universal_metadata.json")
    assert len(data) >= MIN_ENTRIES
    for entry in data:
        assert entry.get("id") and entry.get("document_hash")


def test_outputs_consistent():
    loc_ids = {e["id"] for e in load_json("localized_catalog.json")}
    uni_ids = {e["id"] for e in load_json("universal_metadata.json")}
    cat_ids = {e["code"] for e in load_json("catalog.json")}
    assert loc_ids == uni_ids == cat_ids


# --- versioning ---

def test_run_manifest_exists():
    manifest_path = _run_dir() / "run_manifest.json"
    assert manifest_path.exists(), "run_manifest.json missing"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("run_id"), "run_id missing from manifest"
    assert manifest.get("status") == "completed", (
        f"run did not complete cleanly: status={manifest.get('status')}"
    )


def test_runs_index_exists():
    index_path = RUNS_DIR / "index.json"
    assert index_path.exists(), "runs/index.json missing"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert len(index) >= 1
    assert index[-1].get("run_id"), "last index entry has no run_id"