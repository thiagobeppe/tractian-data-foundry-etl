import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://dominiopublico.mec.gov.br/pesquisa"

PAGE_SIZE = int(os.getenv("PAGE_SIZE", "10"))
MAX_BOOKS = int(os.getenv("MAX_BOOKS", "0"))


def build_list_url(page: int, page_size: int = PAGE_SIZE) -> str:
    """Build the catalog listing URL for the given 1-based page number."""
    skip = (page - 1) * page_size
    return (
        f"{BASE_URL}/ResultadoPesquisaObraForm.do?"
        f"first={page_size}&skip={skip}&ds_titulo=&co_autor=&no_autor="
        f"&co_categoria=41&pagina={page}&select_action=Submit"
        f"&co_midia=2&co_obra=&co_idioma="
        f"&colunaOrdenar=NU_PAGE_HITS&ordem=desc"
    )

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
RUNS_DIR = DATA_DIR / "runs"

_run_id = os.getenv("RUN_ID", "default")
RUN_BASE = RUNS_DIR / _run_id

PDF_DIR = RUN_BASE / "pdfs"
BRZ_LAYER_DIR = RUN_BASE / "brz"
SLV_LAYER_DIR = RUN_BASE / "slv"
GLD_LAYER_DIR = RUN_BASE / "gld"

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "gemma4:e2b")
