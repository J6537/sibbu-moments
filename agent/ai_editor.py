"""Redaktionelle KI-Stufe: zwei getrennte OpenAI-Aufrufe.

Aufruf 1 (Shortlist, text-only): erzeugt aus Projekttexten und den bereits
vorhandenen Bildbeschreibungen (*_bildvorschlaege.txt) eine begrenzte
Kandidatenliste je Zielbereich.

Aufruf 2 (Endauswahl, Vision): erhaelt ausschliesslich diese Kandidaten als
echte Bilder (Base64, herunterskaliert) und trifft daraus die endgueltige,
zusammenhaengende redaktionelle Entscheidung fuer Hero/Reisen/Fotografie/
Journal.

Die KI schreibt an keiner Stelle selbst eine Datei -- sie liefert
ausschliesslich JSON zurueck, das anschliessend von ai_output_validator.py
hart gegenpgrueft wird.
"""

import base64
import io
import json
from pathlib import Path

from PIL import Image

from . import ai_client, config, discover

STAGE_A_INSTRUCTIONS = """\
Du bist der redaktionelle Assistent fuer die Website "Sibbu Moments" \
(Reise-, Natur- und Fotografie-Website).

Aufgabe in diesem ersten Schritt: Erstelle aus den bereitgestellten \
Medienprojekten (Texte und bereits vorhandene Bildbeschreibungen, KEINE \
echten Bilder) eine begrenzte Shortlist geeigneter Kandidaten fuer vier \
Website-Bereiche: Hero (ein grosses Titelbild), Reisen (bis zu 4 \
Reiseziel-Karten), Fotografie (die vier festen Kategorien Natur, \
Unterwegs, Menschen, Details) sowie Themenvorschlaege fuer Journal (kein \
Bild, nur Text).

Regeln:
- Verwende ausschliesslich Informationen aus den bereitgestellten \
Projektdaten. Erfinde keine Fakten, Orte, Personen oder Ereignisse.
- Schlage keine Bilder/Projekte vor, die laut aktuellem Website-Zustand \
bereits aktiv verwendet werden (active_image_paths), es sei denn, du \
schlaegst bewusst vor, den betroffenen Slot unveraendert zu lassen.
- Reisen-Kandidaten sollen aus Projekten mit erkennbarem Reiseziel-Charakter \
stammen (konkreter Ort, Reiseerlebnis).
- Fotografie-Kandidaten: ordne jeden Bildkandidaten genau einer der vier \
Kategorien zu -- Menschen (Personen sind das Motiv), Unterwegs \
(Fortbewegung/Transport/Wegsituation), Natur (Landschaft/Tiere/Pflanzen \
ohne Personen/Transport im Fokus), Details (Nahaufnahme/Textur).
- Journal-Themenvorschlaege muessen sich auf tatsaechlich vorhandene \
Blog-/Contentplan-/Berichtstexte stuetzen. source_file MUSS exakt einem \
Eintrag aus dem Feld 'verfuegbare_quelldateien_fuer_source_file' des \
jeweiligen Projekts entsprechen (z.B. "Neues_Projekt_blog.txt") -- NICHT \
ein generisches Label wie "blog" oder "contentplan". Ohne belastbares \
Quellmaterial keinen Vorschlag machen.
- Achte bei Bildkandidaten auf Feld 'ausrichtung' (querformat/hochformat/ \
quadratisch) jedes Bildes: Hero und Reisen brauchen breite, eher \
querformatige Motive; die Fotografie-Kategorien Natur/Details vertragen \
auch hochformatige Motive gut. Schlage keine offensichtlich unpassende \
Ausrichtung vor (z.B. ein sehr hochformatiges Portraet fuer Hero).
- Reisen-Kandidaten UND Journal-Vorschlaege brauchen zusaetzlich zum \
kurzen Excerpt einen laengeren 'draft_body'/'body': mehrere Saetze bis \
2-3 kurze Absaetze (ca. 400-1800 Zeichen), verdichtet oder woertlich \
uebernommen aus dem tatsaechlichen Blog-/Contentplan-Text des Projekts \
(Einleitung/Absaetze/Zusammenfassung) -- das wird die Grundlage einer \
eigenen Beitragsseite. Nichts hinzuerfinden, was nicht im Quelltext steht. \
Fuer Fotografie-Kandidaten ist draft_body nicht relevant (kann null sein).
- Texte (draft_title/draft_location/draft_excerpt/draft_body/ \
draft_image_alt) sollen sich an den in SCHEMA-GRENZWERTEN mitgelieferten \
Textlaengen orientieren; die endgueltige Pruefung erfolgt spaeter technisch.
- text_rationale: kurze, nachvollziehbare, quellengestuetzte Begruendung \
(1-2 Saetze), keine ausfuehrliche Gedankenkette.
- Findest du fuer einen Bereich keine geeigneten Kandidaten, lass das \
jeweilige Array leer und nenne den Grund in content_gaps.
- Antworte ausschliesslich im vorgegebenen JSON-Schema.
"""

