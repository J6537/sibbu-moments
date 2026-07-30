"""Laedt den aktuellen Zustand der Website (site-content.json, site-state.json,
content-schema.json, agent-interface.json) als Kontext fuer die KI-Redaktion
und fuer die technische Validierung."""

import json
from pathlib import Path

from . import config


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_site_content() -> dict:
    return load_json(config.CONTENT_FILE)


def load_site_state() -> dict:
    return load_json(config.STATE_FILE)


def load_content_schema() -> dict:
    return load_json(config.SCHEMA_FILE)


def load_agent_interface() -> dict:
    return load_json(config.AGENT_INTERFACE_FILE)


def iter_all_items(site_content: dict):
    """Liefert (section, item_dict) fuer alle Eintraege in allen Bereichen,
    unabhaengig davon ob Singleton oder Collection."""
    for section in config.SINGLETON_SECTIONS:
        item = site_content.get(section)
        if isinstance(item, dict):
            yield section, item

    for section in config.COLLECTION_SECTIONS:
        wrapper = site_content.get(section)
        if isinstance(wrapper, dict) and isinstance(wrapper.get("items"), list):
            for item in wrapper["items"]:
                if isinstance(item, dict):
                    yield section, item


def collect_active_images(site_content: dict) -> set:
    """Alle aktuell in site-content.json referenzierten Bildpfade (image +
    image_mobile), unabhaengig vom Buchfuehrungsfeld in site-state.json --
    das ist die verbindliche Quelle fuer Dublettenpruefung."""
    images = set()
    for _section, item in iter_all_items(site_content):
        for field in ("image", "image_mobile"):
            value = item.get(field)
            if isinstance(value, str) and value.strip():
                images.add(value.strip())
    return images


def build_ai_context(site_content: dict, site_state: dict) -> dict:
    """Kompakte Zusammenfassung des aktuellen Website-Zustands fuer den
    KI-Prompt: was ist in jedem Slot aktuell drin, welche Bilder/Projekte
    sind schon verwendet, welche Luecken sind bekannt."""

    def summarize(item: dict) -> dict:
        return {
            "id": item.get("id"),
            "title": item.get("title"),
            "location": item.get("location"),
            "category": item.get("category"),
            "excerpt": item.get("excerpt"),
            "image": item.get("image"),
            "image_alt": item.get("image_alt"),
            "content_status": item.get("content_status"),
            "source_project": item.get("source_project"),
            "source_file": item.get("source_file"),
        }

    sections_summary = {}
    for section in config.SINGLETON_SECTIONS:
        item = site_content.get(section)
        if isinstance(item, dict):
            sections_summary[section] = summarize(item)

    for section in config.COLLECTION_SECTIONS:
        wrapper = site_content.get(section)
        if isinstance(wrapper, dict) and isinstance(wrapper.get("items"), list):
            sections_summary[section] = [summarize(i) for i in wrapper["items"]]

    return {
        "current_sections": sections_summary,
        "active_image_paths": sorted(collect_active_images(site_content)),
        "known_content_gaps": site_state.get("known_content_gaps", []),
        "processed_sources": site_state.get("processed_sources", {}),
    }
