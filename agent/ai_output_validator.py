"""Technische Nachpruefung der KI-Ausgabe (Stufe 2, editorial_output).

Unabhaengig von der API-seitigen JSON-Schema-Erzwingung wird hier jeder
einzelne Vorschlag hart gegengeprueft: existiert das referenzierte Projekt/
Bild wirklich, halten Texte die Laengengrenzen aus content-schema.json ein,
und kollidiert kein Bild mit einem bereits anderswo aktiven Slot.

Ein ungueltiger Einzelvorschlag wird verworfen (rejected) und als
Content-Luecke vermerkt -- der Rest des Laufs wird davon nicht beeinflusst.
Ergebnis sind "Entscheidungen" (decisions), noch OHNE finalen Bildpfad --
die Bildverarbeitung und das eigentliche Schreiben uebernehmen images.py
und content_writer.py erst danach.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from . import discover, images

# content-schema.json definiert fuer reisen/journal keine body_max_len (dort
# bislang nicht vorgesehenes Feld) -- eigene, grosszuegige Obergrenze fuer
# den laengeren Beitragsseiten-Text, rein als Sicherheitsnetz gegen
# ausufernden Text. Ein zu kurzer/fehlender body blockiert die Entscheidung
# NICHT (die Karte wird trotzdem aktualisiert) -- er fuehrt nur dazu, dass
# pages.py fuer diesen Slot keine Beitragsseite erzeugt.
ARTICLE_BODY_MAX_LEN = 2200


@dataclass
class Decision:
    area: str  # "hero" | "reisen" | "fotografie" | "journal"
    slot_key: Union[int, str, None]  # reisen: Position 1-4, fotografie: Kategorie, journal: Position 1-3, hero: None
    action: str  # "update" | "replace" | "keep"
    source_project: Optional[str] = None
    image_filename: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    location: Optional[str] = None
    excerpt: Optional[str] = None
    body: Optional[str] = None
    image_alt: Optional[str] = None
    source_file_text: Optional[str] = None
    decision_basis: str = ""


@dataclass
class Rejection:
    area: str
    slot_key: Union[int, str, None]
    reason: str
    raw: dict


@dataclass
class ValidationResult:
    decisions: List[Decision] = field(default_factory=list)
    rejected: List[Rejection] = field(default_factory=list)
    content_gaps: List[str] = field(default_factory=list)


def _section_rules(content_schema: dict, section: str) -> dict:
    return content_schema.get("sections", {}).get(section, {})


def _len_ok(value: Optional[str], max_len: Optional[int]) -> bool:
    if not max_len or not isinstance(value, str):
        return True
    return len(value) <= max_len


def _nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _resolve_image(projects, source_project, image_filename):
    if not source_project or not image_filename:
        return None, None
    project = discover.find_project_by_id(projects, source_project)
    if project is None:
        return None, None
    image = discover.find_image(project, image_filename)
    if image is None:
        return None, None
    return project, image


def _geometry_reason(image, target_ratio: Optional[float]) -> Optional[str]:
    """Prueft, ob das Bild (nach EXIF-Korrektur) fuer das Ziel-Seitenverhaeltnis
    geeignet ist -- OHNE das Bild tatsaechlich zu verarbeiten. Gibt eine
    Ablehnungsbegruendung zurueck, oder None wenn geeignet. Verhindert, dass
    ein geometrisch unpassendes Bild (z.B. Hochformat-Portraet fuer einen
    breiten Slot) ueberhaupt als Entscheidung akzeptiert wird."""
    if target_ratio is None:
        return None
    if not image.width or not image.height:
        return "Bildmasse konnten nicht gelesen werden (Datei evtl. beschaedigt)"
    if not images.is_suitable_for_ratio((image.width, image.height), target_ratio):
        retain = images.crop_retain_fraction((image.width, image.height), target_ratio)
        return (
            f"Bildausrichtung ({image.width}x{image.height}) passt nicht zum Slot-Seitenverhaeltnis "
            f"{target_ratio:.2f} (nur {retain:.0%} der Kante bliebe erhalten, Minimum {images.MIN_RETAIN_FRACTION:.0%})"
        )
    return None


def _fotografie_category_positions(site_content: dict) -> Dict[str, int]:
    positions = {}
    items = (site_content.get("fotografie") or {}).get("items", [])
    for idx, item in enumerate(items, start=1):
        category = item.get("category")
        if category:
            positions[category] = idx
    return positions


def _combined_provenance(site_content: dict, site_state: dict) -> Dict[tuple, tuple]:
    """Liefert EINE gemeinsame Zuordnung ueber ALLE Bereiche hinweg:
    (area, slot_key) -> (source_project, source_file) fuer jeden aktuell
    aktiven Slot, dessen Bild aus einem frueheren Agentenlauf stammt
    (site-state.json -> image_provenance).

    Wichtig: Die Dublettenpruefung muss bereichsuebergreifend erfolgen (ein
    Bild darf nicht gleichzeitig in reisen UND fotografie aktiv sein) --
    deshalb EINE gemeinsame Map statt einer pro Bereich."""
    provenance_map = site_state.get("image_provenance", {})
    result = {}

    hero_item = site_content.get("hero") or {}
    hero_img = hero_item.get("image")
    if hero_img and hero_img in provenance_map:
        entry = provenance_map[hero_img]
        result[("hero", None)] = (entry.get("source_project"), entry.get("source_file"))

    reisen_items = (site_content.get("reisen") or {}).get("items", [])
    for idx, item in enumerate(reisen_items, start=1):
        img = item.get("image")
        if img and img in provenance_map:
            entry = provenance_map[img]
            result[("reisen", idx)] = (entry.get("source_project"), entry.get("source_file"))

    fotografie_items = (site_content.get("fotografie") or {}).get("items", [])
    for item in fotografie_items:
        category = item.get("category")
        img = item.get("image")
        if category and img and img in provenance_map:
            entry = provenance_map[img]
            result[("fotografie", category)] = (entry.get("source_project"), entry.get("source_file"))

    return result


def _check_duplicate(key: tuple, own_slot: tuple, provenance: Dict[tuple, tuple], claimed: Dict[tuple, tuple]) -> Optional[str]:
    """Prueft 'key' (source_project, image_filename) bereichsuebergreifend
    gegen alle bereits in diesem Lauf vergebenen Bilder (claimed) UND gegen
    alle aktuell aktiven Slots (provenance) -- ausser dem eigenen Slot.
    Gibt eine Fehlerbeschreibung zurueck, oder None wenn alles ok ist."""
    if key in claimed and claimed[key] != own_slot:
        other_area, other_slot = claimed[key]
        return f"Bild wird in diesem Lauf bereits fuer {other_area}:{other_slot} verwendet"

    if provenance.get(own_slot) != key:
        for slot, source in provenance.items():
            if slot != own_slot and source == key:
                return f"Bild ist bereits aktiv in Slot {slot[0]}:{slot[1]}"

    return None


def _validate_hero(entry: dict, projects, content_schema, provenance, claimed, result: ValidationResult):
    action = entry.get("action")
    if action != "update":
        return

    project, image = _resolve_image(projects, entry.get("source_project"), entry.get("image_filename"))
    if project is None or image is None:
        result.rejected.append(Rejection("hero", None, "source_project/image_filename nicht im Archiv auffindbar", entry))
        result.content_gaps.append("hero: KI-Vorschlag verworfen (Bildreferenz nicht auffindbar)")
        return

    rules = _section_rules(content_schema, "hero")

    image_rules = images.get_section_image_rules(content_schema, "hero")
    geometry_reason = _geometry_reason(image, images.target_ratio_for_rules(image_rules) if image_rules else None)
    if geometry_reason:
        result.rejected.append(Rejection("hero", None, geometry_reason, entry))
        result.content_gaps.append(f"hero: KI-Vorschlag verworfen ({geometry_reason}) -- bestehender Inhalt bleibt aktiv")
        return

    if not _len_ok(entry.get("subtitle"), rules.get("subtitle_max_len")):
        result.rejected.append(Rejection("hero", None, "subtitle ueberschreitet subtitle_max_len", entry))
        result.content_gaps.append("hero: KI-Vorschlag verworfen (subtitle zu lang)")
        return
    if not _len_ok(entry.get("excerpt"), rules.get("excerpt_max_len")):
        result.rejected.append(Rejection("hero", None, "excerpt ueberschreitet excerpt_max_len", entry))
        result.content_gaps.append("hero: KI-Vorschlag verworfen (excerpt zu lang)")
        return
    if not _nonempty(entry.get("image_alt")):
        result.rejected.append(Rejection("hero", None, "image_alt fehlt (Pflicht sobald Bild gesetzt)", entry))
        result.content_gaps.append("hero: KI-Vorschlag verworfen (image_alt fehlt)")
        return

    key = (entry.get("source_project"), entry.get("image_filename"))
    own_slot = ("hero", None)
    dup_reason = _check_duplicate(key, own_slot, provenance, claimed)
    if dup_reason:
        result.rejected.append(Rejection("hero", None, dup_reason, entry))
        result.content_gaps.append(f"hero: KI-Vorschlag verworfen ({dup_reason})")
        return

    claimed[key] = own_slot
    result.decisions.append(Decision(
        area="hero", slot_key=None, action="update",
        source_project=entry.get("source_project"), image_filename=entry.get("image_filename"),
        subtitle=entry.get("subtitle"), excerpt=entry.get("excerpt"), image_alt=entry.get("image_alt"),
        decision_basis=entry.get("decision_basis", ""),
    ))


def _validate_reisen(entries: List[dict], projects, content_schema, provenance, claimed, result: ValidationResult):
    rules = _section_rules(content_schema, "reisen")
    reisen_image_rules = images.get_section_image_rules(content_schema, "reisen")
    reisen_ratio = images.target_ratio_for_rules(reisen_image_rules) if reisen_image_rules else None
    seen_positions = set()

    for entry in entries:
        position = entry.get("position")
        action = entry.get("action")

        if not isinstance(position, int) or not (1 <= position <= 4):
            result.rejected.append(Rejection("reisen", position, "ungueltige Position (muss 1-4 sein)", entry))
            continue
        if position in seen_positions:
            result.rejected.append(Rejection("reisen", position, "Position mehrfach in KI-Ausgabe", entry))
            continue
        seen_positions.add(position)

        if action != "replace":
            continue

        project, image = _resolve_image(projects, entry.get("source_project"), entry.get("image_filename"))
        if project is None or image is None:
            result.rejected.append(Rejection("reisen", position, "source_project/image_filename nicht im Archiv auffindbar", entry))
            result.content_gaps.append(f"reisen Position {position}: KI-Vorschlag verworfen (Bildreferenz nicht auffindbar)")
            continue

        geometry_reason = _geometry_reason(image, reisen_ratio)
        if geometry_reason:
            result.rejected.append(Rejection("reisen", position, geometry_reason, entry))
            result.content_gaps.append(f"reisen Position {position}: KI-Vorschlag verworfen ({geometry_reason}) -- bestehender Inhalt bleibt aktiv")
            continue

        if not _nonempty(entry.get("title")) or not _len_ok(entry.get("title"), rules.get("title_max_len")):
            result.rejected.append(Rejection("reisen", position, "title fehlt oder zu lang", entry))
            result.content_gaps.append(f"reisen Position {position}: KI-Vorschlag verworfen (title ungueltig)")
            continue
        if not _nonempty(entry.get("location")) or not _len_ok(entry.get("location"), rules.get("location_max_len")):
            result.rejected.append(Rejection("reisen", position, "location fehlt oder zu lang", entry))
            result.content_gaps.append(f"reisen Position {position}: KI-Vorschlag verworfen (location ungueltig)")
            continue
        if not _nonempty(entry.get("excerpt")) or not _len_ok(entry.get("excerpt"), rules.get("excerpt_max_len")):
            result.rejected.append(Rejection("reisen", position, "excerpt fehlt oder zu lang", entry))
            result.content_gaps.append(f"reisen Position {position}: KI-Vorschlag verworfen (excerpt ungueltig)")
            continue
        if not _nonempty(entry.get("image_alt")):
            result.rejected.append(Rejection("reisen", position, "image_alt fehlt", entry))
            result.content_gaps.append(f"reisen Position {position}: KI-Vorschlag verworfen (image_alt fehlt)")
            continue
        if not _len_ok(entry.get("body"), ARTICLE_BODY_MAX_LEN):
            result.rejected.append(Rejection("reisen", position, "body ueberschreitet ARTICLE_BODY_MAX_LEN", entry))
            result.content_gaps.append(f"reisen Position {position}: KI-Vorschlag verworfen (body zu lang)")
            continue

        key = (entry.get("source_project"), entry.get("image_filename"))
        own_slot = ("reisen", position)
        dup_reason = _check_duplicate(key, own_slot, provenance, claimed)
        if dup_reason:
            result.rejected.append(Rejection("reisen", position, dup_reason, entry))
            result.content_gaps.append(f"reisen Position {position}: KI-Vorschlag verworfen ({dup_reason})")
            continue

        claimed[key] = own_slot
        body = entry.get("body") if _nonempty(entry.get("body")) else None
        result.decisions.append(Decision(
            area="reisen", slot_key=position, action="replace",
            source_project=entry.get("source_project"), image_filename=entry.get("image_filename"),
            title=entry.get("title"), location=entry.get("location"), excerpt=entry.get("excerpt"),
            body=body, image_alt=entry.get("image_alt"), decision_basis=entry.get("decision_basis", ""),
        ))


def _validate_fotografie(entries: List[dict], projects, content_schema, provenance, claimed, result: ValidationResult, allowed_categories, category_positions):
    seen_categories = set()

    for entry in entries:
        category = entry.get("target_category")
        action = entry.get("action")

        if category not in allowed_categories:
            result.rejected.append(Rejection("fotografie", category, "target_category nicht erlaubt", entry))
            continue
        if category in seen_categories:
            result.rejected.append(Rejection("fotografie", category, "Kategorie mehrfach in KI-Ausgabe", entry))
            continue
        seen_categories.add(category)

        if action != "replace":
            continue

        project, image = _resolve_image(projects, entry.get("source_project"), entry.get("image_filename"))
        if project is None or image is None:
            result.rejected.append(Rejection("fotografie", category, "source_project/image_filename nicht im Archiv auffindbar", entry))
            result.content_gaps.append(f"fotografie {category}: KI-Vorschlag verworfen (Bildreferenz nicht auffindbar)")
            continue

        slot_position = category_positions.get(category)
        image_rules = images.get_section_image_rules(content_schema, "fotografie", slot_position=slot_position) if slot_position else None
        geometry_reason = _geometry_reason(image, images.target_ratio_for_rules(image_rules) if image_rules else None)
        if geometry_reason:
            result.rejected.append(Rejection("fotografie", category, geometry_reason, entry))
            result.content_gaps.append(f"fotografie {category}: KI-Vorschlag verworfen ({geometry_reason}) -- bestehender Inhalt bleibt aktiv")
            continue

        if not _nonempty(entry.get("image_alt")):
            result.rejected.append(Rejection("fotografie", category, "image_alt fehlt", entry))
            result.content_gaps.append(f"fotografie {category}: KI-Vorschlag verworfen (image_alt fehlt)")
            continue

        key = (entry.get("source_project"), entry.get("image_filename"))
        own_slot = ("fotografie", category)
        dup_reason = _check_duplicate(key, own_slot, provenance, claimed)
        if dup_reason:
            result.rejected.append(Rejection("fotografie", category, dup_reason, entry))
            result.content_gaps.append(f"fotografie {category}: KI-Vorschlag verworfen ({dup_reason})")
            continue

        claimed[key] = own_slot
        result.decisions.append(Decision(
            area="fotografie", slot_key=category, action="replace",
            source_project=entry.get("source_project"), image_filename=entry.get("image_filename"),
            image_alt=entry.get("image_alt"), decision_basis=entry.get("decision_basis", ""),
        ))


def _validate_journal(entries: List[dict], projects, content_schema, result: ValidationResult):
    rules = _section_rules(content_schema, "journal")
    used_positions = set()
    auto_position = 1

    for entry in entries:
        action = entry.get("action")
        if action != "replace":
            continue

        source_project = entry.get("source_project")
        source_file = entry.get("source_file")
        project = discover.find_project_by_id(projects, source_project) if source_project else None
        if project is None:
            result.rejected.append(Rejection("journal", entry.get("slot_hint"), "source_project nicht im Archiv auffindbar", entry))
            result.content_gaps.append("journal: KI-Vorschlag verworfen (source_project nicht auffindbar)")
            continue

        if not _nonempty(entry.get("title")) or not _len_ok(entry.get("title"), rules.get("title_max_len")):
            result.rejected.append(Rejection("journal", entry.get("slot_hint"), "title fehlt oder zu lang", entry))
            result.content_gaps.append("journal: KI-Vorschlag verworfen (title ungueltig)")
            continue
        if not _nonempty(entry.get("excerpt")) or not _len_ok(entry.get("excerpt"), rules.get("excerpt_max_len")):
            result.rejected.append(Rejection("journal", entry.get("slot_hint"), "excerpt fehlt oder zu lang", entry))
            result.content_gaps.append("journal: KI-Vorschlag verworfen (excerpt ungueltig)")
            continue
        if not _nonempty(source_file) or source_file not in project.available_source_files():
            result.rejected.append(Rejection("journal", entry.get("slot_hint"), "source_file fehlt oder ist kein echter Dateiname im Projekt (Beleg-Pflicht)", entry))
            result.content_gaps.append("journal: KI-Vorschlag verworfen (source_file nicht belegt)")
            continue
        if not _len_ok(entry.get("body"), ARTICLE_BODY_MAX_LEN):
            result.rejected.append(Rejection("journal", entry.get("slot_hint"), "body ueberschreitet ARTICLE_BODY_MAX_LEN", entry))
            result.content_gaps.append("journal: KI-Vorschlag verworfen (body zu lang)")
            continue

        slot_hint = entry.get("slot_hint")
        if isinstance(slot_hint, int) and 1 <= slot_hint <= 3 and slot_hint not in used_positions:
            position = slot_hint
        else:
            while auto_position in used_positions and auto_position <= 3:
                auto_position += 1
            if auto_position > 3:
                result.rejected.append(Rejection("journal", slot_hint, "keine freie Journal-Position mehr (max. 3)", entry))
                result.content_gaps.append("journal: KI-Vorschlag verworfen (keine freie Position mehr)")
                continue
            position = auto_position

        used_positions.add(position)
        body = entry.get("body") if _nonempty(entry.get("body")) else None
        result.decisions.append(Decision(
            area="journal", slot_key=position, action="replace",
            title=entry.get("title"), excerpt=entry.get("excerpt"), body=body,
            source_project=source_project, source_file_text=source_file,
            decision_basis=entry.get("decision_basis", ""),
        ))


def validate(editorial: dict, projects, site_content: dict, site_state: dict, content_schema: dict) -> ValidationResult:
    result = ValidationResult()
    result.content_gaps.extend(editorial.get("content_gaps", []) or [])

    claimed: Dict[tuple, tuple] = {}
    provenance = _combined_provenance(site_content, site_state)

    hero_entry = editorial.get("hero")
    if isinstance(hero_entry, dict):
        _validate_hero(hero_entry, projects, content_schema, provenance, claimed, result)

    _validate_reisen(editorial.get("reisen", []) or [], projects, content_schema, provenance, claimed, result)

    fotografie_categories = content_schema.get("sections", {}).get("fotografie", {}).get("allowed_categories", [])
    category_positions = _fotografie_category_positions(site_content)
    _validate_fotografie(editorial.get("fotografie", []) or [], projects, content_schema, provenance, claimed, result, fotografie_categories, category_positions)

    _validate_journal(editorial.get("journal", []) or [], projects, content_schema, result)

    return result
