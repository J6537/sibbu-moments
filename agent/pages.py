"""Erzeugt vollstaendige Beitragsseiten aus bereits vorhandenen, validierten
Inhalten in site-content.json:

- Reisen: nur Slot 1 (Position 1) -- das ist die einzige Karte im
  bestehenden Layout (index.html), die ueberhaupt ein Link-Element
  ('Geschichte lesen') besitzt. Fuer Karten 2-4 gibt es dort keinen
  Link-Slot, deshalb werden fuer sie keine Seiten erzeugt.
- Journal: alle drei Karten, jede besitzt ein Link-Element ('Weiterlesen').

Es wird hier nichts neu formuliert oder von einer KI erzeugt -- reine
Wiedergabe von Titel/Bild/Text, die bereits durch ai_output_validator.py
geprueft wurden. Seiten uebernehmen Kopf-/Fusszeile 1:1 aus dem bestehenden
Design (gleiche CSS-Klassen wie impressum.html/datenschutz.html), damit sich
Beitragsseiten optisch nahtlos einfuegen -- index.html/style.css/script.js
werden dabei nicht veraendert.
"""

import html
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from . import config

# Ab dieser body-Laenge gilt eine Geschichte als "vollstaendig genug" fuer
# eine eigene Beitragsseite. Kuerzere/keine body-Texte behalten nur die
# Kurzkarte auf der Startseite (kein Link, kein Absturz -- siehe
# content-schema.json journal.link_rules: inaktives 'Weiterlesen').
MIN_BODY_LEN_FOR_PAGE = 150

_CANONICAL_BASE = "https://j6537.github.io/sibbu-moments/"

_CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; "
    "script-src 'self'; connect-src 'self'; font-src 'self'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'; object-src 'none'"
)


class PageLogEntry:
    def __init__(self, area: str, item_id: str, path: str):
        self.area = area
        self.item_id = item_id
        self.path = path

    def to_dict(self):
        return {"area": self.area, "item_id": self.item_id, "path": self.path}


def _humanize_project(project_id: Optional[str]) -> str:
    if not project_id:
        return ""
    slug = project_id.split("/")[-1]
    return " ".join(w.capitalize() for w in slug.split("-") if w)


def _paragraphs(body: str) -> List[str]:
    body = (body or "").strip()
    if not body:
        return []
    parts = [p.strip() for p in body.split("\n\n") if p.strip()]
    if len(parts) <= 1:
        parts = [p.strip() for p in body.split("\n") if p.strip()]
    return parts or [body]


def _body_html(body: str) -> str:
    return "\n".join(f"          <p>{html.escape(p)}</p>" for p in _paragraphs(body))


def _page_shell(*, title: str, description: str, canonical_rel: str, favicon_ok: bool, eyebrow: str, content_html: str) -> str:
    safe_title = html.escape(title)
    safe_description = html.escape(description)
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{safe_title} — Sibbu Moments</title>
  <meta name="description" content="{safe_description}">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="{_CANONICAL_BASE}{canonical_rel}">

  <!-- Sicherheit: identisch zu index.html, GitHub Pages liefert keine eigenen HTTP-Header. -->
  <meta http-equiv="Content-Security-Policy" content="{_CSP}">
  <meta name="referrer" content="strict-origin-when-cross-origin">

  <!-- Favicon -->
  <link rel="icon" type="image/svg+xml" href="../assets/favicon.svg">
  <link rel="alternate icon" href="../assets/favicon.svg">

  <link rel="stylesheet" href="../css/style.css">
</head>
<body data-content-src="../data/site-content.json">

  <a class="skip-link" href="#main">Zum Hauptinhalt springen</a>

  <!-- ============ HEADER ============ -->
  <header class="site-header" id="site-header">
    <div class="container header-inner">
      <a href="../index.html" class="brand" aria-label="Sibbu Moments — Startseite">
        <svg class="brand-mark" width="34" height="34" viewBox="0 0 64 64" fill="none" aria-hidden="true">
          <circle cx="32" cy="24" r="8" fill="#E8A24B"/>
          <path d="M6 46 L22 28 L32 38 L42 24 L58 46 Z" fill="#F4EFE6"/>
        </svg>
        <span class="brand-name">Sibbu <em>Moments</em></span>
      </a>

      <nav class="main-nav" id="main-nav" aria-label="Hauptnavigation">
        <ul>
          <li><a href="../index.html#reisen">Reisen</a></li>
          <li><a href="../index.html#fotografie">Fotografie</a></li>
          <li><a href="../index.html#journal">Journal</a></li>
          <li><a href="../index.html#ueber-uns">Über uns</a></li>
          <li><a href="../index.html#kontakt">Kontakt</a></li>
        </ul>
      </nav>

      <div class="header-actions">
        <a href="../index.html#kontakt" class="btn btn-outline btn-small">Kontakt</a>
        <button class="nav-toggle" id="nav-toggle" aria-label="Menü öffnen" aria-expanded="false" aria-controls="main-nav">
          <span></span><span></span><span></span>
        </button>
      </div>
    </div>
  </header>

  <main id="main">
    <section class="section" id="{eyebrow.lower()}-artikel">
      <div class="container legal-content">
{content_html}
      </div>
    </section>
  </main>

  <!-- ============ FOOTER ============ -->
  <footer class="site-footer">
    <div class="container footer-inner">
      <div class="footer-brand">
        <a href="../index.html" class="brand" aria-label="Sibbu Moments — Startseite">
          <svg class="brand-mark" width="30" height="30" viewBox="0 0 64 64" fill="none" aria-hidden="true">
            <circle cx="32" cy="24" r="8" fill="#E8A24B"/>
            <path d="M6 46 L22 28 L32 38 L42 24 L58 46 Z" fill="#F4EFE6"/>
          </svg>
          <span class="brand-name">Sibbu <em>Moments</em></span>
        </a>
        <p>Reisen, Natur und Fotografie – echte Momente und Geschichten von unterwegs.</p>
      </div>

      <div class="footer-col">
        <h4>Entdecken</h4>
        <ul>
          <li><a href="../index.html#reisen">Reisen</a></li>
          <li><a href="../index.html#fotografie">Fotografie</a></li>
          <li><a href="../index.html#journal">Journal</a></li>
        </ul>
      </div>

      <div class="footer-col">
        <h4>Über</h4>
        <ul>
          <li><a href="../index.html#ueber-uns">Über uns</a></li>
          <li><a href="../index.html#kontakt">Kontakt</a></li>
        </ul>
      </div>
    </div>

    <div class="container footer-bottom">
      <p>© <span id="year"></span> Sibbu Moments. Alle Rechte vorbehalten. · <a href="../impressum.html">Impressum</a> · <a href="../datenschutz.html">Datenschutz</a></p>
      <button class="back-to-top" id="back-to-top" aria-label="Nach oben scrollen">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M12 19V5m0 0-6 6m6-6 6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
    </div>
  </footer>

  <script src="../js/script.js"></script>
</body>
</html>
"""


def _render_reisen_page(item: dict) -> str:
    title = item.get("title") or "Reisegeschichte"
    location = item.get("location") or ""
    image = item.get("image")
    image_alt = item.get("image_alt") or title
    quelle = _humanize_project(item.get("source_project"))

    image_html = ""
    if image:
        image_html = (
            f'          <img src="../{html.escape(image)}" alt="{html.escape(image_alt)}" '
            f'style="width:100%;height:auto;border-radius:16px;margin-bottom:2rem;">\n'
        )

    meta_bits = [b for b in [location, f"Aus dem Reisearchiv: {quelle}" if quelle else ""] if b]
    meta_html = ""
    if meta_bits:
        meta_html = f'          <p class="eyebrow">{html.escape(" · ".join(meta_bits))}</p>\n'

    content = (
        f'          <p class="eyebrow">Unterwegs</p>\n'
        f"{image_html}"
        f"          <h1>{html.escape(title)}</h1>\n"
        f"{meta_html}"
        f"{_body_html(item.get('body', ''))}\n"
        f'          <p><a href="../index.html#reisen" class="story-link">Zurück zu Reisen <span aria-hidden="true">→</span></a></p>'
    )

    return _page_shell(
        title=title,
        description=(item.get("excerpt") or title)[:160],
        canonical_rel=f"reisen/{item['id']}.html",
        favicon_ok=True,
        eyebrow="reisen",
        content_html=content,
    )


def _render_journal_page(item: dict) -> str:
    title = item.get("title") or "Journal-Eintrag"
    date = item.get("date") or ""
    quelle = _humanize_project(item.get("source_project"))
    source_file = item.get("source_file") or ""

    meta_bits = [b for b in [date, f"Notizen aus: {quelle}" if quelle else ""] if b]
    meta_html = ""
    if meta_bits:
        meta_html = f'          <p class="eyebrow">{html.escape(" · ".join(meta_bits))}</p>\n'

    quelle_hinweis = ""
    if quelle or source_file:
        quelle_hinweis = (
            f'          <p><em>Grundlage dieses Eintrags: eigene Reisenotizen'
            f'{" (" + html.escape(quelle) + ")" if quelle else ""}.</em></p>\n'
        )

    content = (
        f'          <p class="eyebrow">Journal</p>\n'
        f"          <h1>{html.escape(title)}</h1>\n"
        f"{meta_html}"
        f"{_body_html(item.get('body', ''))}\n"
        f"{quelle_hinweis}"
        f'          <p><a href="../index.html#journal" class="story-link">Zurück zum Journal <span aria-hidden="true">→</span></a></p>'
    )

    return _page_shell(
        title=title,
        description=(item.get("excerpt") or title)[:160],
        canonical_rel=f"journal/{item['id']}.html",
        favicon_ok=True,
        eyebrow="journal",
        content_html=content,
    )


def _archive_page_file(src: Path, timestamp: str):
    if not src.is_file():
        return
    archive_dir = src.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / f"{timestamp}-{src.name}"
    n = 2
    while dest.exists():
        dest = archive_dir / f"{timestamp}-{n}-{src.name}"
        n += 1
    shutil.move(str(src), str(dest))


def _qualifies(item: dict, require_published: bool) -> bool:
    if require_published and item.get("content_status") != "published":
        return False
    body = item.get("body") or ""
    return len(body) >= MIN_BODY_LEN_FOR_PAGE


def _sync_page(item: dict, area: str, timestamp: str, render_fn, require_published: bool, promote_journal: bool) -> Optional[PageLogEntry]:
    prefix = f"{area}/"
    target_rel = f"{area}/{item['id']}.html"
    old_link = item.get("link")

    qualifies = bool(item.get("id")) and bool(item.get("image") or area == "journal") and _qualifies(item, require_published)

    if not qualifies:
        if isinstance(old_link, str) and old_link.startswith(prefix) and old_link != target_rel:
            _archive_page_file(config.DOCS_DIR / old_link, timestamp)
        if isinstance(old_link, str) and old_link.startswith(prefix):
            item["link"] = None
        return None

    if isinstance(old_link, str) and old_link.startswith(prefix) and old_link != target_rel:
        _archive_page_file(config.DOCS_DIR / old_link, timestamp)

    html_text = render_fn(item)
    dest = config.DOCS_DIR / target_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html_text, encoding="utf-8")

    item["link"] = target_rel

    if promote_journal and item.get("content_status") != "published":
        now = datetime.now(timezone.utc)
        item["content_status"] = "published"
        item["date"] = now.strftime("%Y-%m-%d")
        item["published_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    return PageLogEntry(area, item["id"], target_rel)


def sync_pages(site_content: dict, timestamp: str) -> List[PageLogEntry]:
    """Erzeugt/aktualisiert Beitragsseiten fuer reisen-Slot 1 und alle
    Journal-Eintraege mit ausreichend langem body. Mutiert site_content
    (link / content_status / date / published_at) direkt in-place. Gibt die
    Liste tatsaechlich erzeugter/aktualisierter Seiten zurueck."""
    log: List[PageLogEntry] = []

    reisen_items = (site_content.get("reisen") or {}).get("items", [])
    if reisen_items:
        entry = _sync_page(reisen_items[0], "reisen", timestamp, _render_reisen_page, require_published=True, promote_journal=False)
        if entry:
            log.append(entry)

    journal_items = (site_content.get("journal") or {}).get("items", [])
    for item in journal_items:
        entry = _sync_page(item, "journal", timestamp, _render_journal_page, require_published=False, promote_journal=True)
        if entry:
            log.append(entry)

    return log
