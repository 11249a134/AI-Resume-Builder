"""Text extraction and heuristic section detection for uploaded resumes.

Nothing here renders the uploaded file as an image: PDFs are read with pypdf and
DOCX files with python-docx, then the plain text is split into resume sections
with transparent heuristics. Users can always correct the result in the builder.
"""

from __future__ import annotations

import re
from pathlib import Path

from utils.helpers import clean_line, clean_text, normalise_url, split_items, word_count

# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #
SECTION_HEADINGS: dict[str, tuple[str, ...]] = {
    "objective": ("career objective", "objective", "professional summary", "summary", "profile", "about me", "career summary"),
    "education": ("education", "academic background", "academic qualifications", "academic details", "educational qualification", "education details"),
    "skills": ("skills", "technical skills", "key skills", "core competencies", "technical proficiency", "skills & abilities", "areas of expertise"),
    "projects": ("projects", "academic projects", "personal projects", "key projects", "project experience", "major projects"),
    "certifications": ("certifications", "certificates", "licenses & certifications", "courses & certifications", "training & certifications"),
    "experience": ("experience", "work experience", "professional experience", "internship", "internships", "employment history", "work history"),
    "achievements": ("achievements", "awards", "honors", "honours", "accomplishments", "extracurricular activities", "activities"),
    "languages": ("languages", "languages known"),
    "interests": ("interests", "hobbies", "hobbies & interests"),
    "personal": ("personal details", "personal information", "personal profile"),
}

DEGREE_WORDS = (
    "b.tech", "btech", "b.e", "be ", "b.sc", "bsc", "bca", "b.com", "bcom", "bba", "bachelor",
    "m.tech", "mtech", "m.e", "m.sc", "msc", "mca", "mba", "m.com", "master", "ph.d", "phd",
    "diploma", "intermediate", "higher secondary", "12th", "10th", "secondary school",
)

INSTITUTION_WORDS = ("university", "college", "institute", "school", "academy", "polytechnic", "iit", "nit")

SOFT_SKILL_WORDS = {
    "communication", "teamwork", "team work", "leadership", "problem solving", "problem-solving",
    "time management", "critical thinking", "adaptability", "creativity", "collaboration",
    "presentation", "public speaking", "negotiation", "decision making", "work ethic",
    "attention to detail", "interpersonal skills", "management", "mentoring", "analytical thinking",
    "flexibility", "organization", "organisation", "conflict resolution", "empathy", "patience",
}

YEAR_RANGE_RE = re.compile(
    r"((?:19|20)\d{2})\s*(?:-|–|—|to|until)\s*((?:19|20)\d{2}|present|current|till date)",
    re.I,
)
YEAR_RE = re.compile(r"(19|20)\d{2}")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().\-]{7,17}\d)")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s,;|]+", re.I)
PROFILE_URL_RE = re.compile(
    r"(?:https?://|www\.)?(?:[a-z0-9-]+\.)+(?:com|org|net|io|dev|ai|in|co|me|app|xyz|edu|gov|tech|site|info|online)(?:/[^\s,;|)]*)?",
    re.I,
)
MONTH_DATE_RE = re.compile(
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}", re.I
)
DURATION_RE = re.compile(
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4})\s*"
    r"(?:-|–|—|to|until)\s*"
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4}|present|current|till date)",
    re.I,
)
SCORE_RE = re.compile(
    r"(?:cgpa|gpa|sgpa)\s*[:\-]?\s*\d+(?:\.\d+)?(?:\s*/\s*10)?"
    r"|(?:score|percentage|marks)\s*[:\-]?\s*\d+(?:\.\d+)?\s*%?"
    r"|\d{2,3}(?:\.\d+)?\s*%",
    re.I,
)
BULLET_RE = re.compile(r"^[\u2022\u25aa\u25e6\u00b7\u007f*\-]\s*(.+)$")
TECH_LABEL_RE = re.compile(r"^(?:technolog\w*|tech stack|tools? used|skills? used|stack)\s*[:\-]\s*(.+)$", re.I)
PAGE_FOOTER_RE = re.compile(r"^page\s+\d+(?:\s+of\s+\d+)?$", re.I)
DOMAIN_WORDS = (
    "computer", "science", "engineering", "artificial", "intelligence", "data", "business",
    "commerce", "electronics", "mechanical", "civil", "information technology", "biotech",
    "science", "arts", "commerce", "management", "mathematics", "physics", "chemistry",
)


