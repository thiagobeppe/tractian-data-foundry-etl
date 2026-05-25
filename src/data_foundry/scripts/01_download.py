import json
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
from playwright.sync_api import sync_playwright

from data_foundry.config import (
    BASE_URL,
    LIST_URL,
    PDF_DIR,
    BRZ_LAYER_DIR,
)
from data_foundry.quality import normalize_text

SESSION = cffi_requests.Session(impersonate="chrome")


def fetch_page(url: str) -> str | None:
    try:
        resp = SESSION.get(url, timeout=30)
        if resp.status_code == 200 and "challenge" not in resp.text[:500].lower():
            return resp.text
    except Exception as e:
        print(f"  curl-cffi failed: {e}")

    return fetch_page_playwright(url)


def fetch_page_playwright(url: str) -> str | None:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=60000)
            time.sleep(3)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        print(f"  Playwright fallback failed: {e}")
    return None


def parse_listing(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="res")
    if not table:
        print("ERROR: Could not find results table (#res)")
        return []

    tbody = table.find("tbody")
    if not tbody:
        print("ERROR: No tbody in results table")
        return []

    entries = []
    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 6:
            continue

        link = cells[2].find("a")
        if not link:
            continue
        href = link.get("href", "")
        code = None
        if "co_obra=" in href:
            code = href.split("co_obra=")[-1].strip("'\" ")

        title = normalize_text(link.get_text(strip=True))
        author = normalize_text(cells[3].get_text(strip=True))
        source = normalize_text(cells[4].get_text(strip=True))
        fmt = normalize_text(cells[5].get_text(strip=True))
        # size comes with embedded \r\n and padding from the HTML table cell
        raw_size = normalize_text(cells[6].get_text(strip=True)) if len(cells) > 6 else None
        raw_accesses = cells[7].get_text(strip=True) if len(cells) > 7 else ""
        try:
            accesses = int(raw_accesses.replace(",", "").replace(".", "").strip())
        except (ValueError, AttributeError):
            accesses = None

        if code and title:
            entries.append(
                {
                    "code": code,
                    "title": title,
                    "author": author,
                    "source": source,
                    "format": fmt,
                    "size": raw_size,
                    "accesses": accesses,
                }
            )

    return entries


def parse_detail_page(html: str) -> dict:
    metadata = {}
    field_map = {
        "Título:": "title",
        "Autor:": "author",
        "Categoria:": "category",
        "Idioma:": "language",
        "Instituição:/Parceiro": "institution",
        # The year label varies by document type — theses use "Ano da Tese",
        # general works may use "Ano:" or "Ano de publicação"
        "Ano da Tese": "year",
        "Ano de publicação": "year",
        "Ano:": "year",
        "Acessos:": "accesses",
    }

    matches = re.findall(r'class="detalhe\d"[^>]*>(.*?)</td>', html, re.DOTALL)
    clean = []
    for m in matches:
        text = BeautifulSoup(m, "html.parser").get_text(strip=True)
        clean.append(text)

    current_field = None
    for text in clean:
        matched_label = None
        for label, key in field_map.items():
            if label in text:
                matched_label = key
                break
        if matched_label:
            current_field = matched_label
        elif current_field and text and text != "\xa0":
            if current_field not in metadata:
                metadata[current_field] = normalize_text(text)
            current_field = None

    return metadata


def get_download_url_and_metadata(code: str) -> tuple[str | None, dict]:
    detail_url = f"{BASE_URL}/DetalheObraForm.do?select_action=&co_obra={code}"
    html = fetch_page(detail_url)
    if not html:
        return None, {}

    metadata = parse_detail_page(html)

    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "download" in href.lower():
            if href.startswith("../"):
                return href.replace(
                    "../", "https://dominiopublico.mec.gov.br/"
                ), metadata
            elif href.startswith("/"):
                return f"https://dominiopublico.mec.gov.br{href}", metadata
            elif not href.startswith("http"):
                return f"https://dominiopublico.mec.gov.br/pesquisa/{href}", metadata
            return href, metadata

    return None, metadata


def download_pdf(url: str, filepath: Path) -> bool:
    try:
        resp = SESSION.get(url, timeout=120)
        if resp.status_code == 200 and len(resp.content) > 1000:
            filepath.write_bytes(resp.content)
            return True
    except Exception as e:
        print(f"  Download error: {e}")
    return False


def main():
    print("Fetching listing page...")
    html = fetch_page(LIST_URL)
    if not html:
        print("Failed to fetch listing page.")
        return

    entries = parse_listing(html)
    print(f"Found {len(entries)} entries")

    if not entries:
        print("No entries found. Check if page structure changed.")
        return

    catalog = []
    all_metadata = {}
    for i, entry in enumerate(entries):
        code = entry["code"]
        print(f"[{i + 1}/{len(entries)}] {entry['title'][:60]}...")

        download_url, detail_meta = get_download_url_and_metadata(code)
        entry["download_url"] = download_url

        all_metadata[code] = {
            **detail_meta,
            "code": code,
            "download_url": download_url,
        }

        if download_url:
            pdf_path = PDF_DIR / f"{code}.pdf"
            if pdf_path.exists():
                print(f"  Already downloaded: {pdf_path.name}")
                entry["downloaded"] = True
            else:
                success = download_pdf(download_url, pdf_path)
                entry["downloaded"] = success
                if success:
                    print(
                        f"  Downloaded: {pdf_path.name} ({pdf_path.stat().st_size} bytes)"
                    )
                else:
                    print("  FAILED to download")
                time.sleep(1)
        else:
            print("  No download URL found")
            entry["downloaded"] = False

        catalog.append(entry)

    catalog_path = BRZ_LAYER_DIR / "catalog.json"
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    metadata_path = BRZ_LAYER_DIR / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(all_metadata, f, ensure_ascii=False, indent=2)

    downloaded = sum(1 for e in catalog if e.get("downloaded"))
    print(f"\nDone. {downloaded}/{len(catalog)} PDFs downloaded.")
    print(f"Catalog saved to {catalog_path}")
    print(f"Metadata saved to {metadata_path}")

if __name__ == "__main__":
    main()
