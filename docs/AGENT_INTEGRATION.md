# Sibbu Moments — Integration für den lokalen Website-Pflege-Agenten

Diese Datei richtet sich an einen zukünftigen Coding-Agenten, der auf Basis
dieser Vorbereitung den eigentlichen lokalen Website-Pflege-Agenten baut.
Sie beschreibt verbindlich, wie die Website strukturiert ist, was verändert
werden darf und was nicht, und wie geprüft wird, bevor etwas veröffentlicht
wird.

**Geltungsbereich:** Dieses Dokument und der beschriebene Agent betreffen
ausschließlich dieses eigenständige Website-Repository (Sibbu Moments). Sie
haben keinen Bezug zum separaten Content_Agent-Projekt — dieses Repo liest,
verändert und benötigt es nicht.

Die Website selbst (Design, Layout, Text-Grundgerüst) wurde **nicht neu
gestaltet** — dieses Dokument beschreibt ausschließlich die technische
Vorbereitung, die auf das bestehende, fertige Design von „Sibbu Moments“
aufgesetzt wurde.

---

## 1. Grundprinzip

Die Website besteht aus festem Layout (HTML/CSS/JS) plus austauschbaren
Inhalten (JSON). Ein lokaler Agent verändert **Inhalte und Bilder**, niemals
Layout oder Code. Fehlt ein Inhalt oder ist er ungültig, zeigt die Website
automatisch die ursprüngliche, im HTML fest hinterlegte Fallback-Version —
es gibt keinen Zustand, in dem etwas leer oder kaputt aussieht.

## 2. Welche Dateien sind dynamisch, welche geschützt?

Verbindlich definiert in [`docs/data/agent-interface.json`](data/agent-interface.json).

**Dynamisch (darf der Agent automatisiert verändern):**
- `docs/data/site-content.json` — alle sichtbaren Inhalte
- `docs/data/site-state.json` — Agenten-Gedächtnis
- `docs/data/archive/` — archivierte Vorzustände von Inhalten
- `docs/assets/images/web/`, `docs/assets/images/mobile/`,
  `docs/assets/images/original-derived/`, `docs/assets/images/archive/`

**Geschützt (nur manuelle/bewusste Änderung, nicht durch den Agenten):**
- `docs/index.html`, `docs/css/style.css`, `docs/js/script.js`
- `docs/data/content-schema.json`, `docs/data/agent-interface.json`
- `docs/assets/branding/`, `docs/assets/favicon.svg`, `docs/assets/og-image.svg`
- `tools/validate_site.py`

Der `seo`-Block in `site-content.json` ist redaktionelle Referenz, wird aber
**nicht automatisiert** angewendet, weil eine echte Umsetzung Änderungen an
den Meta-Tags in `docs/index.html` erfordern würde — und `index.html` ist
geschützt. SEO-Anpassungen bleiben manuelle Redaktionsarbeit.

## 3. Aufbau von `site-content.json`

Eine JSON-Datei mit einem Objekt pro Bereich:

```
hero        → einzelnes Objekt
zitat       → einzelnes Objekt
reisen      → { "items": [ 4 Objekte, feste Reihenfolge/Anzahl ] }
fotografie  → { "items": [ 4 Objekte, feste Reihenfolge/Anzahl ] }
journal     → { "items": [ 3 Objekte, feste Reihenfolge/Anzahl ] }
ueber-uns   → einzelnes Objekt
kontakt     → einzelnes Objekt
seo         → einzelnes Objekt (nur Referenz, siehe oben)
```

Jedes Objekt kann die in `content-schema.json` → `common_fields`
beschriebenen Felder enthalten (`id`, `section`, `title`, `subtitle`,
`excerpt`, `body`, `location`, `date`, `category`, `tags`, `image`,
`image_mobile`, `image_alt`, `image_caption`, `link`, `featured`,
`source_project`, `source_file`, `created_at`, `updated_at`,
`published_at`, `content_status`, `fallback_art`).