STAGE_B_INSTRUCTIONS = """\
Du bist der redaktionelle Endentscheider fuer die Website "Sibbu Moments". \
Du erhaeltst die in Schritt 1 vorausgewaehlten Bildkandidaten jetzt als \
ECHTE Bilder, zusammen mit ihren Textentwuerfen, dem aktuellen \
Website-Zustand und den Journal-Themenvorschlaegen aus Schritt 1.

Triff die endgueltige redaktionelle Auswahl fuer Hero, Reisen, Fotografie \
und Journal als EINE zusammenhaengende Entscheidung:

- Beurteile Hauptmotiv, Bildwirkung und Eignung fuer den jeweiligen \
Website-Bereich anhand des tatsaechlichen Bildinhalts, nicht nur anhand \
der Textbeschreibung aus Schritt 1.
- Hero: hoechstens 1 Bild. Reisen: bis zu 4, Position 1 ist die \
grossformatige Hauptkarte. Fotografie: jede der vier Kategorien \
(Natur/Unterwegs/Menschen/Details) hoechstens einmal.
- Ein Bild darf in diesem Lauf nur in genau einem finalen Slot verwendet \
werden -- keine Mehrfachverwendung ueber Bereiche/Slots hinweg.
- WICHTIG -- Vollstaendigkeit hat Prioritaet: Im AKTUELLEN WEBSITE-ZUSTAND \
erkennst du an content_status ("planned"/"draft" statt "published") und an \
image=null, welche Slots noch unbefuellt sind. Wenn Schritt 1 fuer einen \
solchen leeren Slot einen Kandidaten mit brauchbarem, quellengestuetztem \
Material geliefert hat, SOLLST du ihn verwenden -- nutze nicht nur einen \
einzigen Kandidaten pro Lauf, wenn mehrere gute vorliegen. action="keep" \
ist nur fuer Slots gedacht, fuer die WIRKLICH kein brauchbarer Kandidat \
da ist (z.B. Bild ungeeignet, Text nicht belegt) oder die bereits gut \
befuellt sind und keine Verbesserung noetig ist -- nicht als bequeme \
Standardwahl, wenn eigentlich Material vorliegt.
- Titel/Location/Excerpt/Alt-Text redaktionell auswaehlen oder verdichten, \
aber ausschliesslich mit Informationen, die durch die Quelldateien belegt \
sind. Nichts erfinden.
- body (nur Reisen und Journal): Dir liegt hier NICHT der volle Blogtext \
vor, nur die 'draft_body'/'body'-Entwuerfe aus Schritt 1. Uebernimm diese \
weitgehend unveraendert (sprachlich leicht glaetten ist ok), erfinde \
NICHTS Neues hinzu. Bei Fotografie-Entscheidungen gibt es kein body-Feld.
- decision_basis: kurze, quellengestuetzte, fuer einen Menschen \
nachvollziehbare Begruendung in 1-2 Saetzen -- keine ausfuehrliche interne \
Gedankenkette.
- Journal: source_file MUSS ein echter Dateiname aus den Projektdaten sein \
(siehe 'verfuegbare_quelldateien_fuer_source_file' je Projekt), NICHT ein \
generisches Label wie "blog".
- content_gaps: alles, was mangels geeigneten Materials nicht befuellt \
werden konnte.
- Antworte ausschliesslich im vorgegebenen JSON-Schema.
"""


def _load_schema(filename: str) -> dict:
    path = config.AGENT_DIR / "schemas" / filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _prepare_vision_data_url(path: Path, max_dim: int = 1024) -> str:
    """Skaliert ein Bild fuer die KI-Vision-Beurteilung herunter. Das ist ein
    reines Vorschaubild fuer den API-Aufruf -- die spaetere Produktions-
    Bildverarbeitung (images.py) arbeitet unabhaengig davon auf dem
    Original."""
    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((max_dim, max_dim))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82)
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _stage_a_input_text(projects, ai_context, content_schema) -> str:
    return f"""\
AKTUELLER WEBSITE-ZUSTAND:
{json.dumps(ai_context, ensure_ascii=False, indent=2)}

SCHEMA-GRENZWERTE (content-schema.json):
{json.dumps(content_schema, ensure_ascii=False, indent=2)}

VERFUEGBARE MEDIENPROJEKTE (Content_Agent-Archiv, nur Text/Bildbeschreibungen):
{json.dumps([p.to_prompt_dict() for p in projects], ensure_ascii=False, indent=2)}
"""


