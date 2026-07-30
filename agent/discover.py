"""Read-only Discovery des Content_Agent-Medienarchivs.

Liest ausschliesslich. Es wird an keiner Stelle in CONTENT_AGENT_ROOT
geschrieben, verschoben oder geloescht.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import config, images


def _orientation_label(width: int, height: int) -> str:
    if width > height:
        return "querformat"
    if height > width:
        return "hochformat"
    return "quadratisch"


@dataclass
class ImageInfo:
    filename: str
    path: Path
    beschreibung: str = ""
    tiere_natur: str = ""
    kreativ: str = ""
    stichwoerter: List[str] = field(default_factory=list)
    width: int = 0
    height: int = 0

    def to_prompt_dict(self):
        return {
            "filename": self.filename,
            "beschreibung": self.beschreibung,
            "tiere_natur": self.tiere_natur,
            "kreativ": self.kreativ,
            "stichwoerter": self.stichwoerter,
            # Bereits EXIF-korrigierte, tatsaechliche Anzeige-Ausrichtung --
            # damit die KI Bilder nicht fuer geometrisch ungeeignete Slots
            # vorschlaegt (z.B. Hochformat-Portraet fuer den breiten Hero).
            "breite": self.width,
            "hoehe": self.height,
            "ausrichtung": _orientation_label(self.width, self.height) if self.width and self.height else "unbekannt",
        }


@dataclass
class ProjectData:
    project_id: str  # z.B. "Reise/panama-kuna-yala-ustupu", entspricht source_project
    hauptkategorie: str
    projektordner: str
    path: Path
    kategorie_text: str = ""
    kontext_text: str = ""
    projektname: str = ""
    ort_text: str = ""
    ziel_text: str = ""
    notizen_text: str = ""
    blog_text: str = ""
    social_text: str = ""
    bildvorschlaege_text: str = ""
    contentplan_text: str = ""
    bericht_text: str = ""
    # Tatsaechliche Dateinamen (nicht die generischen Bezeichner oben) --
    # noetig, damit die KI in 'source_file' echte, ueberpruefbare
    # Dateinamen zitiert statt generischer Label wie "blog".
    blog_filename: Optional[str] = None
    social_filename: Optional[str] = None
    bildvorschlaege_filename: Optional[str] = None
    contentplan_filename: Optional[str] = None
    bericht_filename: Optional[str] = None
    images: List[ImageInfo] = field(default_factory=list)

    def available_source_files(self) -> List[str]:
        """Alle echten, zitierfaehigen Dateinamen dieses Projekts (Text +
        Bilder). Wird von der KI-Prompterstellung UND vom Validator
        verwendet -- die KI darf 'source_file' ausschliesslich aus dieser
        Liste waehlen."""
        names = [
            self.blog_filename, self.social_filename, self.bildvorschlaege_filename,
            self.contentplan_filename, self.bericht_filename,
        ]
        names += [img.filename for img in self.images]
        return [n for n in names if n]

    def to_prompt_dict(self):
        return {
            "project_id": self.project_id,
            "kategorie": self.kategorie_text,
            "kontext": self.kontext_text,
            "projektname": self.projektname,
            "ort": self.ort_text,
            "ziel": self.ziel_text,
            "notizen": self.notizen_text,
            "blog": {"dateiname": self.blog_filename, "text": self.blog_text},
            "social": {"dateiname": self.social_filename, "text": self.social_text},
            "contentplan": {"dateiname": self.contentplan_filename, "text": self.contentplan_text},
            "bericht": {"dateiname": self.bericht_filename, "text": self.bericht_text},
            "verfuegbare_quelldateien_fuer_source_file": self.available_source_files(),
            "bilder": [img.to_prompt_dict() for img in self.images],
        }


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return ""


def _find_fixed_file(project_dir: Path, filename: str) -> Optional[Path]:
    candidate = project_dir / filename
    return candidate if candidate.is_file() else None


def _find_suffix_file(project_dir: Path, suffix: str) -> Optional[Path]:
    matches = sorted(
        p for p in project_dir.iterdir()
        if p.is_file() and not p.name.startswith(".") and p.name.endswith(suffix)
    )
    return matches[0] if matches else None


_SECTION_HEADER_RE = re.compile(r"^\s*\d+\.\s*([^\n:]+):?\s*$", re.MULTILINE)


def _parse_bildvorschlaege(text: str) -> Dict[str, dict]:
    """Zerlegt eine *_bildvorschlaege.txt in Bloecke pro Originaldatei und
    extrahiert die nummerierten Unterabschnitte. Gibt ein Dict
    {seo_dateiname: {beschreibung, tiere_natur, kreativ, stichwoerter}} zurueck."""
    result = {}
    if not text:
        return result

    blocks = re.split(r"^##\s*Originaldatei\s*$", text, flags=re.MULTILINE)
    for block in blocks[1:]:
        sections = {}
        headers = list(_SECTION_HEADER_RE.finditer(block))
        for idx, match in enumerate(headers):
            label = match.group(1).strip().lower()
            start = match.end()
            end = headers[idx + 1].start() if idx + 1 < len(headers) else len(block)
            sections[label] = block[start:end].strip(" \n-")

        seo_name = None
        for label, value in sections.items():
            if "seo_dateiname" in label.replace(" ", "_"):
                seo_name = value.splitlines()[0].strip() if value else None
                break

        if not seo_name:
            continue

        beschreibung = ""
        tiere_natur = ""
        kreativ = ""
        stichwoerter_raw = ""
        for label, value in sections.items():
            normalized = label.lower()
            if "sachliche bildbeschreibung" in normalized:
                beschreibung = value
            elif "tiere" in normalized and "natur" in normalized:
                tiere_natur = value
            elif "kreative interpretation" in normalized:
                kreativ = value
            elif "stichw" in normalized:
                stichwoerter_raw = value

        stichwoerter = [s.strip() for s in re.split(r",|\n", stichwoerter_raw) if s.strip()]

        result[seo_name] = {
            "beschreibung": beschreibung,
            "tiere_natur": tiere_natur,
            "kreativ": kreativ,
            "stichwoerter": stichwoerter,
        }

    return result


def _load_project(hauptkategorie_dir: Path, project_dir: Path) -> Optional[ProjectData]:
    bilder_dir = project_dir / "bilder"
    if not bilder_dir.is_dir():
        return None

    image_paths = sorted(
        p for p in bilder_dir.iterdir()
        if p.is_file()
        and not p.name.startswith(".")
        and p.suffix.lower() in config.PROJECT_IMAGE_EXTENSIONS
    )
    if not image_paths:
        return None

    project_id = f"{hauptkategorie_dir.name}/{project_dir.name}"

    data = ProjectData(
        project_id=project_id,
        hauptkategorie=hauptkategorie_dir.name,
        projektordner=project_dir.name,
        path=project_dir,
    )

    fixed = config.PROJECT_FIXED_FILES
    kategorie_path = _find_fixed_file(project_dir, fixed["kategorie"])
    kontext_path = _find_fixed_file(project_dir, fixed["kontext"])
    projektname_path = _find_fixed_file(project_dir, fixed["projektname"])
    ort_path = _find_fixed_file(project_dir, fixed["ort"])
    ziel_path = _find_fixed_file(project_dir, fixed["ziel"])
    notizen_path = _find_fixed_file(project_dir, fixed["notizen"])

    data.kategorie_text = _read_text(kategorie_path) if kategorie_path else ""
    data.kontext_text = _read_text(kontext_path) if kontext_path else ""
    data.projektname = _read_text(projektname_path) if projektname_path else project_dir.name
    data.ort_text = _read_text(ort_path) if ort_path else ""
    data.ziel_text = _read_text(ziel_path) if ziel_path else ""
    data.notizen_text = _read_text(notizen_path) if notizen_path else ""

    suffixes = config.PROJECT_TEXT_SUFFIXES
    blog_path = _find_suffix_file(project_dir, suffixes["blog"])
    social_path = _find_suffix_file(project_dir, suffixes["social"])
    bildvorschlaege_path = _find_suffix_file(project_dir, suffixes["bildvorschlaege"])
    contentplan_path = _find_suffix_file(project_dir, suffixes["contentplan"])
    bericht_path = _find_suffix_file(project_dir, suffixes["bericht"])

    data.blog_text = _read_text(blog_path) if blog_path else ""
    data.social_text = _read_text(social_path) if social_path else ""
    data.bildvorschlaege_text = _read_text(bildvorschlaege_path) if bildvorschlaege_path else ""
    data.contentplan_text = _read_text(contentplan_path) if contentplan_path else ""
    data.bericht_text = _read_text(bericht_path) if bericht_path else ""

    data.blog_filename = blog_path.name if blog_path else None
    data.social_filename = social_path.name if social_path else None
    data.bildvorschlaege_filename = bildvorschlaege_path.name if bildvorschlaege_path else None
    data.contentplan_filename = contentplan_path.name if contentplan_path else None
    data.bericht_filename = bericht_path.name if bericht_path else None

    image_descriptions = _parse_bildvorschlaege(data.bildvorschlaege_text)

    for image_path in image_paths:
        desc = image_descriptions.get(image_path.name, {})
        try:
            width, height = images.oriented_dimensions(image_path)
        except Exception:
            width, height = 0, 0
        data.images.append(ImageInfo(
            filename=image_path.name,
            path=image_path,
            beschreibung=desc.get("beschreibung", ""),
            tiere_natur=desc.get("tiere_natur", ""),
            kreativ=desc.get("kreativ", ""),
            stichwoerter=desc.get("stichwoerter", []),
            width=width,
            height=height,
        ))

    return data


def scan_archive(archiv_dir: Path = None) -> List[ProjectData]:
    """Durchsucht Medienprojekte/archiv/<Hauptkategorie>/<Projektordner>/
    read-only nach verwertbaren Medienprojekten (mindestens ein Bild)."""
    root = archiv_dir or config.ARCHIV_DIR
    projects: List[ProjectData] = []

    if not root.is_dir():
        return projects

    for hauptkategorie_dir in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        for project_dir in sorted(p for p in hauptkategorie_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
            project = _load_project(hauptkategorie_dir, project_dir)
            if project is not None:
                projects.append(project)

    return projects


def find_project_by_id(projects: List[ProjectData], project_id: str) -> Optional[ProjectData]:
    for project in projects:
        if project.project_id == project_id:
            return project
    return None


def find_image(project: ProjectData, filename: str) -> Optional[ImageInfo]:
    for image in project.images:
        if image.filename == filename:
            return image
    return None
