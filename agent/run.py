#!/usr/bin/env python3
"""Sibbu Moments -- lokaler Website-Pflege-Agent.

Ablauf pro Lauf:
  1. Discovery (read-only) im Content_Agent-Archiv
  2. KI-Redaktion: Shortlist (Text) -> Endauswahl (Vision), zwei getrennte
     OpenAI-Aufrufe
  3. Technische Validierung der KI-Ausgabe gegen content-schema.json und
     den aktuellen Website-Zustand
  4. (nur ohne --dry-run) Anwenden: Bildverarbeitung, Archivierung,
     site-content.json/site-state.json schreiben
  5. tools/validate_site.py ausfuehren
  6. Nur bei Exit-Code 0 UND gestagtem Diff ausschliesslich innerhalb von
     allowed_write_paths: committen, optional pushen

Nutzung:
  python3 -m agent.run --dry-run
  python3 -m agent.run --no-push
  python3 -m agent.run
"""

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from . import ai_client, ai_editor, ai_output_validator, config, content_writer, discover, git_ops, pages, site_state_reader


class AlreadyRunningError(RuntimeError):
    pass


def acquire_lock():
    """Single-Instance-Sperre ueber eine plattformeigene, prozessuebergreifende
    Dateisperre (fcntl.flock, exklusiv, nicht-blockierend). Verhindert, dass
    zwei gleichzeitig gestartete Laeufe denselben Website-Zustand lesen und
    sich beim Schreiben gegenseitig ueberschreiben (siehe Vorfall mit zwei
    parallelen Commits). Der zweite Lauf bricht sofort ab, bevor er
    irgendetwas liest, die KI aufruft oder schreibt."""
    config.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fh = open(config.LOCK_FILE, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        raise AlreadyRunningError(
            f"Ein anderer Agentenlauf haelt bereits die Sperre ({config.LOCK_FILE}). "
            "Dieser Lauf bricht sofort ab, ohne etwas zu lesen oder zu schreiben."
        )
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def release_lock(fh):
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


def _archive_fingerprint(projects) -> str:
    parts = []
    for p in sorted(projects, key=lambda x: x.project_id):
        total_size = sum(img.path.stat().st_size for img in p.images)
        parts.append(f"{p.project_id}:{len(p.images)}:{total_size}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _print_header(text):
    print("\n" + "=" * 78)
    print(text)
    print("=" * 78)


def _print_decision(d):
    print(f"  [{d.area}] slot={d.slot_key} action={d.action}")
    if d.source_project:
        print(f"    Quelle: {d.source_project} / {d.image_filename or d.source_file_text}")
    for field_name, value in (
        ("title", d.title), ("subtitle", d.subtitle), ("location", d.location),
        ("excerpt", d.excerpt), ("image_alt", d.image_alt),
    ):
        if value:
            print(f"    {field_name}: {value}")
    print(f"    decision_basis: {d.decision_basis}")


def run(dry_run: bool, no_push: bool, force: bool, project_filter: str = None, allow_ueber_uns_replace: bool = False) -> int:
    if not config.resolve_openai_api_key():
        print(f"FEHLER: Kein OpenAI-API-Key gefunden (Env-Var {config.OPENAI_API_KEY_ENV} oder {config.LOCAL_ENV_FILE}).")
        return 1

    _print_header("1. Discovery (Content_Agent-Archiv, read-only)")
    projects = discover.scan_archive()
    if project_filter:
        projects = [p for p in projects if p.project_id == project_filter]
    print(f"Gefundene Medienprojekte: {len(projects)}")
    for p in projects:
        print(f"  - {p.project_id} ({len(p.images)} Bilder)")

    if not projects:
        print("Keine Projekte gefunden -- Lauf wird beendet.")
        return 1

    fingerprint = _archive_fingerprint(projects)

    site_content = site_state_reader.load_site_content()
    site_state = site_state_reader.load_site_state()
    content_schema = site_state_reader.load_content_schema()
    agent_interface = site_state_reader.load_agent_interface()

    if not force and not dry_run and site_state.get("last_archive_fingerprint") == fingerprint:
        print("\nArchiv-Fingerprint unveraendert seit dem letzten erfolgreichen Lauf -- ueberspringe KI-Aufruf (--force erzwingt einen Lauf trotzdem).")
        return 0

    ai_context = site_state_reader.build_ai_context(site_content, site_state)

    _print_header("2. KI-Redaktion (Schritt 1: Shortlist, Schritt 2: Vision-Endauswahl)")
    try:
        pipeline_result = ai_editor.run_editorial_pipeline(projects, ai_context, content_schema)
    except ai_client.MissingApiKeyError as exc:
        print(f"FEHLER: {exc}")
        return 1

    shortlist = pipeline_result["shortlist"]
    editorial = pipeline_result["editorial"]
    print(f"Modell: {pipeline_result['model']}")
    print(f"Shortlist -- Hero: {len(shortlist.get('hero_candidates', []))}, "
          f"Ueber-uns: {len(shortlist.get('ueber_uns_candidates', []))}, "
          f"Reisen: {len(shortlist.get('reisen_candidates', []))}, "
          f"Fotografie Natur/Unterwegs/Menschen/Details: "
          f"{len(shortlist.get('fotografie_candidates_natur', []))}/"
          f"{len(shortlist.get('fotografie_candidates_unterwegs', []))}/"
          f"{len(shortlist.get('fotografie_candidates_menschen', []))}/"
          f"{len(shortlist.get('fotografie_candidates_details', []))}, "
          f"Journal-Vorschlaege: {len(shortlist.get('journal_proposals', []))}")
    print(f"Fuer Vision-Stufe geladene Bilder: {len(pipeline_result['vision_attached_images'])}")
    if pipeline_result["vision_skipped_candidates"]:
        print("Nicht ladbare Kandidaten (uebersprungen):")
        for s in pipeline_result["vision_skipped_candidates"]:
            print(f"  - {s}")

    _print_header("3. Technische Validierung der KI-Endauswahl")
    ueber_uns_locked = bool((site_content.get("ueber-uns") or {}).get("source_project"))
    if ueber_uns_locked and not allow_ueber_uns_replace:
        print("(Hinweis: ueber-uns ist bereits befuellt und daher gesperrt -- KI-Vorschlaege dafuer werden ignoriert. --allow-ueber-uns-replace hebt das auf.)")
    validation_result = ai_output_validator.validate(editorial, projects, site_content, site_state, content_schema, allow_ueber_uns_replace=allow_ueber_uns_replace)
    print(f"Validierte, anwendbare Entscheidungen: {len(validation_result.decisions)}")
    for d in validation_result.decisions:
        _print_decision(d)
    print(f"\nVerworfene KI-Vorschlaege: {len(validation_result.rejected)}")
    for r in validation_result.rejected:
        print(f"  [{r.area}] slot={r.slot_key}: {r.reason}")
    print(f"\nContent-Luecken: {len(validation_result.content_gaps)}")
    for g in validation_result.content_gaps:
        print(f"  - {g}")

    if dry_run:
        _print_header("DRY-RUN -- keine Datei wurde geschrieben, kein Git, kein Push")
        return 0

    if not validation_result.decisions:
        print("\nKeine anwendbaren Entscheidungen -- site-state.json wird dennoch mit aktuellem Zeitstempel/Luecken aktualisiert.")

    site_content_copy = json.loads(json.dumps(site_content))
    site_state_copy = json.loads(json.dumps(site_state))

    _print_header("4. Anwenden: Bildverarbeitung, Archivierung, Schreiben")
    write_log = content_writer.apply_decisions(validation_result, projects, site_content_copy, site_state_copy, content_schema)
    for entry in write_log:
        print(f"  {entry.action} [{entry.area}/{entry.slot_key}] -> {entry.item_id}")

    _print_header("4b. Beitragsseiten (Reisen-Slot 1 + Journal)")
    page_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    page_log = pages.sync_pages(site_content_copy, page_timestamp)
    if page_log:
        for entry in page_log:
            print(f"  Seite geschrieben [{entry.area}] {entry.item_id} -> {entry.path}")
    else:
        print("  Keine Beitragsseite aktualisiert (kein Slot mit ausreichend langem Text).")

    site_state_copy["last_archive_fingerprint"] = fingerprint
    content_writer.save_site_files(site_content_copy, site_state_copy)
    print("site-content.json und site-state.json geschrieben.")

    _print_header("5. Validierung (tools/validate_site.py)")
    result = subprocess.run([sys.executable, str(config.VALIDATE_SCRIPT)], cwd=str(config.WEBSITE_ROOT), capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    if result.returncode != 0:
        print("Validierung fehlgeschlagen -- KEIN Commit, KEIN Push.")
        site_state_copy["known_content_gaps"] = site_state_copy.get("known_content_gaps", []) + [{
            "area": "validate_site",
            "issue": "validate_site.py meldete Fehler nach diesem Lauf -- Aenderungen bleiben lokal.",
            "since": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }]
        content_writer.save_site_files(site_content_copy, site_state_copy)
        return 1

    print("Validierung erfolgreich (Exit-Code 0).")

    _print_header("6. Git: gezieltes Staging, Diff-Pruefung, Commit" + ("" if no_push else "/Push"))
    allowed = agent_interface.get("allowed_write_paths", [])
    protected = agent_interface.get("protected_paths", [])

    staged = git_ops.stage_allowed_paths(allowed)
    print(f"Gestagte Pfade: {staged}")

    ok, violations = git_ops.verify_staged_diff(allowed, protected)
    if not ok:
        print(f"ABBRUCH: gestagter Diff enthaelt nicht erlaubte Pfade: {violations}")
        git_ops.unstage_all()
        return 1

    if not staged:
        print("Keine Aenderungen zum Committen.")
        return 0

    commit_hash = git_ops.commit("Sibbu-Moments Content-Agent: automatisierte Inhaltsaktualisierung")
    print(f"Commit erstellt: {commit_hash}")

    if no_push:
        print("--no-push gesetzt: kein Push.")
        return 0

    push_output = git_ops.push()
    print(f"Gepusht: {push_output}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Sibbu Moments Website-Pflege-Agent")
    parser.add_argument("--dry-run", action="store_true", help="Nur Discovery + KI-Redaktion + Validierung anzeigen, nichts schreiben")
    parser.add_argument("--no-push", action="store_true", help="Lokal committen, aber nicht pushen")
    parser.add_argument("--force", action="store_true", help="KI-Lauf erzwingen, auch wenn sich das Archiv seit dem letzten Lauf nicht geaendert hat")
    parser.add_argument("--project", default=None, help="Nur ein einzelnes Projekt verarbeiten (project_id, z.B. Reise/panama-kuna-yala-ustupu)")
    parser.add_argument("--allow-ueber-uns-replace", action="store_true", help="Hebt die Sperre auf und erlaubt einen Austausch von 'Ueber uns', auch wenn der Slot bereits aus einem echten Projekt befuellt ist")
    args = parser.parse_args()

    try:
        lock_fh = acquire_lock()
    except AlreadyRunningError as exc:
        print(f"ABBRUCH: {exc}")
        return 1

    try:
        return run(
            dry_run=args.dry_run, no_push=args.no_push, force=args.force,
            project_filter=args.project, allow_ueber_uns_replace=args.allow_ueber_uns_replace,
        )
    finally:
        release_lock(lock_fh)


if __name__ == "__main__":
    sys.exit(main())
