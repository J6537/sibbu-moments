"""Bildverarbeitung: Zuschnitt, Skalierung und Kompression gemaess den
Regeln in content-schema.json. Zielmasse/Seitenverhaeltnis/Formate/
Groessenlimits werden zur Laufzeit aus dem Schema gelesen, nicht
hartkodiert.

Wasserzeichen werden nur angewendet, wenn content-schema.json ->
watermark.watermark_enabled == true ist (aktuell false, also No-Op).
"""

import shutil
from pathlib import Path
from typing import Optional

from PIL import Image

from . import config


def get_section_image_rules(content_schema: dict, section: str, slot_position: Optional[int] = None) -> dict:
    section_rules = content_schema.get("sections", {}).get(section, {})

    if section == "fotografie":
        for rule in section_rules.get("per_slot_image_rules", []):
            if rule.get("slot") == slot_position:
                merged = dict(rule)
                merged["max_file_size_kb"] = section_rules.get("max_file_size_kb")
                merged["formats"] = section_rules.get("formats")
                merged["mobile_variant_required"] = section_rules.get("mobile_variant_required", False)
                return merged
        return {}

    rules = dict(section_rules.get("image", {}))
    # hero verwendet 'aspect_ratio_preferred' statt 'aspect_ratio' (siehe
    # content-schema.json) -- hier vereinheitlicht.
    if "aspect_ratio" not in rules and "aspect_ratio_preferred" in rules:
        rules["aspect_ratio"] = rules["aspect_ratio_preferred"]
    return rules


def _parse_ratio(ratio_str: str) -> float:
    w, h = ratio_str.split(":")
    return float(w) / float(h)


def _center_crop_to_ratio(img: Image.Image, target_ratio: float) -> Image.Image:
    w, h = img.size
    current_ratio = w / h
    if current_ratio > target_ratio:
        new_w = max(1, int(h * target_ratio))
        left = (w - new_w) // 2
        box = (left, 0, left + new_w, h)
    else:
        new_h = max(1, int(w / target_ratio))
        top = (h - new_h) // 2
        box = (0, top, w, top + new_h)
    return img.crop(box)


def _save_within_size(img: Image.Image, path: Path, max_kb: float) -> float:
    path.parent.mkdir(parents=True, exist_ok=True)
    quality = 85
    min_quality = 40
    while True:
        img.save(path, format="WEBP", quality=quality, method=6)
        size_kb = path.stat().st_size / 1024.0
        if size_kb <= max_kb or quality <= min_quality:
            break
        quality -= 5

    while path.stat().st_size / 1024.0 > max_kb and min(img.size) > 200:
        img = img.resize(
            (max(1, int(img.width * 0.9)), max(1, int(img.height * 0.9))),
            Image.LANCZOS,
        )
        img.save(path, format="WEBP", quality=min_quality, method=6)

    return path.stat().st_size / 1024.0


def _docs_relative(path: Path) -> str:
    return str(path.resolve().relative_to(config.DOCS_DIR.resolve()))


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    n = 2
    while True:
        candidate = path.with_name(f"{stem}-{n}{suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def process_image(source_path: Path, rules: dict, target_basename: str) -> dict:
    """Schneidet/skaliert/komprimiert ein Quellbild gemaess 'rules' und legt
    Web- (und optional Mobile-)Version unter docs/assets/images/web(+mobile)
    ab. Gibt {'image': <docs-relativer Pfad>, 'image_mobile': <Pfad>|None}
    zurueck."""
    if not rules or (not rules.get("aspect_ratio") and not (rules.get("target_width") and rules.get("target_height"))):
        raise ValueError(f"Keine Bildregeln fuer target_basename={target_basename} gefunden.")

    target_w = rules.get("target_width")
    target_h = rules.get("target_height")
    if target_w and target_h:
        # Verhaeltnis aus den tatsaechlichen Zielpixelmassen ableiten, nicht
        # aus dem separaten 'aspect_ratio'-Textfeld -- bei hero weichen
        # target_width/target_height (16:9) und aspect_ratio_preferred
        # (21:9) in content-schema.json voneinander ab; ein Crop nach dem
        # Textfeld wuerde beim Resize auf die Zielpixelmasse verzerren.
        ratio = target_w / target_h
    else:
        ratio = _parse_ratio(rules["aspect_ratio"])
    max_kb = rules.get("max_file_size_kb") or 500

    with Image.open(source_path) as original:
        original = original.convert("RGB")
        cropped = _center_crop_to_ratio(original, ratio)

        web_img = cropped.resize((target_w, target_h), Image.LANCZOS) if target_w and target_h else cropped.copy()
        web_path = _unique_path(config.IMAGES_WEB_DIR / f"{target_basename}.webp")
        _save_within_size(web_img, web_path, max_kb)

        result = {"image": _docs_relative(web_path), "image_mobile": None}

        if rules.get("mobile_variant_required"):
            mobile_w = max(480, int((target_w or 1200) / 2))
            mobile_h = max(1, int(mobile_w / ratio))
            mobile_img = cropped.resize((mobile_w, mobile_h), Image.LANCZOS)
            mobile_path = _unique_path(config.IMAGES_MOBILE_DIR / f"{target_basename}.webp")
            _save_within_size(mobile_img, mobile_path, max_kb)
            result["image_mobile"] = _docs_relative(mobile_path)

    return result


def archive_existing_image(docs_relative_path: Optional[str], timestamp: str) -> Optional[str]:
    """Verschiebt eine bestehende, aktive Bilddatei nach
    docs/assets/images/archive/ -- Originale werden nie geloescht."""
    if not docs_relative_path:
        return None

    src = config.DOCS_DIR / docs_relative_path
    if not src.is_file():
        return None

    config.IMAGES_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    dest = _unique_path(config.IMAGES_ARCHIVE_DIR / f"{timestamp}-{src.name}")
    shutil.move(str(src), str(dest))
    return _docs_relative(dest)
