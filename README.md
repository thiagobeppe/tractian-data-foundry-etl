# Domínio Público Data Pipeline

A data pipeline that ingests and enriches documents from [Domínio Público](https://dominiopublico.mec.gov.br), Brazil's public domain digital library. It scrapes book metadata, downloads PDFs, generates LLM descriptions and multilingual translations, and produces two normalised output datasets per run.

---

## Setup

### Requirements

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- [uv](https://docs.astral.sh/uv/) (Python package manager) — for local development only

### Run with Docker (recommended)

```bash
cp .env.example .env
make run
```

`make run` starts two containers: `ollama` (the local LLM) and `pipeline` (the pipeline itself). Output is written to `./data/` which is mounted into the container.

### Run locally (without Docker)

```bash
make setup
make setup-ollama

make run
```

Or run individual steps:

```bash
make download                # step 01 — scrape catalog and download PDFs
make hash                    # step 02 — compute SHA-256 hashes
make describe                # step 03 — LLM vision descriptions
make translate               # step 04 — translate titles
make translate-descriptions  # step 05 — translate descriptions
make covers                  # step 06 — extract cover images
make localized-catalog       # step 07 — assemble localized_catalog.json
make universal-metadata      # step 08 — assemble universal_metadata.json
make quality                 # step 09 — validate outputs and write quality report
```

### Validate outputs

```bash
make test
```

### LLM configuration

The pipeline uses an OpenAI-compatible API. Switch between Ollama and any cloud provider via environment variables:

```bash
# .env — local Ollama (default)
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=gemma4:e2b

# .env — OpenAI
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o
```

### Scale configuration

```bash
MAX_BOOKS=50    # cap total books per run (default: 0 = no limit, scrape all)
PAGE_SIZE=10    # results per listing page (default: 10)
```

---

## Architecture

### Pipeline steps

```
Domínio Público (website)
        |
        v
  01_download ──── paginated scraping, PDF download
        |
        v
  02_hash ──────── SHA-256 per PDF, duplicate detection
        |
        v
  03_describe ──── vision LLM → Portuguese description per cover
        |
        v
  04_translate ─── LLM → title in EN / ES / FR
        |
        v
  05_translate_descriptions ── LLM → description in EN / ES / FR
        |
        v
  06_covers ────── extract cover PNG (content-addressed by hash)
        |
        v
  07_localized_catalog ──── assemble gold output #1
        |
        v
  08_universal_metadata ─── assemble gold output #2
        |
        v
  09_quality_check ──────── validate all layers → quality_report.json
```

### Medallion data layers

Each pipeline run writes into its own versioned directory. Layers separate data by maturity:

```
data/
└── runs/
    ├── index.json                    ← history of all runs
    ├── latest -> {run_id}/           ← symlink to most recent completed run
    └── {run_id}/                     ← e.g. 20260525T143012_abc12345
        ├── run_manifest.json         ← timing, step status, start/end timestamps
        ├── quality_report.json       ← per-document issue list + summary
        ├── pdfs/                     ← downloaded PDFs (raw)
        ├── covers/                   ← cover PNGs for this run (content-addressed by SHA-256)
        ├── brz/                      ← Bronze: extracted, unvalidated structured data
        │   ├── catalog.json
        │   ├── metadata.json
        │   └── hashes.json
        ├── slv/                      ← Silver: LLM-enriched, validated
        │   ├── descriptions.json
        │   ├── translations.json
        │   ├── description_translations.json
        │   └── covers.json
        └── gld/                      ← Gold: final, schema-compliant output
            ├── localized_catalog.json
            └── universal_metadata.json
```

### Output datasets

**`gld/localized_catalog.json`** — language-dependent, for browsing and search:

```json
{
  "id": "15713",
  "title": { "pt": "A escravidão", "en": "Slavery", "es": "La esclavitud", "fr": "L'esclavage" },
  "description": { "pt": "...", "en": "...", "es": "...", "fr": "..." },
  "author": "Joaquim Nabuco",
  "source": "[jn] Fundação Joaquim Nabuco"
}
```

**`gld/universal_metadata.json`** — language-independent, for indexing and administration:

```json
{
  "id": "15713",
  "cover_path": "covers/a9c3e4c5....png",
  "cover_hash": "a9c3e4c5...",
  "document_hash": "ed6ca892...",
  "accesses": 39826,
  "size_bytes": 13968344,
  "category": "História",
  "language": "Português",
  "institution": "[jn] Fundação Joaquim Nabuco",
  "year": null,
  "download_url": "https://dominiopublico.mec.gov.br/..."
}
```

---

## Design Decisions and Trade-offs

Before starting development, I evaluated each area by value, impact, and implementation difficulty. Based on that analysis, I chose to follow this order: Data Architecture → Versioning → Data Quality → Scalability → Event-Driven Architecture. This sequence delivers incremental MVPs, where each stage provides tangible value while progressively improving the overall solution.

---

### Medallion layers — bronze / silver / gold

Data moves through three layers of increasing quality:

| Layer  | Contents                          | When it changes                         |
|--------|-----------------------------------|-----------------------------------------|
| Bronze | Raw scraped data, hashes          | After download/hash steps               |
| Silver | LLM-generated content             | After describe/translate/covers steps   |
| Gold   | Final, joined, validated output   | After assembly steps                    |

**Why:** The Medallion architecture improves auditability, backfilling, and visibility. It allows exposing only the Silver layer and beyond as a stable schema contract, ensuring cleaner data for dashboards and model training.

**Trade-off:** There are no significant downsides in this project's current scope. Complexity may increase in a database or cloud-based migration, where multiple datasets and permission boundaries would likely require Infrastructure as Code (IaC). Even so, the organisational benefits outweigh that cost.

---

### Versioning — run-scoped output directories

Every pipeline execution is assigned a unique `run_id` (`{timestamp}_{8-char-uuid}`) at startup. All outputs — PDFs, cover images, intermediate JSON files, and gold datasets — land under `data/runs/{run_id}/`. A `latest` symlink is updated on successful completion; `data/runs/index.json` maintains the full run history. Each run also produces a `run_manifest.json` with step-level timing and status.

**Why:** Re-runs never overwrite previous outputs. This makes debugging safe (compare two runs side by side), supports rollback (point `latest` to any previous run), and makes the pipeline idempotent — the same `RUN_ID` can be re-injected to resume a failed run without overwriting already-completed steps.

**Trade-off:** Storage can grow significantly since PDFs and covers accumulate once per run. A future improvement would be a shared content-addressed asset store, where the bronze layer records a pointer rather than a copy. This keeps the full audit trail while capping storage growth to the number of unique documents rather than the number of runs.

---

### Scalability — pagination with configurable limits

The download script paginates the Domínio Público catalog using `pagina` and `skip` URL parameters. It stops when a page returns fewer entries than `PAGE_SIZE` (natural end of catalog) or when the `MAX_BOOKS` cap is reached. Setting `MAX_BOOKS=0` removes the cap entirely.

**Why:** Pagination gives fine-grained control over input size, allowing different execution strategies — a single-page run for a quick sample, or overnight jobs for large historical backfills — with no code changes.

**Trade-off:** A full uncapped run could take several hours. The 1-second delay between listing page requests is intentional to avoid rate limiting; reducing it risks getting blocked. For large-scale runs, set `MAX_BOOKS` to a reasonable ceiling and schedule during off-peak hours. Pagination alone also does not address the LLM call bottleneck: as the number of books grows, steps 03–05 become the dominant cost. Parallel LLM calls via `asyncio` with a bounded semaphore are the natural next step.

---

### Data Quality — post-pipeline validation step

Step 09 (`09_quality_check.py`) runs after all other steps and inspects every layer. It produces a `quality_report.json` that catalogues issues without blocking the pipeline — records with quality problems carry `null` values in the gold output rather than being silently dropped.

Issues detected include:

- **LLM errors**: descriptions and translations store `"llm_error": "..."` alongside `null` values, so the cause is always traceable
- **Dirty fields**: the `size` field from the HTML listing previously contained embedded `\r\n`; it is now normalised at scrape time via `normalize_text()`
- **Accesses as string**: the listing page returns `"39,826"` — normalised to `int` at ingest
- **Missing output files**: `description_translations.json` was never written when all descriptions were null; now always written (even if empty)
- **Systemic LLM failure detection**: if every document shares the same LLM error, the report flags it as a connectivity/configuration problem rather than per-document noise
- **Duplicate documents**: SHA-256 collisions across files are surfaced in the report

**Trade-off:** Quality validation runs as a read-only final step, meaning issues are reported but not automatically corrected. This is intentional — automatic correction of LLM outputs introduces its own risks. The report is the artefact; fixing the root cause (misconfigured LLM, scraper changes) requires human review.

---

## Future Work

The items below were scoped but not implemented in this iteration, ordered roughly by expected impact.

- **Event-driven ingestion**: Replace the polling-based download step with a Kafka-backed architecture. A producer would stream new entries from Domínio Público into a topic as they arrive; a consumer would trigger enrichment (hashing, LLM description, translation) per message. A dead-letter topic would capture LLM failures for later reprocessing, eliminating the need to re-run the entire pipeline when a subset of documents fail enrichment.

- **Cross-run asset deduplication**: PDFs and cover images currently accumulate once per run. The fix is a shared content-addressed store at `data/assets/{sha256}` — the bronze layer would record a pointer to the asset rather than a copy. Storage growth becomes proportional to the number of unique documents, not the number of runs, while the full audit trail is preserved.

- **Parallel LLM calls**: Steps 03–05 call the LLM sequentially, one document at a time. Replacing the loop with `asyncio` and a bounded semaphore would let multiple requests be in-flight concurrently, reducing wall-clock time roughly proportional to the semaphore size without overwhelming the model server.

- **Inline data quality gates**: The current quality check runs read-only at the end of the pipeline (step 09). Some issues — malformed HTML, missing required fields, LLM responses that fail a schema check — should be caught and either corrected or quarantined in-place rather than surfaced after all downstream steps have already consumed bad data.

- **Run metrics for continuous improvement**: Each run already produces `run_manifest.json` with per-step durations. Aggregating these across runs (e.g., into a lightweight time-series or a simple dashboard) would make it straightforward to spot regressions — a step that suddenly takes 3× longer signals a scraper change, a rate-limit hit, or a model degradation worth investigating.