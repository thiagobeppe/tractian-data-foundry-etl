import json
from pathlib import Path

from data_foundry.config import BRZ_LAYER_DIR, SLV_LAYER_DIR, GLD_LAYER_DIR


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

    translations = load_json(SLV_LAYER_DIR / "translations.json")
    descriptions = load_json(SLV_LAYER_DIR / "descriptions.json")
    desc_translations = load_json(SLV_LAYER_DIR / "description_translations.json")

    # load_json returns [] for missing files; convert dicts-keyed-by-code to dict
    if isinstance(translations, list):
        translations = {}
    if isinstance(descriptions, list):
        descriptions = {}
    if isinstance(desc_translations, list):
        desc_translations = {}

    localized = []
    for entry in catalog:
        code = entry["code"]

        title_trans = translations.get(code, {})
        desc_data = descriptions.get(code, {})
        desc_trans = desc_translations.get(code, {})

        record = {
            "id": code,
            "title": {
                "pt": entry["title"],
                "en": title_trans.get("en"),
                "es": title_trans.get("es"),
                "fr": title_trans.get("fr"),
            },
            "description": {
                "pt": desc_data.get("description"),
                "en": desc_trans.get("en"),
                "es": desc_trans.get("es"),
                "fr": desc_trans.get("fr"),
            },
            "author": entry.get("author"),
            "source": entry.get("source"),
        }
        localized.append(record)

    output_path = GLD_LAYER_DIR / "localized_catalog.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(localized, f, ensure_ascii=False, indent=2)

    complete = sum(
        1 for r in localized if r["title"].get("en") and r["description"].get("pt")
    )
    print(f"Done. {len(localized)} entries assembled ({complete} fully localized).")
    print(f"Output saved to {output_path}")


if __name__ == "__main__":
    main()