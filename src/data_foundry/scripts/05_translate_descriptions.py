import json

from openai import OpenAI

from data_foundry.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, SLV_LAYER_DIR

TARGET_LANGUAGES = {"en": "English", "es": "Spanish", "fr": "French"}

client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)


def translate_text(text: str, target_lang: str) -> tuple[str | None, str | None]:
    """Return (translation, error_message). One of the two will always be None."""
    prompt = (
        f"Translate the following Portuguese text to {target_lang}. "
        f"Return ONLY the translated text, nothing else.\n\n"
        f"{text}"
    )

    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            timeout=60,
        )
        result = resp.choices[0].message.content.strip()
        if not result:
            return None, "empty_response"
        return result, None
    except Exception as e:
        print(f"  LLM error: {e}")
        return None, str(e)


def main():
    SLV_LAYER_DIR.mkdir(parents=True, exist_ok=True)

    desc_path = SLV_LAYER_DIR / "descriptions.json"
    if not desc_path.exists():
        print("descriptions.json not found. Run 03_describe.py first.")
        return

    with open(desc_path, encoding="utf-8") as f:
        descriptions = json.load(f)

    trans_path = SLV_LAYER_DIR / "description_translations.json"
    if trans_path.exists():
        with open(trans_path, encoding="utf-8") as f:
            translations = json.load(f)
    else:
        translations = {}

    entries = {k: v for k, v in descriptions.items() if v.get("description")}
    print(
        f"Translating {len(entries)} descriptions to {', '.join(TARGET_LANGUAGES.values())}..."
    )
    print(f"Using model: {LLM_MODEL} via {LLM_BASE_URL}")

    for i, (code, entry) in enumerate(entries.items()):
        if code in translations:
            print(f"[{i + 1}/{len(entries)}] {code} — already translated, skipping")
            continue

        title = entry.get("title", code)
        description = entry["description"]
        print(f"[{i + 1}/{len(entries)}] {title[:50]}...")

        entry_translations: dict = {"original": description}
        errors: dict[str, str] = {}
        for lang_key, lang_name in TARGET_LANGUAGES.items():
            translated, llm_error = translate_text(description, lang_name)
            entry_translations[lang_key] = translated
            if translated:
                print(f"  {lang_key}: {translated[:60]}")
            elif llm_error:
                errors[lang_key] = llm_error
        if errors:
            entry_translations["errors"] = errors

        translations[code] = entry_translations

        with open(trans_path, "w", encoding="utf-8") as f:
            json.dump(translations, f, ensure_ascii=False, indent=2)

    with open(trans_path, "w", encoding="utf-8") as f:
        json.dump(translations, f, ensure_ascii=False, indent=2)

    translated = sum(1 for t in translations.values() if t.get("en"))
    print(f"\nDone. {translated}/{len(translations)} descriptions translated.")
    print(f"Output saved to {trans_path}")


if __name__ == "__main__":
    main()