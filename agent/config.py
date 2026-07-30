"""Pfade, Konstanten und Env-Var-Namen fuer den Sibbu-Moments-Website-Agenten."""

import os
from pathlib import Path

# --- Repos ---

WEBSITE_ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = WEBSITE_ROOT / "agent"

DOCS_DIR = WEBSITE_ROOT / "docs"
DATA_DIR = DOCS_DIR / "data"
TOOLS_DIR = WEBSITE_ROOT / "tools"

CONTENT_FILE = DATA_DIR / "site-content.json"
STATE_FILE = DATA_DIR / "site-state.json"
SCHEMA_FILE = DATA_DIR / "content-schema.json"
AGENT_INTERFACE_FILE = DATA_DIR / "agent-interface.json"
ARCHIVE_DATA_DIR = DATA_DIR / "archive"

IMAGES_DIR = DOCS_DIR / "assets" / "images"
IMAGES_WEB_DIR = IMAGES_DIR / "web"
IMAGES_MOBILE_DIR = IMAGES_DIR / "mobile"
IMAGES_ARCHIVE_DIR = IMAGES_DIR / "archive"
IMAGES_ORIGINAL_DERIVED_DIR = IMAGES_DIR / "original-derived"

VALIDATE_SCRIPT = TOOLS_DIR / "validate_site.py"

# Content_Agent ist ausschliesslich lesend zu verwenden -- niemals ein Pfad
# aus diesem Bereich in einer Schreiboperation.
CONTENT_AGENT_ROOT = Path.home() / "Desktop" / "Content_Agent"
MEDIENPROJEKTE_DIR = CONTENT_AGENT_ROOT / "Medienprojekte"
ARCHIV_DIR = MEDIENPROJEKTE_DIR / "archiv"

# --- OpenAI ---

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_MODEL_ENV = "SIBBU_AGENT_OPENAI_MODEL"
DEFAULT_OPENAI_MODEL = "gpt-5"

LOCAL_ENV_FILE = AGENT_DIR / ".env.local"

# Single-Instance-Sperre: verhindert, dass zwei Laeufe gleichzeitig auf
# denselben Website-Zustand schreiben (siehe run.py).
LOCK_FILE = AGENT_DIR / ".run.lock"

OPENAI_MAX_VERSUCHE = 4
OPENAI_WARTEZEITEN_SEKUNDEN = [2, 8, 20]

# Anzahl Bildkandidaten pro Fotografie-Zielkategorie, die nach der
# textbasierten Vorauswahl per Vision-Aufruf tatsaechlich beurteilt werden
# (Kostenkontrolle -- nicht das gesamte Archiv wird als Base64 verschickt).
SHORTLIST_SIZE_PER_CATEGORY = 4

SECTIONS = ["hero", "zitat", "reisen", "fotografie", "journal", "ueber-uns", "kontakt"]
COLLECTION_SECTIONS = ["reisen", "fotografie", "journal"]
SINGLETON_SECTIONS = ["hero", "zitat", "ueber-uns", "kontakt"]

FOTOGRAFIE_CATEGORIES = ["Natur", "Unterwegs", "Menschen", "Details"]

# Suffix-Muster fuer Medienprojekt-Textdateien im Content_Agent-Archiv.
# Der Praefix variiert pro Projekt (z.B. "Neues_Projekt_blog.txt",
# "Kuna _blog.txt", "Panama Canal_blog.txt") -- deshalb Suffix-Glob statt
# fester Dateiname.
PROJECT_TEXT_SUFFIXES = {
    "blog": "_blog.txt",
    "social": "_social.txt",
    "bildvorschlaege": "_bildvorschlaege.txt",
    "contentplan": "_contentplan.txt",
    "bericht": "_bericht.txt",
}

PROJECT_FIXED_FILES = {
    "kategorie": "kategorie.txt",
    "kontext": "kontext.txt",
    "projektname": "projektname.txt",
    "ort": "ort.txt",
    "ziel": "ziel.txt",
    "notizen": "notizen.txt",
}

PROJECT_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def resolve_openai_api_key():
    """Liest den API-Key zuerst aus der Umgebungsvariable, dann aus einer
    nicht versionierten lokalen Datei agent/.env.local (KEY=value)."""
    value = os.environ.get(OPENAI_API_KEY_ENV)
    if value:
        return value.strip()

    if LOCAL_ENV_FILE.is_file():
        for line in LOCAL_ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key.strip() == OPENAI_API_KEY_ENV:
                val = val.strip().strip('"').strip("'")
                if val:
                    return val

    return None


def resolve_openai_model():
    return os.environ.get(OPENAI_MODEL_ENV, DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
