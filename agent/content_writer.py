"""Setzt validierte KI-Entscheidungen technisch um:
Archivierung des Vorzustands (Content + Bild), Bildverarbeitung, Schreiben
von site-content.json und site-state.json.

Nichts wird hier verworfen/geloescht -- nur archiviert. Diese Funktionen
schreiben ausschliesslich innerhalb der in agent-interface.json erlaubten
Pfade.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from . import config, discover, images
from .ai_output_validator import Decision, ValidationResult


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _timestamp_for_filenames() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def slugify(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "item"


def _mint_unique_id(prefix: str, hint: str, used_ids: set) -> str:
    base = f"{prefix}-{slugify(hint)}"
    if base not in used_ids:
        return base
    n = 2
    while f"{base}-{n}" in used_ids:
        n += 1
    return f"{base}-{n}"


# Reisen- und Journal-Karten haben im festen HTML-Layout (index.html) je
# Slot ein data-content-id-Attribut, das NIE geaendert wird (index.html ist
# geschuetzt und wird vom Agenten nie beruehrt). Die Slot-Identitaet ist
# deshalb an die POSITION gebunden, nicht an die jeweilige Geschichte --
# genau wie bei fotografie (dort an die Kategorie). Wird hier stattdessen
# eine frisch gemintete ID vergeben, findet script.js beim naechsten Laden
# keinen passenden Slot mehr (idMap-Lookup ueber die ID schlaegt fehl) und
# zeigt weiterhin den urspruenglichen HTML-Fallback-Text/-SVG an, obwohl
# site-content.json laengst aktualisiert ist. Deshalb IMMER die feste
# Positions-ID verwenden, nie neu erzeugen.
REISEN_SLOT_IDS = {
    1: "reisen-panama-kuna-yala",
    2: "reisen-norwegen-fjorde",
    3: "reisen-marokko-sahara",
    4: "reisen-island-gletscher",
}
JOURNAL_SLOT_IDS = {
    1: "journal-wie-eine-reise-zur-geschichte-wird",
    2: "journal-leicht-packen-weit-kommen",
    3: "journal-licht-das-man-nicht-planen-kann",
}


def _archive_content_item(item: dict, section: str, timestamp: str):
    if not item:
        return
    section_dir = config.ARCHIVE_DATA_DIR / section
    section_dir.mkdir(parents=True, exist_ok=True)
    item_id = item.get("id", "unbekannt")
    dest = section_dir / f"{item_id}-{timestamp}.json"
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False, indent=2)


class WriteLogEntry:
    def __init__(self, area, slot_key, action, item_id, decision_basis, source_project=None, source_file=None):
        self.area = area
        self.slot_key = slot_key
        self.action = action
        self.item_id = item_id
        self.decision_basis = decision_basis
        self.source_project = source_project
        self.source_file = source_file

    def to_dict(self):
        return {
            "area": self.area,
            "slot_key": self.slot_key,
            "action": self.action,
            "item_id": self.item_id,
            "decision_basis": self.decision_basis,
            "source_project": self.source_project,
            "source_file": self.source_file,
        }


def _apply_hero(decision: Decision, projects, site_content, content_schema, timestamp, used_ids, provenance_updates, write_log):
    existing = site_content.get("hero") or {}
    project = discover.find_project_by_id(projects, decision.source_project)
    image = discover.find_image(project, decision.image_filename)

    content_schema_rules = images.get_section_image_rules(content_schema, "hero")
    basename = slugify(Path(decision.image_filename).stem)
    processed = images.process_image(image.path, content_schema_rules, basename)  # kann ImageUnsuitableError werfen -- Aufrufer faengt das ab

    _archive_content_item(existing, "hero", timestamp)
    archived_image = images.archive_existing_image(existing.get("image"), timestamp)

    new_item = dict(existing)
    new_item.update({
        "subtitle": decision.subtitle or existing.get("subtitle"),
        "excerpt": decision.excerpt or existing.get("excerpt"),
        "image": processed["image"],
        "image_mobile": processed["image_mobile"],
        "image_alt": decision.image_alt,
        "source_project": decision.source_project,
        "source_file": decision.image_filename,
        "updated_at": _now_iso(),
        "published_at": _now_iso(),
        "content_status": "published",
    })
    site_content["hero"] = new_item
    provenance_updates[processed["image"]] = {"source_project": decision.source_project, "source_file": decision.image_filename}
    if archived_image:
        write_log.append(WriteLogEntry("hero", None, "archived_previous_image", None, f"alte Bilddatei -> {archived_image}"))
    write_log.append(WriteLogEntry("hero", None, "update", new_item["id"], decision.decision_basis, decision.source_project, decision.image_filename))


def _apply_ueber_uns(decision: Decision, projects, site_content, content_schema, timestamp, used_ids, provenance_updates, write_log):
    existing = site_content.get("ueber-uns") or {}
    project = discover.find_project_by_id(projects, decision.source_project)
    image = discover.find_image(project, decision.image_filename)

    rules = images.get_section_image_rules(content_schema, "ueber-uns")
    basename = slugify(Path(decision.image_filename).stem)
    processed = images.process_image(image.path, rules, basename)  # kann ImageUnsuitableError werfen -- Aufrufer faengt das ab

    _archive_content_item(existing, "ueber-uns", timestamp)
    archived_image = images.archive_existing_image(existing.get("image"), timestamp)

    new_item = dict(existing)
    new_item.update({
        "body": decision.body,
        "image": processed["image"],
        "image_mobile": processed["image_mobile"],
        "image_alt": decision.image_alt,
        "source_project": decision.source_project,
        "source_file": decision.image_filename,
        "updated_at": _now_iso(),
        "published_at": _now_iso(),
        "content_status": "published",
    })
    site_content["ueber-uns"] = new_item
    provenance_updates[processed["image"]] = {"source_project": decision.source_project, "source_file": decision.image_filename}
    if archived_image:
        write_log.append(WriteLogEntry("ueber_uns", None, "archived_previous_image", None, f"alte Bilddatei -> {archived_image}"))
    write_log.append(WriteLogEntry("ueber_uns", None, "update", new_item["id"], decision.decision_basis, decision.source_project, decision.image_filename))


def _apply_reisen(decision: Decision, projects, site_content, content_schema, timestamp, used_ids, provenance_updates, write_log):
    items = site_content["reisen"]["items"]
    idx = decision.slot_key - 1
    existing = items[idx]
    project = discover.find_project_by_id(projects, decision.source_project)
    image = discover.find_image(project, decision.image_filename)

    rules = images.get_section_image_rules(content_schema, "reisen")
    basename = slugify(Path(decision.image_filename).stem)
    processed = images.process_image(image.path, rules, basename)  # kann ImageUnsuitableError werfen -- Aufrufer faengt das ab

    _archive_content_item(existing, "reisen", timestamp)
    archived_image = images.archive_existing_image(existing.get("image"), timestamp)

    new_id = REISEN_SLOT_IDS.get(decision.slot_key) or existing.get("id")
    used_ids.add(new_id)

    new_item = {
        "id": new_id,
        "section": "reisen",
        "title": decision.title,
        "subtitle": None,
        "excerpt": decision.excerpt,
        "body": decision.body,
        "location": decision.location,
        "date": None,
        "category": "reiseziel",
        "tags": [],
        "image": processed["image"],
        "image_mobile": processed["image_mobile"],
        "image_alt": decision.image_alt,
        "image_caption": None,
        "link": existing.get("link") if decision.slot_key == 1 else None,
        "featured": decision.slot_key == 1,
        "source_project": decision.source_project,
        "source_file": decision.image_filename,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "published_at": _now_iso(),
        "content_status": "published",
        "fallback_art": existing.get("fallback_art"),
    }
    items[idx] = new_item
    provenance_updates[processed["image"]] = {"source_project": decision.source_project, "source_file": decision.image_filename}
    if archived_image:
        write_log.append(WriteLogEntry("reisen", decision.slot_key, "archived_previous_image", existing.get("id"), f"alte Bilddatei -> {archived_image}"))
    write_log.append(WriteLogEntry("reisen", decision.slot_key, "replace", new_id, decision.decision_basis, decision.source_project, decision.image_filename))


def _apply_fotografie(decision: Decision, projects, site_content, content_schema, timestamp, used_ids, provenance_updates, write_log):
    items = site_content["fotografie"]["items"]
    idx = next(i for i, item in enumerate(items) if item.get("category") == decision.slot_key)
    existing = items[idx]
    project = discover.find_project_by_id(projects, decision.source_project)
    image = discover.find_image(project, decision.image_filename)

    rules = images.get_section_image_rules(content_schema, "fotografie", slot_position=idx + 1)
    basename = slugify(Path(decision.image_filename).stem)
    processed = images.process_image(image.path, rules, basename)  # kann ImageUnsuitableError werfen -- Aufrufer faengt das ab

    _archive_content_item(existing, "fotografie", timestamp)
    archived_image = images.archive_existing_image(existing.get("image"), timestamp)

    new_item = dict(existing)
    new_item.update({
        "image": processed["image"],
        "image_mobile": processed["image_mobile"],
        "image_alt": decision.image_alt,
        "source_project": decision.source_project,
        "source_file": decision.image_filename,
        "updated_at": _now_iso(),
        "published_at": _now_iso(),
        "content_status": "published",
    })
    items[idx] = new_item
    provenance_updates[processed["image"]] = {"source_project": decision.source_project, "source_file": decision.image_filename}
    if archived_image:
        write_log.append(WriteLogEntry("fotografie", decision.slot_key, "archived_previous_image", existing.get("id"), f"alte Bilddatei -> {archived_image}"))
    write_log.append(WriteLogEntry("fotografie", decision.slot_key, "replace", new_item["id"], decision.decision_basis, decision.source_project, decision.image_filename))


def _apply_journal(decision: Decision, site_content, timestamp, used_ids, write_log):
    items = site_content["journal"]["items"]
    idx = decision.slot_key - 1
    existing = items[idx]

    _archive_content_item(existing, "journal", timestamp)

    new_id = JOURNAL_SLOT_IDS.get(decision.slot_key) or existing.get("id")
    used_ids.add(new_id)

    new_item = {
        "id": new_id,
        "section": "journal",
        "title": decision.title,
        "subtitle": None,
        "excerpt": decision.excerpt,
        "body": decision.body,
        "location": None,
        "date": None,
        "category": None,
        "tags": [],
        "image": None,
        "image_mobile": None,
        "image_alt": None,
        "image_caption": None,
        "link": None,
        "featured": False,
        "source_project": decision.source_project,
        "source_file": decision.source_file_text,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "published_at": None,
        # Bleibt 'draft' bis pages.py (siehe run.py) erfolgreich eine echte
        # Beitragsseite erzeugt hat -- erst dann sinnvoll 'published' mit
        # echtem Link, sonst waere "Weiterlesen" irrefuehrend.
        "content_status": "draft",
        "fallback_art": None,
    }
    items[idx] = new_item
    write_log.append(WriteLogEntry("journal", decision.slot_key, "replace", new_id, decision.decision_basis, decision.source_project, decision.source_file_text))


def _collect_ids(site_content: dict) -> set:
    ids = set()
    for section in config.SINGLETON_SECTIONS + ["seo"]:
        item = site_content.get(section)
        if isinstance(item, dict) and item.get("id"):
            ids.add(item["id"])
    for section in config.COLLECTION_SECTIONS:
        wrapper = site_content.get(section)
        if isinstance(wrapper, dict):
            for item in wrapper.get("items", []):
                if item.get("id"):
                    ids.add(item["id"])
    return ids


def _collect_images(site_content: dict) -> list:
    paths = set()
    for section in config.SINGLETON_SECTIONS + ["seo"]:
        item = site_content.get(section)
        if isinstance(item, dict):
            for f in ("image", "image_mobile"):
                if item.get(f):
                    paths.add(item[f])
    for section in config.COLLECTION_SECTIONS:
        wrapper = site_content.get(section)
        if isinstance(wrapper, dict):
            for item in wrapper.get("items", []):
                for f in ("image", "image_mobile"):
                    if item.get(f):
                        paths.add(item[f])
    return sorted(paths)


def apply_decisions(
    validation_result: ValidationResult,
    projects: List,
    site_content: dict,
    site_state: dict,
    content_schema: dict,
):
    """Wendet alle nicht-'keep'-Entscheidungen an. Veraendert site_content
    und site_state in-place und gibt eine Liste von WriteLogEntry fuer den
    Abschlussbericht zurueck."""
    timestamp = _timestamp_for_filenames()
    used_ids = set(site_state.get("used_ids", [])) | _collect_ids(site_content)
    provenance_updates = {}
    write_log: List[WriteLogEntry] = []

    touched_sections = set()

    for decision in validation_result.decisions:
        try:
            if decision.area == "hero":
                _apply_hero(decision, projects, site_content, content_schema, timestamp, used_ids, provenance_updates, write_log)
                touched_sections.add("hero")
            elif decision.area == "ueber_uns":
                _apply_ueber_uns(decision, projects, site_content, content_schema, timestamp, used_ids, provenance_updates, write_log)
                touched_sections.add("ueber-uns")
            elif decision.area == "reisen":
                _apply_reisen(decision, projects, site_content, content_schema, timestamp, used_ids, provenance_updates, write_log)
                touched_sections.add("reisen")
            elif decision.area == "fotografie":
                _apply_fotografie(decision, projects, site_content, content_schema, timestamp, used_ids, provenance_updates, write_log)
                touched_sections.add("fotografie")
            elif decision.area == "journal":
                _apply_journal(decision, site_content, timestamp, used_ids, write_log)
                touched_sections.add("journal")
        except images.ImageUnsuitableError as exc:
            # Letztes Sicherheitsnetz (der Validator sollte das bereits
            # abgefangen haben) -- bestehender Inhalt bleibt unangetastet,
            # der Lauf wird nicht abgebrochen.
            validation_result.content_gaps.append(
                f"{decision.area} {decision.slot_key}: Bildverarbeitung abgelehnt ({exc}) -- bestehender Inhalt bleibt aktiv"
            )

    now = _now_iso()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    active_images = set(_collect_images(site_content))
    provenance = dict(site_state.get("image_provenance", {}))
    provenance.update(provenance_updates)
    provenance = {path: entry for path, entry in provenance.items() if path in active_images}

    site_state["last_updated"] = now
    site_state["last_checked"] = now
    site_state["active_content_ids"] = sorted(_collect_ids(site_content))
    site_state["active_image_files"] = sorted(active_images)
    site_state["used_ids"] = sorted(used_ids | _collect_ids(site_content))
    site_state["image_provenance"] = provenance

    section_last_changed = dict(site_state.get("section_last_changed", {}))
    for section in touched_sections:
        section_last_changed[section] = now
    site_state["section_last_changed"] = section_last_changed

    gaps = []
    for gap_text in validation_result.content_gaps:
        area = gap_text.split(":", 1)[0].strip() if ":" in gap_text else "allgemein"
        gaps.append({"area": area, "issue": gap_text, "since": today})
    site_state["known_content_gaps"] = gaps

    site_state["last_ai_decisions"] = {
        "run_at": now,
        "applied": [entry.to_dict() for entry in write_log if entry.action != "archived_previous_image"],
        "rejected": [
            {"area": r.area, "slot_key": r.slot_key, "reason": r.reason}
            for r in validation_result.rejected
        ],
    }

    site_state["content_source"] = "sibbu_content_agent_ai"
    touched_projects = sorted({d.source_project for d in validation_result.decisions if d.source_project})
    if touched_projects:
        site_state["used_project"] = ", ".join(touched_projects)

    return write_log


def save_site_files(site_content: dict, site_state: dict):
    """Schreibt site-content.json und site-state.json. Wird nur nach
    erfolgreicher Anwendung der Entscheidungen aufgerufen -- niemals im
    Dry-Run."""
    with open(config.CONTENT_FILE, "w", encoding="utf-8") as f:
        json.dump(site_content, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(site_state, f, ensure_ascii=False, indent=2)
        f.write("\n")