# --------------------------------------------------------------------------- #
# Raw text extraction
# --------------------------------------------------------------------------- #
def _read_pdf(path: Path) -> tuple[str, dict]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    text = "\n".join(pages)
    return text, {"pages": len(reader.pages), "has_tables": False, "format": "PDF"}


def _read_docx(path: Path) -> tuple[str, dict]:
    from docx import Document

    document = Document(str(path))
    lines = [paragraph.text for paragraph in document.paragraphs]
    table_cells = 0
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    lines.append(cell.text)
                    table_cells += 1
    return "\n".join(lines), {"pages": None, "has_tables": bool(document.tables), "table_cells": table_cells, "format": "DOCX"}


def extract_document(path: Path) -> dict:
    """Extract text + metadata + structured fields from a PDF or DOCX file."""
    extension = path.suffix.lower()
    warnings: list[str] = []
    try:
        if extension == ".pdf":
            raw_text, meta = _read_pdf(path)
        elif extension == ".docx":
            raw_text, meta = _read_docx(path)
        else:
            return {"text": "", "meta": {"format": extension}, "parsed": empty_parsed(), "warnings": ["Unsupported file type."], "scanned": False}
    except Exception as exc:  # corrupt/encrypted files must not 500
        return {
            "text": "",
            "meta": {"format": extension.upper()},
            "parsed": empty_parsed(),
            "warnings": [f"The file could not be read ({exc.__class__.__name__}). It may be corrupt or password protected. You can still fill the form manually."],
            "scanned": False,
        }

    text = normalise_extracted_text(raw_text)
    scanned = extension == ".pdf" and word_count(text) < 40
    if scanned:
        warnings.append(
            "This PDF contains almost no selectable text, which usually means it is a scanned image. "
            "OCR is not installed, so the text cannot be recovered automatically — please enter the details manually."
        )
    elif word_count(text) < 120:
        warnings.append("Very little text was extracted. Check each field and add anything that is missing.")
    else:
        warnings.append("Sections were detected with heuristics. Please review every field before generating the updated resume.")

    parsed = parse_resume_text(text)
    if parsed["confidence"] < 0.5 and not scanned:
        warnings.append("Automatic section detection found limited structure; most fields may need manual correction.")

    return {"text": text, "meta": meta, "parsed": parsed, "warnings": warnings, "scanned": scanned}


