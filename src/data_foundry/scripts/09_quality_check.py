import json
import os
from pathlib import Path

from data_foundry.config import BRZ_LAYER_DIR, GLD_LAYER_DIR, RUNS_DIR, SLV_LAYER_DIR
from data_foundry.quality import QualityReport

_MIN_PDF_BYTES = 1_024


def _load(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _check_bronze(report: QualityReport) -> tuple[list[dict], dict[str, list[str]]]:
    catalog: list[dict] = _load(BRZ_LAYER_DIR / "catalog.json") or []
    hashes_data: dict = _load(BRZ_LAYER_DIR / "hashes.json") or {}
    duplicates: dict[str, list[str]] = hashes_data.get("duplicates", {})

    year_null_count = 0

    for entry in catalog:
        code = entry.get("code", "unknown")

        if not entry.get("download_url"):
            report.add(code, "bronze", "download_url", "download_failed",
                       "No download URL found on detail page")

        if not entry.get("downloaded"):
            report.add(code, "bronze", "downloaded", "download_failed",
                       "PDF was not downloaded successfully")

        for field in ("title", "author"):
            value = entry.get(field) or ""
            if not value.strip():
                report.add(code, "bronze", field, "null_value", f"'{field}' is empty")

        raw_acc = entry.get("accesses")
        if isinstance(raw_acc, str):
            report.add(code, "bronze", "accesses",
                       "dirty_field", f"accesses stored as string: {repr(raw_acc)}")

        raw_size = entry.get("size", "") or ""
        if "\r" in raw_size or "\n" in raw_size:
            report.add(code, "bronze", "size", "dirty_field",
                       f"size contains whitespace/newline: {repr(raw_size[:40])}")

        if entry.get("year") is None:
            year_null_count += 1

    if year_null_count == len(catalog) and catalog:
        report.add("_run", "bronze", "year", "null_value",
                   f"year is null for all {year_null_count} documents — "
                   "the year label on the detail page likely does not match any entry in field_map")

    for hash_val, files in duplicates.items():
        for filename in files:
            doc_id = Path(filename).stem
            others = [f for f in files if f != filename]
            report.add(doc_id, "bronze", "document_hash", "duplicate",
                       f"Shares hash {hash_val[:16]}... with {others}")

    return catalog, duplicates


def _check_silver(report: QualityReport, catalog: list[dict]) -> None:
    descriptions: dict = _load(SLV_LAYER_DIR / "descriptions.json") or {}
    translations: dict = _load(SLV_LAYER_DIR / "translations.json") or {}
    desc_trans_path = SLV_LAYER_DIR / "description_translations.json"

    if not desc_trans_path.exists():
        report.add("_run", "silver", "description_translations.json", "missing_file",
                   "File was never written — likely because all descriptions were null "
                   "so 05_translate_descriptions.py had nothing to process")
    desc_translations: dict = _load(desc_trans_path) or {}

    target_langs = ("en", "es", "fr")
    llm_errors_seen: set[str] = set()

    for entry in catalog:
        code = entry.get("code", "unknown")

        desc_entry = descriptions.get(code, {})
        if desc_entry.get("llm_error"):
            err = desc_entry["llm_error"]
            report.add(code, "silver", "description", "llm_error",
                       f"LLM failed to generate description: {err[:120]}")

            llm_errors_seen.add(err[:80])
        elif not desc_entry.get("description"):
            report.add(code, "silver", "description", "null_value",
                       "description is null with no error context (possible silent LLM failure)")

        title_trans = translations.get(code, {})
        trans_errors = title_trans.get("errors", {})
        for lang in target_langs:
            if not title_trans.get(lang):
                detail = trans_errors.get(lang, "no error context recorded")
                report.add(code, "silver", f"title.{lang}", "llm_error",
                           f"Title translation to '{lang}' failed: {detail[:120]}")

        dt = desc_translations.get(code, {})
        for lang in target_langs:
            if not dt.get(lang) and desc_entry.get("description"):
                report.add(code, "silver", f"description.{lang}", "null_value",
                           f"Description translation to '{lang}' is missing")

    # If the same LLM error appears for every document, flag it as a systemic issue
    if len(llm_errors_seen) == 1 and len(descriptions) > 1:
        report.add("_run", "silver", "llm", "llm_error",
                   f"Same LLM error repeated across all documents — likely a "
                   f"connectivity or model configuration problem: {next(iter(llm_errors_seen))}")


def _check_gold(report: QualityReport, catalog: list[dict]) -> None:
    localized: list[dict] = _load(GLD_LAYER_DIR / "localized_catalog.json") or []
    universal: list[dict] = _load(GLD_LAYER_DIR / "universal_metadata.json") or []

    catalog_ids = {e["code"] for e in catalog}
    localized_ids = {e["id"] for e in localized}
    universal_ids = {e["id"] for e in universal}

    for missing_id in catalog_ids - localized_ids:
        report.add(missing_id, "gold", "localized_catalog", "null_value",
                   "Entry in catalog is absent from localized_catalog.json")

    for missing_id in catalog_ids - universal_ids:
        report.add(missing_id, "gold", "universal_metadata", "null_value",
                   "Entry in catalog is absent from universal_metadata.json")

    for record in universal:
        code = record.get("id", "unknown")

        if not record.get("document_hash"):
            report.add(code, "gold", "document_hash", "null_value",
                       "No SHA-256 hash recorded — PDF may not have been hashed")

        size = record.get("size_bytes")
        if size is not None and size < _MIN_PDF_BYTES:
            report.add(code, "gold", "size_bytes", "dirty_field",
                       f"File is only {size} bytes — likely corrupt or placeholder")


def main():
    run_id = os.getenv("RUN_ID", "default")
    run_dir = RUNS_DIR / run_id

    print("Running quality checks...")
    report = QualityReport(run_id)

    catalog, duplicates = _check_bronze(report)

    if not catalog:
        print("catalog.json not found — skipping silver/gold checks.")
    else:
        _check_silver(report, catalog)
        _check_gold(report, catalog)

    report_path = run_dir / "quality_report.json"
    report.write(report_path, total_docs=len(catalog), duplicates=duplicates)
    print(f"Report saved to {report_path}")


if __name__ == "__main__":
    main()