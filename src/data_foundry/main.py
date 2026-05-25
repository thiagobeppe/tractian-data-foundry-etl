import os
import subprocess
import sys
import time
from pathlib import Path

from data_foundry.config import PDF_DIR, RUNS_DIR
from data_foundry.run_context import RunContext

SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"

STEPS = [
    ("01_download.py", "Scrape catalog and download PDFs"),
    ("02_hash.py", "Calculate document hashes"),
    ("03_describe.py", "Generate descriptions via vision LLM"),
    ("04_translate.py", "Translate titles"),
    ("05_translate_descriptions.py", "Translate descriptions"),
    ("06_covers.py", "Extract cover pages"),
    ("07_localized_catalog.py", "Assemble localized catalog"),
    ("08_universal_metadata.py", "Assemble universal metadata"),
]


def run_step(script: str, description: str, run_id: str) -> tuple[bool, float]:
    print(f"\n{'=' * 60}")
    print(f"  {description}")
    print(f"  Running: {script}")
    print(f"{'=' * 60}\n")

    env = {**os.environ, "RUN_ID": run_id}
    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script)],
        cwd=str(SCRIPTS_DIR.parent),
        env=env,
    )
    duration = time.monotonic() - start
    return result.returncode == 0, duration


def main():
    print("Domínio Público Data Pipeline")
    print("=" * 60)

    run_ctx = RunContext(RUNS_DIR)
    run_ctx.setup
    print("=" * 60)

    

    overall_status = "completed"
    for script, description in STEPS:
        success, duration = run_step(script, description, run_ctx.run_id)
        step_status = "ok" if success else "failed"
        run_ctx.record_step(script, step_status, duration)

        if not success:
            print(f"\nStep failed: {script}. Stopping pipeline.")
            overall_status = "failed"
            break

    print(f"\n{'=' * 60}")
    print("Pipeline Summary")
    print(f"{'=' * 60}")
    for script, info in run_ctx._steps.items():
        icon = "+" if info["status"] == "ok" else "X"
        print(f"  [{icon}] {script}: {info['status']} ({info['duration_seconds']}s)")

    run_ctx.finalize(overall_status)

    print(f"\nRun {run_ctx.run_id} — {overall_status}")
    if overall_status == "completed":
        print(f"Outputs → {run_ctx.run_dir}")
        print(f"Latest  → {run_ctx.runs_dir / 'latest'}")


if __name__ == "__main__":
    main()