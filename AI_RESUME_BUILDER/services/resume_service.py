"""Resume data model, validation, storage and rendering helpers.

Every resume is a plain dictionary so that it can be serialised to JSON, rendered
by Jinja, forwarded to the PDF engine and analysed by the ATS service without any
conversion step in between.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from utils.helpers import (
    CERTIFICATE_EXTENSIONS,
    IMAGE_EXTENSIONS,
    clean_line,
    clean_text,
    is_email,
    new_id,
    normalise_url,
    now_iso,
    save_document_upload,
    save_image_upload,
    split_items,
    year_range,
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RESUMES_DIR = DATA_DIR / "resumes"
UPLOADS_DIR = DATA_DIR / "uploads"

#: Resume templates offered in the builder and the PDF engine.
TEMPLATES = [
    {
        "id": "modern",
        "name": "Modern Professional",
        "tagline": "Accent header, right-aligned photo, strong section rules.",
        "accent": "#4338ca",
    },
    {
        "id": "classic",
        "name": "Classic Serif",
        "tagline": "Centred header in serif type — traditional and ATS-safe.",
        "accent": "#111827",
    },
    {
        "id": "minimal",
        "name": "Minimal Clean",
        "tagline": "Airy single column with thin dividers and no colour blocks.",
        "accent": "#0f766e",
    },
]
TEMPLATE_IDS = {tpl["id"] for tpl in TEMPLATES}
DEFAULT_TEMPLATE = "modern"


def template_by_id(template_id: str | None) -> dict:
    for tpl in TEMPLATES:
        if tpl["id"] == (template_id or DEFAULT_TEMPLATE):
            return tpl
    return TEMPLATES[0]


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def ensure_dirs() -> None:
    for folder in (RESUMES_DIR, UPLOADS_DIR):
        folder.mkdir(parents=True, exist_ok=True)


def blank_resume(source: str = "created") -> dict:
    return {
        "id": "",
        "template": DEFAULT_TEMPLATE,
        "source": source,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "original_file": None,
        "personal": {
            "full_name": "",
            "email": "",
            "phone": "",
            "location": "",
            "linkedin": "",
            "github": "",
            "portfolio": "",
            "photo": "",
            "photo_original_name": "",
        },
        "objective": "",
        "target_role": "",
        "education": [],
        "skills": {"technical": [], "soft": []},
        "projects": [],
        "certifications": [],
        "experience": [],
        "experience_status": "has",
        "extraction": None,
    }


def normalise_resume(data: dict | None) -> dict:
    """Guarantee every key exists so templates never hit an undefined value."""
    base = blank_resume()
    if not isinstance(data, dict):
        return base
    for key, value in data.items():
        if key in {"personal", "skills"} and isinstance(value, dict):
            base[key].update(value)
        elif key in {"education", "projects", "certifications", "experience"} and isinstance(value, list):
            base[key] = [item for item in value if isinstance(item, dict)]
        elif key in base:
            base[key] = value
    for field in ("education", "projects", "certifications", "experience"):
        base[field] = _slice_entries(base[field])
    base["skills"] = {
        "technical": _string_list(base["skills"].get("technical")),
        "soft": _string_list(base["skills"].get("soft")),
    }
    base["personal"] = {key: (value if value is not None else "") for key, value in base["personal"].items()}
    if base["template"] not in TEMPLATE_IDS:
        base["template"] = DEFAULT_TEMPLATE
    if base["experience_status"] not in {"has", "fresher", "skip"}:
        base["experience_status"] = "has"
    return base


def _slice_entries(entries: list) -> list:
    return [entry for entry in entries if any(str(value).strip() for value in entry.values())][:25]


def _string_list(values) -> list[str]:
    if isinstance(values, str):
        return split_items(values)
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for item in values:
        text = clean_line(item, 80)
        if text and text.lower() not in {existing.lower() for existing in cleaned}:
            cleaned.append(text)
    return cleaned[:60]


def save_resume(resume: dict) -> dict:
    """Persist a resume to ``data/resumes/<id>.json`` and return it."""
    ensure_dirs()
    resume = normalise_resume(resume)
    if not resume["id"]:
        resume["id"] = new_id()
    resume["updated_at"] = now_iso()
    path = RESUMES_DIR / f"{resume['id']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(resume, indent=1), encoding="utf-8")
    tmp.replace(path)
    return resume


def get_resume(resume_id: str | None) -> dict | None:
    if not resume_id or not resume_id.replace("-", "").isalnum():
        return None
    path = RESUMES_DIR / f"{resume_id}.json"
    if not path.exists():
        return None
    try:
        return normalise_resume(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def upload_dir(resume_id: str) -> Path:
    folder = UPLOADS_DIR / resume_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def stored_path(relative: str | None) -> Path | None:
    """Resolve a stored uploads-relative path, refusing anything outside data/."""
    if not relative:
        return None
    candidate = (DATA_DIR / "uploads" / relative).resolve()
    try:
        candidate.relative_to(UPLOADS_DIR.resolve())
    except ValueError:
        return None
    return candidate if candidate.exists() else None


def delete_resume_files(resume_id: str) -> None:
    folder = UPLOADS_DIR / resume_id
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Derived facts used by templates, the ATS analyser and the career module
# --------------------------------------------------------------------------- #
def all_skills(resume: dict) -> list[str]:
    resume = normalise_resume(resume)
    return resume["skills"]["technical"] + resume["skills"]["soft"]


def section_presence(resume: dict) -> dict[str, bool]:
    resume = normalise_resume(resume)
    return {
        "contact": bool(resume["personal"]["full_name"] and resume["personal"]["email"]),
        "objective": len(clean_text(resume["objective"])) >= 20,
        "education": bool(resume["education"]),
        "skills": bool(all_skills(resume)),
        "projects": bool(resume["projects"]),
        "certifications": bool(resume["certifications"]),
        "experience": bool(resume["experience"]) and resume["experience_status"] == "has",
    }


def counted_sections(resume: dict) -> list[dict]:
    """Ordered section list with display counts, used for the preview sidebar."""
    resume = normalise_resume(resume)
    presence = section_presence(resume)
    return [
        {"key": "contact", "label": "Personal Information", "count": sum(1 for v in resume["personal"].values() if v), "present": presence["contact"]},
        {"key": "objective", "label": "Career Objective", "count": len(clean_text(resume["objective"]).split()), "present": presence["objective"]},
        {"key": "education", "label": "Education", "count": len(resume["education"]), "present": presence["education"]},
        {"key": "skills", "label": "Skills", "count": len(all_skills(resume)), "present": presence["skills"]},
        {"key": "projects", "label": "Projects", "count": len(resume["projects"]), "present": presence["projects"]},
        {"key": "certifications", "label": "Certifications", "count": len(resume["certifications"]), "present": presence["certifications"]},
        {"key": "experience", "label": "Experience", "count": len(resume["experience"]), "present": presence["experience"]},
    ]


def resume_to_text(resume: dict) -> str:
    """Flatten a resume to ATS-style plain text (used by the ATS analyser)."""
    resume = normalise_resume(resume)
    personal = resume["personal"]
    lines: list[str] = [personal["full_name"]]
    contact_bits = [personal["email"], personal["phone"], personal["location"]]
    contact_line = " | ".join(bit for bit in contact_bits if bit)
    if contact_line:
        lines.append(contact_line)
    links = [personal["linkedin"], personal["github"], personal["portfolio"]]
    if any(links):
        lines.append(" | ".join(link for link in links if link))

    if clean_text(resume["objective"]):
        lines += ["", "CAREER OBJECTIVE", resume["objective"]]
    if resume["education"]:
        lines += ["", "EDUCATION"]
        for entry in resume["education"]:
            head = " — ".join(filter(None, [entry.get("degree"), entry.get("department")]))
            years = year_range(entry.get("start_year"), entry.get("grad_year"))
            lines.append(" | ".join(filter(None, [entry.get("institution"), head, years, entry.get("score")])))
    skills = resume["skills"]
    if skills["technical"] or skills["soft"]:
        lines += ["", "SKILLS"]
        if skills["technical"]:
            lines.append("Technical: " + ", ".join(skills["technical"]))
        if skills["soft"]:
            lines.append("Soft: " + ", ".join(skills["soft"]))
    if resume["projects"]:
        lines += ["", "PROJECTS"]
        for project in resume["projects"]:
            lines.append(project.get("title", ""))
            if project.get("technologies"):
                lines.append("Technologies: " + project["technologies"])
            for bullet in _bullets(project.get("description")):
                lines.append(f"• {bullet}")
            if project.get("url"):
                lines.append(project["url"])
    if resume["certifications"]:
        lines += ["", "CERTIFICATIONS"]
        for cert in resume["certifications"]:
            lines.append(" | ".join(filter(None, [cert.get("name"), cert.get("organization"), cert.get("issue_date"), cert.get("credential_id")])))
    if resume["experience"] and resume["experience_status"] == "has":
        lines += ["", "EXPERIENCE"]
        for job in resume["experience"]:
            lines.append(" | ".join(filter(None, [job.get("title"), job.get("company"), job.get("duration")])))
            for bullet in _bullets(job.get("responsibilities") or job.get("description")):
                lines.append(f"• {bullet}")
            for bullet in _bullets(job.get("achievements")):
                lines.append(f"• {bullet}")
    elif resume["experience_status"] == "fresher":
        lines += ["", "EXPERIENCE", "Fresher — no professional experience yet."]
    return "\n".join(line for line in lines if line is not None).strip()


def _bullets(text: str | None) -> list[str]:
    raw = (text or "").replace("\r", "\n")
    parts = [clean_line(part, 400) for part in raw.split("\n")]
    bullets = [part.lstrip("•-*· ").strip() for part in parts if part.strip()]
    return [bullet for bullet in bullets if bullet]


# --------------------------------------------------------------------------- #
# Form parsing
# --------------------------------------------------------------------------- #
def parse_form(form, files, existing: dict | None = None) -> tuple[dict, list[str], list[str]]:
    """Turn the builder's ``request.form``/``request.files`` into a resume dict.

    Returns ``(resume, errors, warnings)``. Errors block generation; warnings are
    shown to the user but do not stop it (an unusable photo, for example).
    """
    errors: list[str] = []
    warnings: list[str] = []
    resume = normalise_resume(existing) if existing else blank_resume()
    resume["id"] = clean_line(form.get("resume_id"), 40) or resume.get("id") or new_id()

    personal = resume["personal"]
    personal["full_name"] = clean_line(form.get("full_name"), 90)
    personal["email"] = clean_line(form.get("email"), 120)
    personal["phone"] = clean_line(form.get("phone"), 40)
    personal["location"] = clean_line(form.get("location"), 120)
    personal["linkedin"] = normalise_url(form.get("linkedin"))
    personal["github"] = normalise_url(form.get("github"))
    personal["portfolio"] = normalise_url(form.get("portfolio"))

    for field, value in (("linkedin", form.get("linkedin")), ("github", form.get("github")), ("portfolio", form.get("portfolio"))):
        if clean_line(value) and not personal[field]:
            warnings.append(f"The {field.title()} URL looked invalid, so it was left off the resume.")

    resume["objective"] = clean_text(form.get("objective"), 1200)
    resume["target_role"] = clean_line(form.get("target_role"), 90)
    resume["template"] = clean_line(form.get("template"), 30) or resume["template"]

    # ---- photo ----------------------------------------------------------- #
    resume["experience_status"] = clean_line(form.get("experience_status"), 12) or "has"
    if resume["experience_status"] not in {"has", "fresher", "skip"}:
        resume["experience_status"] = "has"

    photo = files.get("photo") if files else None
    if form.get("remove_photo") == "1" and not (photo and photo.filename):
        personal["photo"] = ""
        personal["photo_original_name"] = ""
    if photo and photo.filename:
        stored, error = save_image_upload(photo, upload_dir(resume["id"]), max_bytes=int(form.get("max_photo_bytes") or 4 * 1024 * 1024))
        if error:
            warnings.append(error)
        else:
            personal["photo"] = f"{resume['id']}/{stored}"
            personal["photo_original_name"] = clean_line(photo.filename, 120)

    # ---- education ------------------------------------------------------- #
    institutions = form.getlist("edu_institution")
    education: list[dict] = []
    for index, institution in enumerate(institutions):
        entry = {
            "institution": clean_line(institution, 140),
            "degree": _at(form.getlist("edu_degree"), index, 120),
            "department": _at(form.getlist("edu_department"), index, 120),
            "start_year": _at(form.getlist("edu_start_year"), index, 12),
            "grad_year": _at(form.getlist("edu_grad_year"), index, 12),
            "score": _at(form.getlist("edu_score"), index, 40),
        }
        if any(entry.values()):
            education.append(entry)
    resume["education"] = education

    # ---- skills ---------------------------------------------------------- #
    resume["skills"] = {
        "technical": split_items(form.get("skills_technical")),
        "soft": split_items(form.get("skills_soft")),
    }

    # ---- projects -------------------------------------------------------- #
    projects: list[dict] = []
    for index, title in enumerate(form.getlist("project_title")):
        entry = {
            "title": clean_line(title, 120),
            "description": clean_text(_at(form.getlist("project_description"), index, 900), 900),
            "technologies": clean_line(_at(form.getlist("project_technologies"), index, 200), 200),
            "url": normalise_url(_at(form.getlist("project_url"), index, 300)),
        }
        if any(entry.values()):
            projects.append(entry)
    resume["projects"] = projects

    # ---- certifications -------------------------------------------------- #
    certs = resume["certifications"] if existing else []
    certifications: list[dict] = []
    for index, name in enumerate(form.getlist("cert_name")):
        previous = certs[index] if index < len(certs) else {}
        entry = {
            "name": clean_line(name, 140),
            "organization": _at(form.getlist("cert_org"), index, 120),
            "issue_date": clean_line(_at(form.getlist("cert_date"), index, 40), 40),
            "credential_id": _at(form.getlist("cert_id"), index, 80),
            "url": normalise_url(_at(form.getlist("cert_url"), index, 300)),
            "attachment": _at(form.getlist("cert_attachment"), index, 160) or previous.get("attachment", ""),
            "attachment_path": previous.get("attachment_path", ""),
        }
        upload = files.get(f"cert_file_{index}") if files else None
        if upload and upload.filename:
            stored, error = save_document_upload(
                upload, upload_dir(resume["id"]), CERTIFICATE_EXTENSIONS, int(form.get("max_upload_bytes") or 8 * 1024 * 1024), prefix="certificate"
            )
            if error:
                warnings.append(f"Certificate “{entry['name'] or index + 1}” attachment: {error}")
            else:
                entry["attachment"] = clean_line(upload.filename, 160)
                entry["attachment_path"] = f"{resume['id']}/{stored}"
        if form.get(f"cert_remove_attachment_{index}") == "1" and not (upload and upload.filename):
            entry["attachment"] = ""
            entry["attachment_path"] = ""
        if any(entry.values()):
            certifications.append(entry)
    resume["certifications"] = certifications

    # ---- experience ------------------------------------------------------ #
    experience: list[dict] = []
    if resume["experience_status"] == "has":
        for index, company in enumerate(form.getlist("exp_company")):
            entry = {
                "company": clean_line(company, 120),
                "title": _at(form.getlist("exp_title"), index, 120),
                "duration": clean_line(_at(form.getlist("exp_duration"), index, 60), 60),
                "responsibilities": clean_text(_at(form.getlist("exp_responsibilities"), index, 900), 900),
                "achievements": clean_text(_at(form.getlist("exp_achievements"), index, 600), 600),
            }
            if any(entry.values()):
                experience.append(entry)
        if not experience:
            warnings.append("You selected “I have experience” but added no entries — the resume keeps an empty experience section out.")
    resume["experience"] = experience

    # ---- validation ------------------------------------------------------ #
    if not personal["full_name"]:
        errors.append("Full name is required.")
    if not is_email(personal["email"]):
        errors.append("A valid email address is required.")
    if not education:
        errors.append("Add at least one education entry.")
    if not (resume["skills"]["technical"] or resume["skills"]["soft"]):
        errors.append("Add at least one skill (technical or professional).")

    return resume, errors, warnings


def _at(values: list[str], index: int, limit: int) -> str:
    if index >= len(values):
        return ""
    return clean_line(values[index], limit)


def merge_extracted(base: dict, extracted: dict) -> dict:
    """Merge freshly parsed resume data over an existing draft."""
    merged = normalise_resume(base)
    for key in ("objective", "target_role"):
        if extracted.get(key):
            merged[key] = extracted[key]
    if extracted.get("personal"):
        for field, value in extracted["personal"].items():
            if value and field in merged["personal"]:
                merged["personal"][field] = value
    for section in ("education", "projects", "certifications", "experience"):
        if extracted.get(section):
            merged[section] = _slice_entries(extracted[section])
    if extracted.get("skills"):
        merged["skills"] = {
            "technical": _string_list(extracted["skills"].get("technical")),
            "soft": _string_list(extracted["skills"].get("soft")),
        }
    if extracted.get("experience_status"):
        merged["experience_status"] = extracted["experience_status"]
    return merged


def photo_extension_ok(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS
