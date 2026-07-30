#!/usr/bin/env python3
"""
validate_site.py — Lokales Prüfskript für die Sibbu-Moments-Website.

Prüft docs/data/site-content.json gegen docs/data/content-schema.json sowie
allgemeine Sicherheits- und Konsistenzregeln, BEVOR der lokale
Website-Pflege-Agent Änderungen veröffentlicht oder committet. Verändert und
veröffentlicht nichts selbst — reines Read-only-Prüfskript.

Nutzung:
    python3 tools/validate_site.py

Exit-Codes:
    0  -> Alle Prüfungen bestanden. Commit/Push darf fortgesetzt werden.
    1  -> Mindestens ein Fehler gefunden. Kein Commit, kein Push.

Nur Python-Standardbibliothek, keine externen Abhängigkeiten.
"""

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
DATA_DIR = DOCS_DIR / "data"
INDEX_HTML = DOCS_DIR / "index.html"

CONTENT_FILE = DATA_DIR / "site-content.json"
SCHEMA_FILE = DATA_DIR / "content-schema.json"
STATE_FILE = DATA_DIR / "site-state.json"
AGENT_INTERFACE_FILE = DATA_DIR / "agent-interface.json"

SINGLETON_SECTIONS = ["hero", "zitat", "ueber-uns", "kontakt", "seo"]
COLLECTION_SECTIONS = ["reisen", "fotografie", "journal"]

TEXT_FIELDS_TO_SCAN = ["title", "subtitle", "excerpt", "body", "location", "category"]


class Report:
    """Sammelt Fehler und Warnungen und druckt am Ende einen Bericht."""

    def __init__(self):
        self.errors = []
        self.warnings = []
        self.checks_run = 0

    def error(self, message):
        self.errors.append(message)

    def warn(self, message):
        self.warnings.append(message)

    def check(self, label, ok, message_if_fail, is_error=True):
        self.checks_run += 1
        if not ok:
            if is_error:
                self.error("{}: {}".format(label, message_if_fail))
            else:
                self.warn("{}: {}".format(label, message_if_fail))

    def print_summary(self):
        print("=" * 70)
        print("Sibbu Moments — Website-Prüfbericht")
        print("=" * 70)
        print("Durchgeführte Einzelprüfungen: {}".format(self.checks_run))
        print("Fehler: {}".format(len(self.errors)))
        print("Warnungen: {}".format(len(self.warnings)))
        print("")

        if self.errors:
            print("FEHLER (blockieren Commit/Push):")
            for i, msg in enumerate(self.errors, 1):
                print("  {}. {}".format(i, msg))
            print("")

        if self.warnings:
            print("WARNUNGEN (nicht blockierend, bitte prüfen):")
            for i, msg in enumerate(self.warnings, 1):
                print("  {}. {}".format(i, msg))
            print("")

        if not self.errors:
            print("ERGEBNIS: OK — alle Pflichtprüfungen bestanden.")
        else:
            print("ERGEBNIS: FEHLGESCHLAGEN — bitte Fehler beheben, bevor veröffentlicht wird.")
        print("=" * 70)


def load_json(path, report):
    if not path.is_file():
        report.error("Datei fehlt: {}".format(rel(path)))
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        report.error("Ungültiges JSON in {}: {}".format(rel(path), exc))
        return None


def rel(path):
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def is_within_docs(path: Path) -> bool:
    try:
        path.resolve().relative_to(DOCS_DIR.resolve())
        return True
    except ValueError:
        return False


def get_all_ids_and_items(content, report):
    """Liefert eine flache Liste von (id, section, item_dict) über alle Bereiche."""
    entries = []

    for section in SINGLETON_SECTIONS:
        item = content.get(section)
        if item is None:
            continue
        if not isinstance(item, dict):
            report.error("Bereich '{}' in site-content.json ist kein Objekt.".format(section))
            continue
        entries.append((item.get("id"), section, item))

    for section in COLLECTION_SECTIONS:
        wrapper = content.get(section)
        if wrapper is None:
            continue
        if not isinstance(wrapper, dict) or not isinstance(wrapper.get("items"), list):
            report.error("Bereich '{}' in site-content.json besitzt kein gültiges 'items'-Array.".format(section))
            continue
        for item in wrapper["items"]:
            if not isinstance(item, dict):
                report.error("Ein Eintrag in '{}' ist kein Objekt.".format(section))
                continue
            entries.append((item.get("id"), section, item))

    return entries


def check_duplicate_ids(entries, report):
    seen = {}
    for content_id, section, _item in entries:
        if not content_id:
            report.error("Ein Eintrag in Bereich '{}' hat keine 'id'.".format(section))
            continue
        if content_id in seen:
            report.error(
                "Doppelte Content-ID '{}' (Bereiche: {} und {}).".format(content_id, seen[content_id], section)
            )
        else:
            seen[content_id] = section


def check_id_pattern(entries, schema, report):
    pattern = schema.get("id_pattern") if schema else None
    if not pattern:
        return
    compiled = re.compile(pattern)
    for content_id, section, _item in entries:
        if content_id and not compiled.match(content_id):
            report.error("Content-ID '{}' ({}) entspricht nicht dem erlaubten Muster '{}'.".format(content_id, section, pattern))


def check_fixed_item_counts(content, schema, report):
    sections_schema = schema.get("sections", {}) if schema else {}
    for section in COLLECTION_SECTIONS:
        wrapper = content.get(section)
        if not isinstance(wrapper, dict) or not isinstance(wrapper.get("items"), list):
            continue
        rules = sections_schema.get(section, {})
        expected = rules.get("fixed_item_count")
        if expected is None:
            continue
        actual = len(wrapper["items"])
        report.check(
            "Anzahl Einträge '{}'".format(section),
            actual == expected,
            "erwartet {} Einträge (festes Layout), gefunden {}.".format(expected, actual),
        )


def check_required_and_lengths(content, schema, report):
    common_required_default = ["id", "section", "content_status"]
    sections_schema = schema.get("sections", {}) if schema else {}

    def check_item(item, section, label):
        rules = sections_schema.get(section, {})
        required = rules.get("required_fields", common_required_default)
        for field in required:
            value = item.get(field)
            missing = value is None or (isinstance(value, str) and not value.strip())
            report.check(
                "Pflichtfeld '{}' in {}".format(field, label),
                not missing,
                "Feld ist leer oder fehlt.",
            )

        for len_key, field in (
            ("title_max_len", "title"),
            ("subtitle_max_len", "subtitle"),
            ("location_max_len", "location"),
        ):
            max_len = rules.get(len_key)
            value = item.get(field)
            if max_len and isinstance(value, str) and len(value) > max_len:
                report.error("{}: Feld '{}' ist {} Zeichen lang (Maximum {}).".format(label, field, len(value), max_len))

        for field, min_key, max_key in (
            ("excerpt", "excerpt_min_len", "excerpt_max_len"),
            ("body", "body_min_len", "body_max_len"),
        ):
            value = item.get(field)
            min_len = rules.get(min_key)
            max_len = rules.get(max_key)
            if isinstance(value, str):
                if max_len and len(value) > max_len:
                    report.error("{}: Feld '{}' ist {} Zeichen lang (Maximum {}).".format(label, field, len(value), max_len))
                if min_len and value.strip() and len(value) < min_len:
                    report.warn("{}: Feld '{}' ist mit {} Zeichen kürzer als empfohlen (Minimum {}).".format(label, field, len(value), min_len))

        allowed_categories = rules.get("allowed_categories")
        if allowed_categories and item.get("category") and item.get("category") not in allowed_categories:
            report.error(
                "{}: Kategorie '{}' ist nicht erlaubt (erlaubt: {}).".format(label, item.get("category"), ", ".join(allowed_categories))
            )

        image_alt_required = rules.get("image_alt_required") or (
            isinstance(rules.get("image"), dict) and True
        )
        if item.get("image") and image_alt_required:
            alt = item.get("image_alt")
            report.check(
                "Alt-Text für Bild in {}".format(label),
                bool(alt and str(alt).strip()),
                "Bild ist gesetzt, aber 'image_alt' fehlt oder ist leer (Pflicht laut Schema).",
            )

    for section in SINGLETON_SECTIONS:
        item = content.get(section)
        if isinstance(item, dict):
            check_item(item, section, "'{}'".format(section))

    for section in COLLECTION_SECTIONS:
        wrapper = content.get(section)
        if isinstance(wrapper, dict) and isinstance(wrapper.get("items"), list):
            for item in wrapper["items"]:
                if isinstance(item, dict):
                    check_item(item, section, "'{}' (id={})".format(section, item.get("id", "?")))


def check_forbidden_text_patterns(entries, schema, report):
    security = schema.get("security_rules", {}) if schema else {}
    patterns = security.get("forbidden_patterns_in_text", [])
    if not patterns:
        return
    lowered_patterns = [p.lower() for p in patterns]

    for content_id, section, item in entries:
        for field in TEXT_FIELDS_TO_SCAN:
            value = item.get(field)
            if not isinstance(value, str):
                continue
            lowered = value.lower()
            for pattern in lowered_patterns:
                if pattern in lowered:
                    report.error(
                        "Verdächtiger Inhalt in Feld '{}' von '{}' ({}): enthält '{}'.".format(
                            field, content_id or "?", section, pattern
                        )
                    )


def resolve_docs_path(raw_path):
    """Löst einen im JSON angegebenen Pfad relativ zu docs/ auf. Gibt None
    zurück, wenn der Pfad unsicher ist (absolut, Protokoll, '..')."""
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    value = raw_path.strip()
    if value.startswith("/") or "://" in value or ".." in value:
        return None
    if re.match(r"^[a-z][a-z0-9+.-]*:", value, re.IGNORECASE):
        return None
    return (DOCS_DIR / value).resolve()


def check_images(entries, schema, report):
    allowed_ext = set()
    common_rules = schema.get("image_rules_common", {}) if schema else {}
    for ext in common_rules.get("allowed_formats", []):
        allowed_ext.add("." + ext.lower())

    allowed_prefixes = common_rules.get("allowed_path_prefixes", [])
    default_max_kb = common_rules.get("max_file_size_kb_default", 500)
    sections_schema = schema.get("sections", {}) if schema else {}

    seen_images = {}

    for content_id, section, item in entries:
        if section == "seo":
            # SEO-Bild ist die statische OG-Grafik unter assets/ (manuell
            # gepflegt, siehe content-schema.json 'seo.manual_only') und
            # unterliegt nicht der Bildpipeline für Content-Fotos.
            continue
        for field in ("image", "image_mobile"):
            raw = item.get(field)
            if raw is None:
                continue
            if not isinstance(raw, str) or not raw.strip():
                report.error("'{}' ({}): Feld '{}' ist gesetzt, aber kein gültiger String.".format(content_id, section, field))
                continue

            value = raw.strip()

            has_allowed_prefix = any(value.startswith(p) for p in allowed_prefixes) if allowed_prefixes else True
            report.check(
                "Bildpfad-Ordner für {} ({})".format(field, content_id),
                has_allowed_prefix,
                "Pfad '{}' liegt außerhalb der erlaubten Ordner {}.".format(value, allowed_prefixes),
            )

            ext = os.path.splitext(value)[1].lower()
            report.check(
                "Dateiendung für {} ({})".format(field, content_id),
                ext in allowed_ext,
                "Endung '{}' ist nicht erlaubt (erlaubt: {}).".format(ext, sorted(allowed_ext)),
            )

            resolved = resolve_docs_path(value)
            report.check(
                "Pfad-Sicherheit für {} ({})".format(field, content_id),
                resolved is not None and is_within_docs(resolved),
                "Pfad '{}' verlässt das docs/-Verzeichnis oder enthält ein Protokoll/'..'.".format(value),
            )

            if resolved is None:
                continue

            report.check(
                "Bilddatei vorhanden ({} von {})".format(field, content_id),
                resolved.is_file(),
                "Referenzierte Datei '{}' existiert nicht.".format(rel(resolved) if resolved else value),
            )

            if resolved.is_file():
                size_kb = resolved.stat().st_size / 1024.0
                section_rules = sections_schema.get(section, {})
                image_rules = section_rules.get("image", {}) if isinstance(section_rules.get("image"), dict) else {}
                max_kb = image_rules.get("max_file_size_kb") or section_rules.get("max_file_size_kb") or default_max_kb
                report.check(
                    "Dateigröße ({} von {})".format(field, content_id),
                    size_kb <= max_kb,
                    "{:.0f} KB überschreitet das Limit von {} KB.".format(size_kb, max_kb),
                )

                key = str(resolved)
                if key in seen_images:
                    report.error(
                        "Bild '{}' wird mehrfach verwendet ({} und {}) — laut Schema nicht erlaubt.".format(
                            value, seen_images[key], "{} ({})".format(content_id, field)
                        )
                    )
                else:
                    seen_images[key] = "{} ({})".format(content_id, field)


def get_html_ids(html_text):
    return set(re.findall(r'id=["\']([^"\']+)["\']', html_text))


def check_links(entries, html_ids, report):
    for content_id, section, item in entries:
        link = item.get("link")
        if link is None:
            continue
        if not isinstance(link, str) or not link.strip():
            report.error("'{}' ({}): Feld 'link' ist gesetzt, aber kein gültiger String.".format(content_id, section))
            continue

        value = link.strip()

        if value == "#":
            report.warn("'{}' ({}): 'link' ist der Platzhalter '#' — wird von script.js als kein Link behandelt.".format(content_id, section))
            continue

        if value.startswith("#"):
            anchor = value[1:]
            report.check(
                "Interner Anker-Link von '{}'".format(content_id),
                anchor in html_ids,
                "Anker '#{}' existiert in keiner id= in index.html.".format(anchor),
            )
        elif value.startswith("mailto:"):
            report.check(
                "mailto-Link von '{}'".format(content_id),
                len(value) > len("mailto:"),
                "mailto-Link ohne Adresse.",
            )
        elif value.startswith("https://"):
            pass  # Kein Netzwerkzugriff im Prüfskript; Protokoll ist erlaubt.
        elif re.match(r"^[a-z][a-z0-9+.-]*:", value, re.IGNORECASE) or value.startswith("//"):
            report.error("'{}' ({}): Link-Protokoll von '{}' ist nicht erlaubt.".format(content_id, section, value))
        elif value.startswith("/") or ".." in value:
            report.error("'{}' ({}): Link '{}' ist absolut oder verlässt das docs/-Verzeichnis.".format(content_id, section, value))
        else:
            target = (DOCS_DIR / value.split("#")[0]).resolve()
            report.check(
                "Interner relativer Link von '{}'".format(content_id),
                is_within_docs(target) and target.is_file(),
                "Zieldatei '{}' existiert nicht relativ zu docs/.".format(value),
            )


def check_agent_interface(report):
    data = load_json(AGENT_INTERFACE_FILE, report)
    if data is None:
        return
    for key in ("allowed_write_paths", "protected_paths", "allowed_content_sections"):
        report.check(
            "agent-interface.json Feld '{}'".format(key),
            key in data,
            "erforderliches Feld fehlt.",
        )


def check_site_state(report):
    data = load_json(STATE_FILE, report)
    if data is None:
        return
    for key in ("active_content_ids", "known_content_gaps", "publish_status"):
        report.check(
            "site-state.json Feld '{}'".format(key),
            key in data,
            "erforderliches Feld fehlt.",
        )


def main():
    report = Report()

    if not DOCS_DIR.is_dir():
        report.error("docs/-Verzeichnis nicht gefunden unter {}.".format(DOCS_DIR))
        report.print_summary()
        return 1

    schema = load_json(SCHEMA_FILE, report)
    content = load_json(CONTENT_FILE, report)

    if not INDEX_HTML.is_file():
        report.error("docs/index.html nicht gefunden.")
        html_ids = set()
    else:
        html_ids = get_html_ids(INDEX_HTML.read_text(encoding="utf-8"))

    check_agent_interface(report)
    check_site_state(report)

    if content is not None and schema is not None:
        entries = get_all_ids_and_items(content, report)
        check_duplicate_ids(entries, report)
        check_id_pattern(entries, schema, report)
        check_fixed_item_counts(content, schema, report)
        check_required_and_lengths(content, schema, report)
        check_forbidden_text_patterns(entries, schema, report)
        check_images(entries, schema, report)
        check_links(entries, html_ids, report)

    report.print_summary()
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
