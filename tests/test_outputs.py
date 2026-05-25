import json
import re
from pathlib import Path

import pytest

from data_foundry.config import build_list_url
from data_foundry.quality import QualityReport, normalize_text
from data_foundry.run_context import RunContext

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Codes present in every fixture file — used to assert completeness.
FIXTURE_CODES = {"15713", "15654", "2268"}


def load(layer: str, filename: str) -> dict | list:
    return json.loads((FIXTURES / layer / filename).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# normalize_text
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    (None, None),
    ("", None),
    ("  hello  world  ", "hello world"),
    ("café\xa0au\xa0lait", "café au lait"),
    ("line\r\nbreak", "line break"),
    ("​silent", "silent"),   # zero-width space
    ("﻿bom", "bom"),         # byte-order mark
])
def test_normalize_text(text, expected):
    assert normalize_text(text) == expected


def test_normalize_text_nfc():
    # e + combining acute accent → precomposed é
    assert normalize_text("é") == "\xe9"


# ---------------------------------------------------------------------------
# build_list_url
# ---------------------------------------------------------------------------

def test_build_list_url_page_1():
    url = build_list_url(1, page_size=10)
    assert "pagina=1" in url
    assert "skip=0" in url
    assert "first=10" in url


def test_build_list_url_page_2():
    url = build_list_url(2, page_size=10)
    assert "pagina=2" in url
    assert "skip=10" in url


@pytest.mark.parametrize("page", range(1, 6))
def test_build_list_url_skip_formula(page):
    url = build_list_url(page, page_size=5)
    assert f"skip={(page - 1) * 5}" in url


# ---------------------------------------------------------------------------
# RunContext
# ---------------------------------------------------------------------------

def test_run_context_creates_dirs(tmp_path):
    ctx = RunContext(tmp_path)
    ctx.setup()
    for attr in ("brz_dir", "slv_dir", "gld_dir", "pdf_dir", "covers_dir"):
        assert getattr(ctx, attr).exists(), f"{attr} was not created"


def test_run_context_run_id_format(tmp_path):
    ctx = RunContext(tmp_path)
    assert re.match(r"^\d{8}T\d{6}_[0-9a-f]{8}$", ctx.run_id)


def test_run_context_manifest_on_finalize(tmp_path):
    ctx = RunContext(tmp_path)
    ctx.setup()
    ctx.finalize("completed")
    manifest = json.loads((ctx.run_dir / "run_manifest.json").read_text())
    assert manifest["status"] == "completed"
    assert manifest["run_id"] == ctx.run_id
    assert manifest["completed_at"] is not None


def test_run_context_latest_symlink(tmp_path):
    ctx = RunContext(tmp_path)
    ctx.setup()
    ctx.finalize("completed")
    latest = tmp_path / "latest"
    assert latest.is_symlink()
    assert latest.resolve() == ctx.run_dir


def test_run_context_index(tmp_path):
    ctx = RunContext(tmp_path)
    ctx.setup()
    ctx.finalize("completed")
    index = json.loads((tmp_path / "index.json").read_text())
    assert len(index) == 1
    assert index[0]["run_id"] == ctx.run_id


def test_run_context_record_step(tmp_path):
    ctx = RunContext(tmp_path)
    ctx.setup()
    ctx.record_step("01_download.py", "ok", 1.5)
    manifest = json.loads((ctx.run_dir / "run_manifest.json").read_text())
    assert manifest["steps"]["01_download.py"]["status"] == "ok"
    assert manifest["steps"]["01_download.py"]["duration_seconds"] == 1.5


# ---------------------------------------------------------------------------
# QualityReport
# ---------------------------------------------------------------------------

def test_quality_report_write(tmp_path):
    report = QualityReport("test-run")
    report.add("doc1", "bronze", "size", "dirty_field", "has \\r\\n")
    report.add("doc2", "silver", "description", "llm_error", "timeout")
    out = tmp_path / "quality_report.json"
    report.write(out, total_docs=5, duplicates={})
    data = json.loads(out.read_text())
    assert data["run_id"] == "test-run"
    assert data["summary"]["total_documents"] == 5
    assert data["summary"]["total_issues"] == 2
    assert data["summary"]["documents_with_issues"] == 2
    assert data["summary"]["documents_clean"] == 3


def test_quality_report_deduplicates_affected_docs(tmp_path):
    report = QualityReport("run-x")
    report.add("doc1", "bronze", "size", "dirty_field", "a")
    report.add("doc1", "silver", "description", "llm_error", "b")
    out = tmp_path / "report.json"
    report.write(out, total_docs=3, duplicates={})
    data = json.loads(out.read_text())
    assert data["summary"]["total_issues"] == 2
    assert data["summary"]["documents_with_issues"] == 1


# ---------------------------------------------------------------------------
# Bronze layer — fixtures
# ---------------------------------------------------------------------------

def test_bronze_catalog_required_fields():
    catalog = load("brz", "catalog.json")
    assert {e["code"] for e in catalog} == FIXTURE_CODES
    for entry in catalog:
        assert "title" in entry
        assert "download_url" in entry


