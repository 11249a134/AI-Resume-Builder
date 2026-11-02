"""Small, dependency-light helpers shared by the Flask routes and services."""

from __future__ import annotations

import html
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
RESUME_EXTENSIONS = {".pdf", ".docx"}
CERTIFICATE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
URL_RE = re.compile(r"^(https?://)?[\w\-]+(\.[\w\-]+)+(/[\w\-./?%&=+#]*)?$")


def new_id() -> str:
    """Return a URL-safe random identifier."""
    return uuid.uuid4().hex[:16]


def extension_of(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def is_allowed(filename: str, allowed: set[str]) -> bool:
    return extension_of(filename) in allowed


def split_items(raw: str | None, max_items: int = 40) -> list[str]:
    """Split comma/newline/semicolon/pipe separated user input into clean items."""
    if not raw:
        return []
    parts = re.split(r"[,;\n\r|]+", str(raw))
    seen: set[str] = set()
    items: list[str] = []
    for part in parts:
        item = " ".join(part.strip(" \t-•*").split())
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(item[:80])
        if len(items) >= max_items:
            break
    return items


def clean_text(value: str | None, limit: int = 2000) -> str:
    """Trim, collapse runs of whitespace/newlines and cap the length."""
    if value is None:
        return ""
    text = str(value).replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:limit]


def clean_line(value: str | None, limit: int = 180) -> str:
    return re.sub(r"\s+", " ", clean_text(value, limit)).strip()


def is_email(value: str) -> bool:
    return bool(EMAIL_RE.match((value or "").strip()))


def is_url(value: str) -> bool:
    return bool(URL_RE.match((value or "").strip()))


def normalise_url(value: str | None) -> str:
    """Turn user-supplied profile handles into a real, safe http(s) link."""
    url = clean_line(value, 300)
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url.lstrip("/")
    if not is_url(url):
        return ""
    return url


def link_label(url: str) -> str:
    """Short human label for a profile URL (linkedin.com/in/name -> LinkedIn)."""
    url = (url or "").lower()
    for host, label in (
        ("linkedin", "LinkedIn"),
        ("github", "GitHub"),
        ("gitlab", "GitLab"),
        ("kaggle", "Kaggle"),
        ("medium", "Medium"),
        ("behance", "Behance"),
        ("dribbble", "Dribbble"),
        ("youtube", "YouTube"),
    ):
        if host in url:
            return label
    return re.sub(r"^https?://(www\.)?", "", url).split("/")[0]


def word_count(text: str | None) -> int:
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'+#./\-]*", text or ""))


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def pretty_date(value: str | None) -> str:
    """Normalise '2024-06', 'June 2024', '06/2024' into 'Jun 2024'."""
    raw = clean_line(value, 40)
    if not raw:
        return ""
    for fmt in ("%Y-%m", "%m/%Y", "%m-%Y", "%Y/%m", "%d/%m/%Y", "%Y-%m-%d", "%B %Y", "%b %Y", "%Y"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.strftime("%b %Y") if fmt != "%Y" else str(parsed.year)
        except ValueError:
            continue
    return raw


def year_range(start: str | None, end: str | None) -> str:
    start_year = clean_line(start, 12)
    end_year = clean_line(end, 12)
    if start_year and end_year:
        if start_year == end_year:
            return start_year
        return f"{start_year} – {end_year}"
    return start_year or end_year or ""


def escape(text: str | None) -> str:
    return html.escape(text or "")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def save_image_upload(file_storage, folder: Path, max_bytes: int) -> tuple[str, str]:
    """Validate and store a profile photo. Returns (filename, error)."""
    if not file_storage or not file_storage.filename:
        return "", ""
    if not is_allowed(file_storage.filename, IMAGE_EXTENSIONS):
        return "", "Profile photo must be a JPG, JPEG or PNG file."

    blob = file_storage.read(max_bytes + 1)
    if len(blob) > max_bytes:
        return "", f"Profile photo is larger than {max_bytes // (1024 * 1024)} MB."
    if not blob:
        return "", "The uploaded profile photo was empty."

    try:
        image = Image.open(__import__("io").BytesIO(blob))
        image.verify()
        image = Image.open(__import__("io").BytesIO(blob))
        image = image.convert("RGB")
    except (UnidentifiedImageError, OSError):
        return "", "That file is not a valid image. Please upload a JPG or PNG photo."

    # Square-ish crop, capped at 900px to keep resumes light.
    side = min(image.size)
    left = (image.width - side) // 2
    top = max(0, int((image.height - side) * 0.15))
    image = image.crop((left, top, left + side, top + side))
    image.thumbnail((900, 900))

    folder.mkdir(parents=True, exist_ok=True)
    name = f"{secure_filename(file_storage.filename).rsplit('.', 1)[0][:40] or 'photo'}.jpg"
    image.save(folder / name, "JPEG", quality=88, optimize=True)
    return name, ""


def save_document_upload(file_storage, folder: Path, allowed: set[str], max_bytes: int, prefix: str = "file") -> tuple[str, str]:
    """Validate and store an uploaded document. Returns (stored_filename, error)."""
    if not file_storage or not file_storage.filename:
        return "", ""
    if not is_allowed(file_storage.filename, allowed):
        readable = ", ".join(sorted(ext.lstrip(".").upper() for ext in allowed))
        return "", f"Unsupported file type. Allowed formats: {readable}."

    blob = file_storage.read(max_bytes + 1)
    if not blob:
        return "", "The uploaded file was empty."
    if len(blob) > max_bytes:
        return "", f"File is larger than {max_bytes // (1024 * 1024)} MB."

    folder.mkdir(parents=True, exist_ok=True)
    original = secure_filename(file_storage.filename) or f"{prefix}{extension_of(file_storage.filename)}"
    stored = f"{prefix}_{new_id()[:8]}_{original}"[:120]
    (folder / stored).write_bytes(blob)
    return stored, ""