**Wichtig — nicht jedes Feld ist mit dem HTML verknüpft.** Nur die Felder,
die im HTML ein passendes `data-field="..."` besitzen, werden tatsächlich
angezeigt. Aktuell sind das:

| Bereich       | Live gerenderte Felder                                   | Nur Referenz/nicht gerendert |
|---------------|-----------------------------------------------------------|-------------------------------|
| `hero`        | `subtitle` (Kicker), `excerpt` (Lede), `image`+`image_mobile`+`image_alt` | `title` (Überschrift bleibt festes Markendesign) |
| `zitat`       | `body` (Zitat), `subtitle` (Zuschreibung)                 | — |
| `reisen`      | `location`, `title`, `excerpt`, `content_status` (→ Badge „Aktuell“/„Bald“), `link` (nur Slot 1, s. u.), `image`+`image_mobile`+`image_alt` | `date`, `tags` |
| `fotografie`  | `category`, `image`+`image_mobile`+`image_alt`            | `title`, `location` |
| `journal`     | `title`, `excerpt`, `content_status`+`date` (→ Datum statt „In Vorbereitung“, nur wenn `published`), `link` | `tags` |
| `ueber-uns`   | `body` (erster Absatz), `image`+`image_alt`                | `title` (H2 bleibt fest); zweiter Absatz (Erwähnung des Sibbu Content Agent) bleibt bewusst fest in `index.html` |
| `kontakt`     | `excerpt`                                                  | `title` (H2 bleibt fest) |

Alle Abschnitts-Überschriften (`<h2>`) und "Eyebrows" sind bewusst festes
Redaktionsdesign und werden nicht dynamisch überschrieben.

### Feste Anzahl der Karten

`reisen` (4), `fotografie` (4) und `journal` (3) haben eine **feste** Anzahl
Slots, die dem bestehenden Layout entsprechen (`content-schema.json` →
`fixed_item_count`, `allow_count_change: false`). Ein Item in
`site-content.json`, dessen `id` zu keinem vorhandenen Slot im HTML passt,
wird von `script.js` einfach ignoriert — es entsteht kein Fehler und kein
zusätzliches Element. Der Agent tauscht Inhalte in bestehenden Slots aus,
er erzeugt keine neuen.

## 4. Neue Bilder eintragen

1. Bild in der passenden Zielgröße/Format ablegen:
   - Web-Version → `docs/assets/images/web/<beschreibender-name>.webp` (oder `.jpg`/`.png`)
   - Mobile-Version (optional) → `docs/assets/images/mobile/<name>.webp`
   - Unbearbeitete/Zwischenversion → `docs/assets/images/original-derived/`
2. Anforderungen pro Bereich (Seitenverhältnis, Zielbreite/-höhe, maximale
   Dateigröße, erlaubte Formate) stehen in `content-schema.json` →
   `sections.<bereich>.image`.
3. Im passenden Item in `site-content.json` setzen:
   - `image`: relativer Pfad ab `docs/`, z. B. `assets/images/web/reisen-panama-01.webp`
   - `image_mobile`: optional, eigener mobiler Zuschnitt
   - `image_alt`: **Pflicht**, sobald `image` gesetzt ist — ohne Alt-Text
     bleibt die Fallback-Illustration aktiv (siehe Punkt 5).
4. `tools/validate_site.py` ausführen (siehe Punkt 7), bevor committet wird.

Erlaubte Pfade: nur `assets/images/web/`, `assets/images/mobile/`,
`assets/images/original-derived/`. Erlaubte Formate: `.webp`, `.jpg`,
`.jpeg`, `.png`. Alles andere wird sowohl vom Prüfskript als auch von
`script.js` abgelehnt (die Fallback-Illustration bleibt dann sichtbar).

## 5. Wie Fallbacks funktionieren

Jeder Bildplatz im HTML hat zwei übereinanderliegende Kindelemente:

```html
<div class="story-art">
  <svg data-fallback-art="panama">…bestehende Illustration…</svg>
  <div class="media-slot" data-media-slot hidden></div>
  <!-- weitere feste Elemente, z.B. Status-Badge -->
</div>
```