def test_bronze_catalog_accesses_is_int():
    catalog = load("brz", "catalog.json")
    for entry in catalog:
        assert isinstance(entry.get("accesses"), int), (
            f"accesses must be int in catalog entry {entry['code']}: "
            f"got {type(entry.get('accesses')).__name__}"
        )


def test_bronze_catalog_no_dirty_size():
    catalog = load("brz", "catalog.json")
    for entry in catalog:
        size = entry.get("size") or ""
        assert "\r" not in size and "\n" not in size, (
            f"Dirty size field in {entry['code']}: {repr(size)}"
        )


def test_bronze_hashes_structure():
    hashes = load("brz", "hashes.json")
    assert "files" in hashes
    for filename, info in hashes["files"].items():
        assert "sha256" in info, f"sha256 missing for {filename}"
        assert "size_bytes" in info, f"size_bytes missing for {filename}"


# ---------------------------------------------------------------------------
# Silver layer — fixtures
# ---------------------------------------------------------------------------

def test_silver_descriptions_keys():
    descriptions = load("slv", "descriptions.json")
    assert set(descriptions.keys()) == FIXTURE_CODES


def test_silver_descriptions_llm_error_field():
    descriptions = load("slv", "descriptions.json")
    for code, entry in descriptions.items():
        assert "llm_error" in entry, f"llm_error field missing for {code}"


def test_silver_translations_languages():
    translations = load("slv", "translations.json")
    for code, entry in translations.items():
        for lang in ("en", "es", "fr"):
            assert lang in entry, f"Missing '{lang}' in translations for {code}"


def test_silver_description_translations_exists():
    path = FIXTURES / "slv" / "description_translations.json"
    assert path.exists(), "description_translations.json must always be present"


def test_silver_covers_structure():
    covers = load("slv", "covers.json")
    assert set(covers.keys()) == FIXTURE_CODES
    for code, entry in covers.items():
        assert "path" in entry and "hash" in entry, (
            f"covers entry for {code} missing path or hash"
        )


# ---------------------------------------------------------------------------
# Gold layer — fixtures
# ---------------------------------------------------------------------------

def test_gold_localized_catalog_schema():
    data = load("gld", "localized_catalog.json")
    assert {e["id"] for e in data} == FIXTURE_CODES
    for entry in data:
        assert entry.get("id"), "localized_catalog entry missing 'id'"
        assert entry["title"].get("pt"), "Portuguese title must be present"
        for lang in ("en", "es", "fr"):
            assert lang in entry["title"], f"title missing language '{lang}'"
            assert lang in entry["description"], f"description missing language '{lang}'"


def test_gold_universal_metadata_schema():
    data = load("gld", "universal_metadata.json")
    assert {e["id"] for e in data} == FIXTURE_CODES
    for entry in data:
        assert entry.get("document_hash"), f"document_hash missing for {entry['id']}"
        assert isinstance(entry.get("accesses"), int), (
            f"accesses must be int in universal_metadata: {entry['id']}"
        )
        assert entry.get("size_bytes", 0) > 0, (
            f"size_bytes must be positive for {entry['id']}"
        )


def test_gold_outputs_ids_consistent():
    loc_ids = {e["id"] for e in load("gld", "localized_catalog.json")}
    uni_ids = {e["id"] for e in load("gld", "universal_metadata.json")}
    cat_ids = {e["code"] for e in load("brz", "catalog.json")}
    assert loc_ids == uni_ids == cat_ids, (
        "IDs must match across localized_catalog, universal_metadata, and catalog"
    )


def test_gold_cover_path_matches_cover_hash():
    data = load("gld", "universal_metadata.json")
    for entry in data:
        if entry.get("cover_path") and entry.get("cover_hash"):
            assert entry["cover_hash"] in entry["cover_path"], (
                f"cover_path does not contain cover_hash for {entry['id']}"
            )


# ---------------------------------------------------------------------------
# Run manifest — fixture
# ---------------------------------------------------------------------------

def test_run_manifest_structure():
    manifest = json.loads((FIXTURES / "run_manifest.json").read_text())
    assert manifest.get("run_id")
    assert manifest.get("status") == "completed"
    assert manifest.get("completed_at") is not None
    assert isinstance(manifest.get("steps"), dict)


def test_run_manifest_all_steps_present():
    manifest = json.loads((FIXTURES / "run_manifest.json").read_text())
    expected = {
        "01_download.py", "02_hash.py", "03_describe.py",
        "04_translate.py", "05_translate_descriptions.py", "06_covers.py",
        "07_localized_catalog.py", "08_universal_metadata.py", "09_quality_check.py",
    }
    assert set(manifest["steps"].keys()) == expected


# ---------------------------------------------------------------------------
# Quality report — fixture
# ---------------------------------------------------------------------------

def test_quality_report_structure():
    report = json.loads((FIXTURES / "quality_report.json").read_text())
    assert report.get("run_id")
    summary = report.get("summary", {})
    assert "total_documents" in summary
    assert "total_issues" in summary
    assert "documents_with_issues" in summary
    assert "documents_clean" in summary


def test_quality_report_issues_have_required_fields():
    report = json.loads((FIXTURES / "quality_report.json").read_text())
    for issue in report.get("issues", []):
        for field in ("doc_id", "stage", "field", "issue_type", "detail"):
            assert field in issue, f"Quality issue missing field '{field}': {issue}"