def normalise_extracted_text(raw: str) -> str:
    text = (raw or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Presentation footers are not resume content; drop page-number-only lines.
    lines = [line for line in text.split("\n") if not PAGE_FOOTER_RE.match(line.strip())]
    return "\n".join(lines).strip()


def empty_parsed() -> dict:
    return {
        "personal": {"full_name": "", "email": "", "phone": "", "location": "", "linkedin": "", "github": "", "portfolio": ""},
        "objective": "",
        "education": [],
        "skills": {"technical": [], "soft": []},
        "projects": [],
        "certifications": [],
        "experience": [],
        "experience_status": "fresher",
        "confidence": 0.0,
    }


# --------------------------------------------------------------------------- #
# Section detection
# --------------------------------------------------------------------------- #
def _heading_key(line: str) -> str | None:
    candidate = re.sub(r"[^a-z& ]", " ", line.lower())
    candidate = re.sub(r"\s+", " ", candidate).strip()
    if not candidate or len(candidate) > 42:
        return None
    for key, headings in SECTION_HEADINGS.items():
        if candidate in headings:
            return key
    # "TECHNICAL SKILLS:" or "Education Details" with trailing words
    for key, headings in SECTION_HEADINGS.items():
        for heading in headings:
            if candidate == heading or candidate.startswith(heading + " "):
                return key
    return None


def _split_sections(text: str) -> tuple[list[str], dict[str, list[str]]]:
    lines = [line.strip() for line in text.split("\n")]
    header: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        key = _heading_key(line) if line else None
        if key:
            current = key
            sections.setdefault(current, [])
            continue
        if current is None:
            if line:
                header.append(line)
        else:
            sections[current].append(line)
    return header, sections


def _find_contact(header_lines: list[str], full_text: str) -> dict:
    joined = "\n".join(header_lines) or full_text[:1200]
    email = next(iter(EMAIL_RE.findall(joined)), "")
    phone = ""
    for candidate in PHONE_RE.findall(joined):
        digits = re.sub(r"\D", "", candidate)
        if 10 <= len(digits) <= 15:
            phone = clean_line(candidate, 30)
            break
    # Strip emails first so the domain part is not mistaken for a portfolio URL.
    urls = PROFILE_URL_RE.findall(EMAIL_RE.sub(" ", joined))
    links = {"linkedin": "", "github": "", "portfolio": ""}
    for url in urls:
        url = url.rstrip(".,);")
        normalised = normalise_url(url)
        if not normalised:
            continue
        if "linkedin.com" in normalised and not links["linkedin"]:
            links["linkedin"] = normalised
        elif "github.com" in normalised and not links["github"]:
            links["github"] = normalised
        elif not links["portfolio"]:
            links["portfolio"] = normalised

    name = ""
    for line in header_lines[:6]:
        candidate = clean_line(line, 70)
        if not candidate or len(candidate) < 3:
            continue
        if EMAIL_RE.search(candidate) or URL_RE.search(candidate) or re.search(r"\d{3,}", candidate):
            continue
        if PAGE_FOOTER_RE.match(candidate):
            continue
        if _heading_key(candidate) or re.search(r"(?i)\b(resume|curriculum vitae|vitae|profile|contact)\b", candidate):
            continue
        if candidate.endswith(":") or any(char in candidate for char in "|•·@"):
            continue
        words = candidate.split()
        if 1 < len(words) <= 5 and re.search(r"[A-Za-z]", candidate):
            name = candidate.title() if candidate.isupper() else candidate
            break

    location = ""
    location_re = re.compile(
        r"(?i)\b(city|india|usa|uk|canada|australia|state|district|street|road|nagar|pradesh|delhi|mumbai|bangalore|bengaluru|hyderabad|chennai|pune|kolkata|kochi|cochin|ahmedabad|jaipur|lucknow|chandigarh|kozhikode|trivandrum|thiruvananthapuram)\b"
    )
    for line in header_lines[:8]:
        # Contact lines in PDFs often separate items with bullets or wide spaces.
        for part in re.split(r"\s*[|•·\u2022\u007f]\s*|\s{2,}", line):
            part = clean_line(part, 80)
            if not part or EMAIL_RE.search(part) or URL_RE.search(part) or PHONE_RE.search(part):
                continue
            if location_re.search(part) and len(part.split()) <= 6:
                location = part
                break
        if location:
            break
    return {"full_name": name, "email": email, "phone": phone, "location": location, **links}


def _clean_section_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    for line in lines:
        item = line.strip(" \t•▪◦·*-–—\x7f")
        if not item:
            cleaned.append("")
            continue
        if len(item) <= 2:
            continue
        cleaned.append(item)
    while cleaned and not cleaned[0]:
        cleaned.pop(0)
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return cleaned


def _parse_education(lines: list[str]) -> list[dict]:
    entries: list[dict] = []
    current: dict = {}

    def flush():
        nonlocal current
        if current and (current.get("institution") or current.get("degree")):
            entries.append(current)
        current = {}

    for raw_line in _clean_section_lines(lines):
        if not raw_line:
            flush()
            continue
        line = raw_line
        start = end = ""
        years = YEAR_RANGE_RE.search(line)
        if years:
            start, end = years.group(1), years.group(2)
            line = YEAR_RANGE_RE.sub(" ", line)
        else:
            single = YEAR_RE.search(line)
            if single:
                start = single.group(0)
                line = line[: single.start()] + " " + line[single.end():]

        score_text = ""
        score_match = SCORE_RE.search(line)
        if score_match:
            if len(raw_line.split()) <= 5:
                score_text = re.sub(r"(?i)^\s*(score|percentage|marks)\s*[:\-]?\s*", "", raw_line).strip(" :|,-–")
            else:
                score_text = clean_line(score_match.group(0), 30)
            line = line[: score_match.start()] + " " + line[score_match.end():]
        line = clean_line(line, 200).strip(" |–—-:")

        parts = [part.strip(" :–—-|") for part in re.split(r"\s*\|\s*|\s+[—–]\s+|\s+-\s+", line) if part.strip()]
        institution = next((part for part in parts if any(word in part.lower() for word in INSTITUTION_WORDS)), "")
        degree_part = next((part for part in parts if any(word in part.lower() for word in DEGREE_WORDS)), "")
        domain_part = next(
            (
                part
                for part in parts
                if part not in {institution, degree_part} and any(word in part.lower() for word in DOMAIN_WORDS)
            ),
            "",
        )

        if institution:
            existing = re.sub(r"[^a-z0-9]", "", current.get("institution", "").lower())
            incoming = re.sub(r"[^a-z0-9]", "", institution.lower())
            if existing and incoming and existing != incoming:
                flush()
            current["institution"] = clean_line(institution, 150)
        if degree_part and not current.get("degree"):
            current["degree"] = _degree_line(degree_part)
        if domain_part and not current.get("department"):
            current["department"] = clean_line(domain_part, 120)

        if line and not institution and not degree_part:
            lower = line.lower()
            if any(word in lower for word in DEGREE_WORDS) and not current.get("degree"):
                current["degree"] = _degree_line(line)
            elif not current.get("institution") and len(line) > 6:
                current["institution"] = clean_line(line, 150)
            elif not current.get("department") and len(line) <= 110:
                current["department"] = clean_line(line, 120)

        if start:
            current.setdefault("start_year", start)
        if end:
            current["grad_year"] = end if end.lower() not in {"present", "current", "till date"} else end.title()
        if score_text:
            current["score"] = score_text
    flush()
    return [entry for entry in entries if entry.get("institution") or entry.get("degree")][:8]


def _degree_line(line: str) -> str:
    match = re.search(r"(?i)(b\.?\s?tech[^,|–-]*|b\.?\s?e\.?[^,|–-]*|b\.?\s?sc[^,|–-]*|bca[^,|–-]*|b\.?\s?com[^,|–-]*|bba[^,|–-]*|m\.?\s?tech[^,|–-]*|m\.?\s?sc[^,|–-]*|mca[^,|–-]*|mba[^,|–-]*|ph\.?\s?d[^,|–-]*|diploma[^,|–-]*|bachelor[^,|–-]*|master[^,|–-]*)", line)
    if not match:
        return clean_line(line, 120)
    return clean_line(match.group(1), 120).strip(" -–|,")


def _parse_skills(lines: list[str], heading_hint: str = "") -> dict:
    technical: list[str] = []
    soft: list[str] = []
    raw_lines = _clean_section_lines(lines)
    chunks: list[str] = []
    for line in raw_lines:
        if not line:
            continue
        lowered = line.lower()
        if ":" in line:
            prefix, _, rest = line.partition(":")
            lowered_prefix = prefix.lower()
            if "soft" in lowered_prefix or "interpersonal" in lowered_prefix:
                soft.extend(split_items(rest))
                continue
            if any(word in lowered_prefix for word in ("technical", "programming", "tools", "core", "key", "skills")):
                chunks.extend(split_items(rest))
                continue
        chunks.extend(split_items(re.sub(r"\s{2,}", ",", line)))
    for chunk in chunks:
        item = clean_line(chunk, 60)
        if not item or len(item) > 55:
            continue
        lowered = item.lower().strip(".")
        if lowered in SOFT_SKILL_WORDS or any(word == lowered for word in SOFT_SKILL_WORDS):
            soft.append(item)
        else:
            technical.append(item)
    return {"technical": _dedupe(technical)[:35], "soft": _dedupe(soft)[:15]}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _split_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if not line:
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _parse_projects(lines: list[str]) -> list[dict]:
    """Line-based project detection that survives PDF wrapping.

    A project starts at a short, unpunctuated line (usually after a bullet or URL),
    a short comma list right after the title is treated as the technology stack, and
    bullet lines become the description.
    """
    projects: list[dict] = []
    current: dict | None = None
    previous_was_bullet = False

    def flush():
        nonlocal current
        if current and current.get("title"):
            current["description"] = clean_text(current.get("description", ""), 900)
            projects.append(current)
        current = None

    def add_description(text: str, new_bullet: bool) -> None:
        existing = current.get("description", "") if current else ""
        if not existing:
            current["description"] = text
        elif new_bullet:
            current["description"] = existing + "\n" + text
        else:
            current["description"] = existing + " " + text

    for raw in lines:
        if not raw.strip():
            flush()
            previous_was_bullet = False
            continue
        line = raw.strip()
        bullet = BULLET_RE.match(line)
        if bullet:
            content = clean_line(bullet.group(1), 500)
            if not content:
                continue
            if current is None:
                current = {"title": "Project", "description": "", "technologies": "", "url": ""}
            add_description(content, new_bullet=True)
            previous_was_bullet = True
            continue

        url_match = URL_RE.search(line)
        if url_match and len(line) <= 140:
            if current is None:
                current = {"title": "Project", "description": "", "technologies": "", "url": ""}
            current["url"] = normalise_url(url_match.group(0).rstrip(".,);"))
            previous_was_bullet = False
            continue

        tech_label = TECH_LABEL_RE.match(line)
        if tech_label and current is not None:
            current["technologies"] = clean_line(tech_label.group(1), 180)
            previous_was_bullet = False
            continue

        comma_parts = [part.strip() for part in line.split(",") if part.strip()]
        looks_like_tech = (
            2 <= len(comma_parts) <= 8
            and len(line) <= 100
            and all(len(part.split()) <= 4 for part in comma_parts)
            and not line.endswith(".")
        )
        if current is not None and not current.get("technologies") and not current.get("description") and looks_like_tech:
            current["technologies"] = clean_line(line, 180)
            previous_was_bullet = False
            continue

        title_like = len(line) <= 115 and not line.endswith(".") and not looks_like_tech
        if title_like and (current is None or previous_was_bullet or current.get("url")):
            flush()
            current = {"title": clean_line(line, 130), "description": "", "technologies": "", "url": ""}
            previous_was_bullet = False
            continue

        if current is None:
            current = {"title": clean_line(line, 130), "description": "", "technologies": "", "url": ""}
        else:
            add_description(line, new_bullet=False)
        previous_was_bullet = False

    flush()
    return [project for project in projects if project.get("title")][:8]


def _parse_certifications(lines: list[str]) -> list[dict]:
    cleaned = [line for line in _clean_section_lines(lines) if line]
    certs: list[dict] = []
    for raw_line in cleaned[:12]:
        line = raw_line.strip(" \t•▪◦·*-–—\x7f:")
        if len(line) < 4:
            continue

        issue_date = ""
        date_match = MONTH_DATE_RE.search(line)
        if date_match:
            issue_date = clean_line(date_match.group(0), 30)
            line = line[: date_match.start()] + " — " + line[date_match.end():]
        else:
            year = YEAR_RE.search(line)
            if year:
                issue_date = year.group(0)
                line = line[: year.start()] + " — " + line[year.end():]

        credential_id = ""
        credential = re.search(r"(?i)\b(?:credential\s*)?id\s*[:\-]?\s*([A-Za-z0-9\-]{4,})", line)
        if credential:
            credential_id = credential.group(1)
            line = line[: credential.start()] + " — " + line[credential.end():]

        url = ""
        url_match = URL_RE.search(line) or PROFILE_URL_RE.search(line)
        if url_match:
            url = normalise_url(url_match.group(0).rstrip(".,);"))
            line = line.replace(url_match.group(0), " ")

        parts = [
            clean_line(part, 120).strip(" :-–—|")
            for part in re.split(r"\s*[|–—]\s*|\s+-\s+|" + r"\s*,\s*(?=[A-Z])", line)
            if part.strip(" :-–—|")
        ]
        parts = [part for part in parts if not re.fullmatch(r"(?i)(verify|view|certificate link|see credential)", part)]
        name = parts[0] if parts else clean_line(line, 140)
        organization = ""
        for part in parts[1:]:
            if re.fullmatch(r"[\d\s\-–/]+", part):
                continue
            organization = part
            break
        certs.append(
            {
                "name": clean_line(name, 140),
                "organization": clean_line(organization, 120),
                "issue_date": issue_date,
                "credential_id": credential_id,
                "url": url,
            }
        )
    return certs


def _parse_experience(lines: list[str]) -> list[dict]:
    cleaned = _clean_section_lines(lines)
    blocks = _split_blocks(cleaned)
    merged: list[list[str]] = []
    for block in blocks:
        if merged and len(block) <= 2 and not YEAR_RANGE_RE.search(block[0]):
            merged[-1].extend(block)
        else:
            merged.append(block)
    jobs: list[dict] = []
    for block in merged[:8]:
        if not block:
            continue
        header = block[0]
        duration = ""
        duration_match = DURATION_RE.search(header) or YEAR_RANGE_RE.search(header)
        if duration_match:
            duration = clean_line(re.sub(r"(?i)\s+to\s+", " – ", duration_match.group(0)), 60)
            header = (header[: duration_match.start()] + " " + header[duration_match.end():]).strip(" |–—-")
        else:
            loose = DURATION_RE.search(" ".join(block[:2]))
            if loose:
                duration = clean_line(re.sub(r"(?i)\s+to\s+", " – ", loose.group(0)), 60)

        title = company = ""
        at_match = re.search(r"\s+(?:at|@)\s+", header, re.I)
        if at_match:
            title = clean_line(header[: at_match.start()], 120)
            company = clean_line(header[at_match.end():], 120)
        else:
            parts = [part for part in re.split(r"\s*[|•·]\s*|\s+[—–]\s+|\s+-\s+", header) if part.strip(" :-–—|")]
            parts = [clean_line(part, 120).strip(" :-–—|") for part in parts]
            if len(parts) >= 2:
                title, company = parts[0], parts[1]
            elif parts:
                title = parts[0]
        responsibilities = [line for line in block[1:] if line]
        jobs.append(
            {
                "company": company,
                "title": title,
                "duration": duration,
                "responsibilities": "\n".join(responsibilities[:8]),
                "achievements": "",
            }
        )
    return jobs


def parse_resume_text(text: str) -> dict:
    """Split extracted plain text into editable resume fields."""
    parsed = empty_parsed()
    if not text.strip():
        return parsed

    header_lines, sections = _split_sections(text)
    parsed["personal"] = _find_contact(header_lines, text)

    if sections.get("objective"):
        parsed["objective"] = clean_text(" ".join(line for line in sections["objective"] if line), 900)

    if sections.get("education"):
        parsed["education"] = _parse_education(sections["education"])

    if sections.get("skills"):
        parsed["skills"] = _parse_skills(sections["skills"])
    if not parsed["skills"]["technical"]:
        inline = re.search(r"(?i)(?:technical\s+)?skills\s*[:\-]\s*(.+)", text)
        if inline:
            parsed["skills"] = _parse_skills([inline.group(1)])

    if sections.get("projects"):
        parsed["projects"] = _parse_projects(sections["projects"])

    if sections.get("certifications"):
        parsed["certifications"] = _parse_certifications(sections["certifications"])

    experience_lines = sections.get("experience", [])
    if experience_lines:
        parsed["experience"] = _parse_experience(experience_lines)
        parsed["experience_status"] = "has" if parsed["experience"] else "fresher"

    # Confidence reflects how much of a resume we actually recovered.
    signals = sum(
        1
        for condition in (
            parsed["personal"]["full_name"],
            parsed["personal"]["email"],
            parsed["personal"]["phone"],
            parsed["objective"],
            parsed["education"],
            parsed["skills"]["technical"] or parsed["skills"]["soft"],
            parsed["projects"],
            parsed["certifications"],
            parsed["experience"],
        )
        if condition
    )
    parsed["confidence"] = round(signals / 9, 2)
    return parsed


def parse_resume_file(path: Path) -> dict:
    return extract_document(path)