`script.js` prüft beim Laden `data/site-content.json`:
- Ist `image` gesetzt, ein erlaubter Pfad, die Datei-Endung zulässig, UND
  `image_alt` vorhanden? → Es wird ein `<picture>`/`<img>` in den
  `media-slot` eingefügt, `media-slot` wird sichtbar, die SVG-Illustration
  (`[data-fallback-art]`) wird ausgeblendet.
- Andernfalls (kein Bild, ungültiger Pfad, fehlender Alt-Text, Datei fehlt) →
  nichts passiert, die SVG-Illustration bleibt sichtbar.
- Lädt eine referenzierte Bilddatei zur Laufzeit nicht (z. B. 404), springt
  ein `error`-Handler am `<img>` automatisch zurück auf die
  Fallback-Illustration, statt ein kaputtes Bild-Icon zu zeigen.

Das gilt auch, wenn `data/site-content.json` komplett fehlt, kein gültiges
JSON ist, oder der Abruf technisch fehlschlägt (z. B. beim lokalen Test über
`file://` ohne Server) — die Seite sieht dann exakt wie die ursprüngliche,
fest im HTML hinterlegte Version aus.

## 6. Responsive Bilder & Performance

- `image` + optional `image_mobile` werden als `<picture>` mit
  `<source media="(max-width: 640px)">` (mobile Variante) + `<img>`
  (Standardversion) gerendert.
- Alle Bilder außerhalb des Hero-Bereichs erhalten `loading="lazy"
  decoding="async"`. Das Hero-Bild wird `eager` geladen (above the fold).
- Layout-Verschiebungen (CLS) werden verhindert, weil jeder Bildplatz durch
  feste CSS-Maße/`aspect-ratio` bereits Platz reserviert, bevor ein Bild
  geladen ist.

## 7. Wasserzeichen (vorbereitet, noch nicht aktiv)

Konfigurationsfelder liegen in `content-schema.json` → `watermark`:
`watermark_enabled`, `watermark_asset`, `watermark_position`,
`watermark_opacity`, `watermark_scale`.

**Wichtig:** Das Wasserzeichen wird **nicht im Browser** gerendert. Der
lokale Agent muss es bei der Bildaufbereitung (vor Ablage in
`assets/images/web/`/`mobile/`) direkt in die Bilddatei einarbeiten, z. B.
mit Pillow. Die Datei für das Wasserzeichen-Asset selbst gehört nach
`docs/assets/branding/` (aktuell nur mit `.gitkeep` vorbereitet).

## 8. Prüfsystem starten

```bash
python3 tools/validate_site.py
```

Das Skript prüft (ohne etwas zu verändern oder zu veröffentlichen):
- Gültigkeit aller JSON-Dateien unter `docs/data/`
- Einhaltung von `content-schema.json` (Pflichtfelder, Textlängen,
  erlaubte Kategorien, Alt-Text-Pflicht, feste Item-Anzahl je Bereich)
- Alle referenzierten Bilder existieren, liegen in einem erlaubten Ordner,
  haben eine erlaubte Endung, überschreiten keine Größenlimits
- Keine doppelt verwendeten Bilder
- Keine doppelten Content-IDs
- Alle internen Links (`#anker`, relative Pfade) haben ein gültiges Ziel
- Keine verdächtigen HTML-/Script-Fragmente in Textfeldern
- `agent-interface.json` und `site-state.json` enthalten die erwarteten Felder

**Exit-Codes:**
- `0` → Erfolgreich. Commit/Push darf fortgesetzt werden.
- `1` (oder anders ungleich 0) → Mindestens ein Fehler. **Kein Commit, kein
  Push.** Der Bericht auf stdout listet jeden Fehler einzeln auf.

## 9. Wie der spätere lokale Agent arbeiten soll

Empfohlener Ablauf pro Lauf:

1. Content-Archiv / Projektdaten auswerten, die als Quelle für neue
   Website-Inhalte dienen sollen.
2. Passende Bilder auswählen, zuschneiden/skalieren/komprimieren gemäß den
   Vorgaben in `content-schema.json`, optional Wasserzeichen einarbeiten,
   in `assets/images/web/` (+ `mobile/`) ablegen.
