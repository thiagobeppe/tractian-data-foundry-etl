import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://dominiopublico.mec.gov.br/pesquisa"
LIST_URL = (
    f"{BASE_URL}/ResultadoPesquisaObraForm.do?"
    "first=10&skip=0&ds_titulo=&co_autor=&no_autor="
    "&co_categoria=41&pagina=1&select_action=Submit"
    "&co_midia=2&co_obra=&co_idioma="
    "&colunaOrdenar=NU_PAGE_HITS&ordem=desc"
)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PDF_DIR = DATA_DIR / "pdfs"
OUTPUT_DIR = DATA_DIR / "runs"
BRZ_LAYER_DIR = DATA_DIR / "runs" / "brz"
SLV_LAYER_DIR = DATA_DIR / "runs" / "slv"
GLD_LAYER_DIR = DATA_DIR / "runs" / "gld"

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "gemma4:e2b")
