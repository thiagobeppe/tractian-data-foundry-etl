import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _generate_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    short = uuid.uuid4().hex[:8]
    return f"{ts}_{short}"


class RunContext:
    def __init__(self, runs_dir: Path):
        self.run_id = _generate_run_id()
        self.runs_dir = runs_dir
        self.run_dir = runs_dir / self.run_id
        self.pdf_dir = self.run_dir / "pdfs"
        self.brz_dir = self.run_dir / "brz"
        self.slv_dir = self.run_dir / "slv"
        self.gld_dir = self.run_dir / "gld"
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._steps: dict[str, dict] = {}

    def setup(self) -> None:
        for d in (self.brz_dir, self.slv_dir, self.gld_dir):
            d.mkdir(parents=True, exist_ok=True)
        self._write_manifest("running")

    def record_step(self, script: str, status: str, duration_seconds: float) -> None:
        self._steps[script] = {
            "status": status,
            "duration_seconds": round(duration_seconds, 2),
        }
        self._write_manifest("running")

    def finalize(self, status: str) -> None:
        self._write_manifest(status)
        self._update_index(status)
        if status == "completed":
            self._update_latest_symlink()

    def _write_manifest(self, status: str) -> None:
        completed_at = (
            datetime.now(timezone.utc).isoformat() if status != "running" else None
        )
        manifest = {
            "run_id": self.run_id,
            "started_at": self._started_at,
            "completed_at": completed_at,
            "status": status,
            "steps": self._steps,
        }
        (self.run_dir / "run_manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    def _update_index(self, status: str) -> None:
        index_path = self.runs_dir / "index.json"
        index: list[dict] = []
        if index_path.exists():
            with open(index_path, encoding="utf-8") as f:
                index = json.load(f)
        index.append(
            {
                "run_id": self.run_id,
                "started_at": self._started_at,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "status": status,
            }
        )
        index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _update_latest_symlink(self) -> None:
        latest = self.runs_dir / "latest"
        if latest.is_symlink():
            latest.unlink()
        latest.symlink_to(self.run_id)