3. **Vor** jeder inhaltlichen Änderung: bisherigen Datensatz aus
   `site-content.json` nach `docs/data/archive/<section>/<id>-<timestamp>.json`
   kopieren; bisherige Bilddatei (falls vorhanden) nach
   `docs/assets/images/archive/` verschieben. Originale werden nie gelöscht.
4. `site-content.json` mit den neuen Werten aktualisieren
   (`updated_at`/`published_at`/`content_status` mitpflegen).
5. `site-state.json` aktualisieren (`last_updated`, `active_content_ids`,
   `active_image_files`, `section_last_changed`, `known_content_gaps`).
6. `python3 tools/validate_site.py` ausführen.
7. Nur bei Exit-Code `0`: `last_successful_test` in `site-state.json`
   setzen, committen, `last_git_commit` eintragen, pushen.
8. Bei Exit-Code ungleich `0`: **kein Commit, kein Push.** Fehler in
   `site-state.json` unter `known_content_gaps` vermerken und Lauf
   abbrechen. Bereits archivierte Vorzustände bleiben unangetastet, damit
   zurückgerollt werden kann.

## 10. Welche Dateien vor einem Git-Push geprüft werden müssen

Vor jedem Push durch den Agenten:
1. `python3 tools/validate_site.py` → muss Exit-Code `0` liefern.
2. Der Diff darf **ausschließlich** Pfade aus
   `agent-interface.json` → `allowed_write_paths` enthalten. Taucht eine
   Datei aus `protected_paths` im Diff auf, muss der Push abgebrochen
   werden (siehe `agent-interface.json` → `git_push_policy`).

## 11. Archivierung eines vorherigen Inhalts

Beispiel: Reisen-Slot 1 bekommt ein neues Titelbild.

1. Aktuellen Datensatz aus `site-content.json` lesen (das komplette
   Objekt für `reisen-panama-kuna-yala`).
2. Unverändert speichern unter
   `docs/data/archive/reisen/reisen-panama-kuna-yala-2026-08-01T120000Z.json`.
3. Bisherige Bilddatei (falls vorhanden) nach
   `docs/assets/images/archive/` verschieben (nicht löschen).
4. Neuen Datensatz/neues Bild in `site-content.json` bzw.
   `assets/images/web/` eintragen.
5. Validieren (Punkt 8), erst dann committen.

Die Website zeigt das Archiv aktuell nicht öffentlich an — es dient der
Nachvollziehbarkeit und einer möglichen späteren Archiv-Ansicht.

## 12. Sicherheitsrahmen (bereits umgesetzt)

- Alle dynamischen Texte werden über `textContent` gesetzt, nie `innerHTML`.
- Links werden gegen eine Protokoll-Positivliste geprüft: `https:`,
  `mailto:`, interne Anker (`#…`), interne relative Pfade. Alles andere
  (`javascript:`, `data:`, `http:`, `ftp:`, absolute `/`-Pfade, `..`) wird
  verworfen; das Element bleibt sichtbar, aber ohne Klickziel
  (`aria-disabled="true"`, kein `href`).
- Externe `https://`-Links erhalten automatisch `rel="noopener noreferrer"`
  und `target="_blank"`.
- Es gibt keinen Servercode und keine Datenbank — GitHub Pages ist rein
  statisch, das bleibt so.
- Content-Security-Policy und Referrer-Policy sind als Meta-Tags in
  `index.html` hinterlegt (GitHub Pages liefert keine eigenen HTTP-Header).
- Das Newsletter-Formular ist als Vorschau gekennzeichnet (Hinweistext unter
  dem Formular) und sendet nichts an einen Server.

---

Bei Fragen zur ursprünglichen Design-Entscheidung: Die visuelle Gestaltung
war zum Zeitpunkt dieser technischen Umstellung bereits fertig und wurde
bewusst nicht verändert. Jede zukünftige Design-Änderung ist eine separate,
manuelle Aufgabe — nicht Teil der automatisierten Content-Pflege.