def run_shortlist_stage(projects, ai_context, content_schema, model) -> dict:
    schema = _load_schema("shortlist_output.schema.json")
    response = ai_client.call_responses(
        model=model,
        instructions=STAGE_A_INSTRUCTIONS,
        input=_stage_a_input_text(projects, ai_context, content_schema),
        text=ai_client.json_schema_format("sibbu_shortlist", schema),
    )
    return json.loads(response.output_text)


def _collect_unique_candidates(shortlist: dict):
    buckets = [
        ("hero", shortlist.get("hero_candidates", [])),
        ("reisen", shortlist.get("reisen_candidates", [])),
        ("fotografie_natur", shortlist.get("fotografie_candidates_natur", [])),
        ("fotografie_unterwegs", shortlist.get("fotografie_candidates_unterwegs", [])),
        ("fotografie_menschen", shortlist.get("fotografie_candidates_menschen", [])),
        ("fotografie_details", shortlist.get("fotografie_candidates_details", [])),
    ]
    unique = {}
    for bucket_name, items in buckets:
        for candidate in items:
            key = (candidate["project_id"], candidate["image_filename"])
            entry = unique.setdefault(key, {"candidate": candidate, "targets": set()})
            entry["targets"].add(bucket_name)
    return unique


def run_vision_stage(shortlist: dict, projects, ai_context, content_schema, model):
    unique = _collect_unique_candidates(shortlist)

    context_text = f"""\
AKTUELLER WEBSITE-ZUSTAND:
{json.dumps(ai_context, ensure_ascii=False, indent=2)}

SCHEMA-GRENZWERTE (content-schema.json):
{json.dumps(content_schema, ensure_ascii=False, indent=2)}

JOURNAL-THEMENVORSCHLAEGE AUS SCHRITT 1 (zur Bestaetigung/Anpassung, kein Bild noetig):
{json.dumps(shortlist.get("journal_proposals", []), ensure_ascii=False, indent=2)}

VERFUEGBARE QUELLDATEIEN JE PROJEKT (source_file MUSS exakt aus dieser Liste stammen):
{json.dumps({p.project_id: p.available_source_files() for p in projects}, ensure_ascii=False, indent=2)}

BEKANNTE LUECKEN AUS SCHRITT 1:
{json.dumps(shortlist.get("content_gaps", []), ensure_ascii=False, indent=2)}

Im Folgenden alle in Schritt 1 vorausgewaehlten Bildkandidaten, jeweils mit \
Kennzeichnung des/der vorgeschlagenen Zielbereiche, gefolgt vom echten Bild.
"""
    content_blocks = [{"type": "input_text", "text": context_text}]

    attached = []
    skipped = []

    for (project_id, filename), entry in unique.items():
        project = discover.find_project_by_id(projects, project_id)
        image = discover.find_image(project, filename) if project else None
        if project is None or image is None:
            skipped.append(f"{project_id}/{filename} (nicht im Archiv auffindbar -- ausgelassen)")
            continue

        label = (
            f"BILD project_id={project_id} image_filename={filename} "
            f"vorgeschlagen_fuer={sorted(entry['targets'])}\n"
            f"Textentwurf aus Schritt 1: {json.dumps(entry['candidate'], ensure_ascii=False)}"
        )

        try:
            data_url = _prepare_vision_data_url(image.path)
        except Exception as exc:  # defekte/unlesbare Bilddatei
            skipped.append(f"{project_id}/{filename} (Bild konnte nicht geladen werden: {exc})")
            continue

        content_blocks.append({"type": "input_text", "text": label})
        content_blocks.append({"type": "input_image", "image_url": data_url})
        attached.append(f"{project_id}/{filename}")

    if skipped:
        content_blocks.append({
            "type": "input_text",
            "text": "HINWEIS -- folgende Kandidaten aus Schritt 1 stehen NICHT zur Auswahl:\n" + "\n".join(skipped),
        })

    schema = _load_schema("editorial_output.schema.json")
    response = ai_client.call_responses(
        model=model,
        instructions=STAGE_B_INSTRUCTIONS,
        input=[{"role": "user", "content": content_blocks}],
        text=ai_client.json_schema_format("sibbu_editorial_output", schema),
    )
    editorial = json.loads(response.output_text)
    return editorial, attached, skipped


def run_editorial_pipeline(projects, ai_context, content_schema, model=None) -> dict:
    model = model or config.resolve_openai_model()
    shortlist = run_shortlist_stage(projects, ai_context, content_schema, model)
    editorial, attached, skipped = run_vision_stage(shortlist, projects, ai_context, content_schema, model)
    return {
        "model": model,
        "shortlist": shortlist,
        "editorial": editorial,
        "vision_attached_images": attached,
        "vision_skipped_candidates": skipped,
    }
