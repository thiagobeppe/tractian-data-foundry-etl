import json
from pathlib import Path

from data_foundry.config import BRZ_LAYER_DIR, SLV_LAYER_DIR, GLD_LAYER_DIR, PDF_DIR


def load_json(path: Path) -> dict | list:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


def main():
    GLD_LAYER_DIR.mkdir(parents=True, exist_ok=True)

    catalog = load_json(BRZ_LAYER_DIR / "catalog.json")
    if not catalog:
        print("catalog.json not found. Run 01_download.py first.")
        return

    metadata_raw = load_json(BRZ_LAYER_DIR / "metadata.json")
    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}

    hashes_data = load_json(BRZ_LAYER_DIR / "hashes.json")
    hashes = hashes_data.get("files", {}) if isinstance(hashes_data, dict) else {}

    covers_raw = load_json(SLV_LAYER_DIR / "covers.json")
    covers = covers_raw if isinstance(covers_raw, dict) else {}

    metadata_records = []
    for entry in catalog:
        code = entry["code"]
        meta = metadata.get(code, {})
        file_hash = hashes.get(f"{code}.pdf", {})
        cover = covers.get(code)

        accesses_raw = meta.get("accesses") or entry.get("accesses", "0")
        try:
            accesses = int(str(accesses_raw).replace(",", "").replace(".", "").strip())
        except ValueError:
            accesses = None

        size_bytes = file_hash.get("size_bytes")
        if not size_bytes:
            pdf_path = PDF_DIR / f"{code}.pdf"
            if pdf_path.exists():
                size_bytes = pdf_path.stat().st_size

        record = {
            "id": code,
            "cover_path": cover.get("path") if cover else None,
            "cover_hash": cover.get("hash") if cover else None,
            "document_hash": file_hash.get("sha256"),
            "accesses": accesses,
            "size_bytes": size_bytes,
            "category": meta.get("category"),
            "language": meta.get("language"),
            "institution": meta.get("institution"),
            "year": meta.get("year"),
            "download_url": meta.get("download_url") or entry.get("download_url"),
        }
        metadata_records.append(record)

    output_path = GLD_LAYER_DIR / "universal_metadata.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metadata_records, f, ensure_ascii=False, indent=2)

    with_hash = sum(1 for r in metadata_records if r["document_hash"])
    with_cover = sum(1 for r in metadata_records if r["cover_path"])
    print(f"Done. {len(metadata_records)} entries assembled.")
    print(f"  With hash: {with_hash}, with cover: {with_cover}")
    print(f"Output saved to {output_path}")


if __name__ == "__main__":
    main()