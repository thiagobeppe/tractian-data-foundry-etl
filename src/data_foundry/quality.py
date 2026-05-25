import json
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path



def normalize_text(text: str | None) -> str | None:
    if not text:
        return None
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\xa0", " ").replace("\r", "").replace("​", "").replace("﻿", "")
    text = " ".join(text.split())
    return text or None


@dataclass
class QualityIssue:
    doc_id: str
    stage: str        # bronze | silver | gold
    field: str
    issue_type: str   # null_value | download_failed |
                      # llm_error | missing_file | dirty_field | invalid_year
    detail: str


class QualityReport:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.issues: list[QualityIssue] = []

    def add(self, doc_id: str, stage: str, field: str, issue_type: str, detail: str) -> None:
        self.issues.append(QualityIssue(doc_id, stage, field, issue_type, detail))

    def write(self, path: Path, total_docs: int, duplicates: dict[str, list[str]]) -> None:
        affected = {i.doc_id for i in self.issues}
        report = {
            "run_id": self.run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_documents": total_docs,
                "documents_with_issues": len(affected),
                "documents_clean": total_docs - len(affected),
                "total_issues": len(self.issues),
            },
            "duplicates": duplicates,
            "issues": [asdict(i) for i in self.issues],
        }
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        clean = total_docs - len(affected)
        print(f"Quality: {clean}/{total_docs} documents clean, {len(self.issues)} issues found.")
        if duplicates:
            print(f"  Duplicate groups: {len(duplicates)}")