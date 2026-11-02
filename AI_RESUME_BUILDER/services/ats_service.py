"""Deterministic resume quality / ATS compatibility analysis.

This is an *estimated* compatibility score produced by an open scoring model, not
a result from any employer's proprietary applicant tracking system. Every point is
traceable to a named check, and every lost point produces a stated reason.
"""

from __future__ import annotations

import re

from services import ai_service, career_service, resume_service
from utils.helpers import clean_text, word_count

#: Category weights. They add up to exactly 100 points.
WEIGHTS = [
    ("contact", "Contact Information", 12),
    ("objective", "Career Objective", 10),
    ("education", "Education", 15),
    ("skills", "Technical & Soft Skills", 15),
    ("projects", "Projects", 15),
    ("certifications", "Certifications", 5),
    ("experience", "Experience", 8),
    ("keywords", "Relevant Keywords", 10),
    ("formatting", "Formatting", 6),
    ("readability", "Readability", 4),
]

ACTION_VERBS = {
    "built", "developed", "designed", "led", "implemented", "created", "improved", "automated",
    "analysed", "analyzed", "reduced", "increased", "delivered", "managed", "collaborated",
    "engineered", "deployed", "optimised", "optimized", "launched", "migrated", "tested",
    "researched", "trained", "mentored", "achieved", "integrated", "presented", "documented",
    "streamlined", "architected", "configured", "maintained", "published", "secured", "scaled",
}

DATE_RE = re.compile(
    r"^(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}"
    r"|\d{4}|\d{1,2}/\d{4}|\d{4}-\d{2}|\d{1,2}/\d{1,2}/\d{4}"
    r"|present|current|\d{4}\s*[–—-]\s*(?:\d{4}|present|current))$",
    re.I,
)


def _check(label: str, points: float, earned: float, evidence: str = "", deduction: str = "") -> dict:
    earned = max(0.0, min(points, earned))
    return {
        "label": label,
        "points": round(points, 1),
        "earned": round(earned, 1),
        "evidence": evidence,
        "deduction": deduction if earned < points else "",
        "passed": earned >= points - 0.01,
    }


def _category(key: str, label: str, max_points: float, checks: list[dict]) -> dict:
    earned = round(sum(item["earned"] for item in checks), 1)
    return {
        "key": key,
        "label": label,
        "score": earned,
        "max": max_points,
        "percent": round(earned / max_points * 100, 1) if max_points else 0,
        "checks": checks,
        "deductions": [f"{item['label']}: {item['deduction']}" for item in checks if item["deduction"]],
    }


def _bullets(resume: dict) -> list[str]:
    bullets: list[str] = []
    for project in resume.get("projects", []):
        bullets.extend(_lines(project.get("description", "")))
    for job in resume.get("experience", []):
        bullets.extend(_lines(job.get("responsibilities", "")))
        bullets.extend(_lines(job.get("achievements", "")))
    return [bullet for bullet in bullets if bullet]


def _lines(text: str | None) -> list[str]:
    if not text:
        return []
    parts = [part.strip(" •-*·") for part in re.split(r"[\n\r]+", str(text))]
    return [part for part in parts if len(part) > 3]


# --------------------------------------------------------------------------- #
# Category scoring
# --------------------------------------------------------------------------- #
def _score_contact(resume: dict) -> dict:
    personal = resume["personal"]
    checks = []
    name = personal.get("full_name", "").strip()
    checks.append(_check("Full name present", 3, 3 if len(name.split()) >= 2 else (1.5 if name else 0),
                         evidence=name, deduction="Add your full name as it should appear to employers."))
    email = personal.get("email", "").strip()
    checks.append(_check("Professional email address", 3, 3 if re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", email) else 0,
                         evidence=email, deduction="Add a valid email address in the header."))
    digits = re.sub(r"\D", "", personal.get("phone", ""))
    checks.append(_check("Phone number", 2, 2 if 10 <= len(digits) <= 15 else 0,
                         evidence=personal.get("phone", ""), deduction="Add a reachable phone number with country/area code."))
    checks.append(_check("Location", 1.5, 1.5 if personal.get("location") else 0,
                         evidence=personal.get("location", ""), deduction="Add city and country so recruiters can judge location fit."))
    links = [link for link in (personal.get("linkedin"), personal.get("github"), personal.get("portfolio")) if link]
    checks.append(_check("Professional profile link", 2.5, 2.5 if links else 0,
                         evidence=", ".join(links), deduction="Add a LinkedIn, GitHub or portfolio link."))
    return _category("contact", "Contact Information", 12, checks)


def _score_objective(resume: dict) -> dict:
    objective = clean_text(resume.get("objective", ""))
    words = word_count(objective)
    role = resume.get("target_role", "") or ""
    technical = resume.get("skills", {}).get("technical", [])
    mentioned = sum(1 for skill in technical if re.search(rf"\b{re.escape(skill.lower())}\b", objective.lower()))
    checks = [
        _check("Career objective written", 4, 4 if words >= 15 else (2 if words else 0),
               evidence=f"{words} words", deduction="Write a 25–70 word objective that states what role you want."),
        _check("Concise length", 3, 3 if 20 <= words <= 85 else (1.5 if words > 85 else 0),
               evidence=f"{words} words", deduction="Trim the objective to roughly 25–70 words so recruiters can scan it."),
        _check("Targets a role or specific skills", 3, 3 if role or mentioned >= 2 else (1 if mentioned == 1 else 0),
               evidence=role or f"{mentioned} skills named", deduction="Name the role you are targeting and one or two relevant skills."),
    ]
    return _category("objective", "Career Objective", 10, checks)


def _score_education(resume: dict) -> dict:
    entries = resume.get("education", [])
    complete = [entry for entry in entries if entry.get("institution") and entry.get("degree")]
    with_years = [entry for entry in entries if entry.get("start_year") or entry.get("grad_year")]
    with_score = [entry for entry in entries if entry.get("score")]
    checks = [
        _check("Education section present", 6, 6 if entries else 0, evidence=f"{len(entries)} entry/entries",
               deduction="Add at least one education entry with institution and degree."),
        _check("Institution and degree", 3, 3 if complete else 0, evidence=f"{len(complete)} complete",
               deduction="Include both the institution name and the degree for each entry."),
        _check("Study years", 3, 3 if with_years else 0, evidence=f"{len(with_years)} with dates",
               deduction="Add start and graduation years — ATS parsers use them for ordering."),
        _check("Academic score", 3, 3 if with_score else 0, evidence=f"{len(with_score)} with score",
               deduction="Add CGPA or percentage; many fresher filters look for it."),
    ]
    return _category("education", "Education", 15, checks)


def _score_skills(resume: dict, keyword_info: dict) -> dict:
    technical = resume.get("skills", {}).get("technical", [])
    soft = resume.get("skills", {}).get("soft", [])
    total = len(technical) + len(soft)
    target_match = keyword_info["matched"][:2]
    clean_labels = all(len(skill) <= 45 for skill in technical + soft) and len({s.lower() for s in technical + soft}) == total
    checks = [
        _check("Technical skills listed", 5, min(5, len(technical)), evidence=f"{len(technical)} technical skills",
               deduction="List at least five technical skills you can defend in an interview."),
        _check("Overall skill coverage", 3, 3 if total >= 8 else round(total / 8 * 3, 1), evidence=f"{total} skills total",
               deduction="Aim for 8–14 focused skills rather than a very short list."),
        _check("Soft skills included", 3, min(3, len(soft) * 1.5), evidence=f"{len(soft)} soft skills",
               deduction="Add two or three soft skills backed by evidence in your projects."),
        _check("Clean skill labels", 2, 2 if clean_labels else 1, evidence="No duplicates or overlong labels",
               deduction="Remove duplicate or sentence-length skill labels."),
        _check("Skills relevant to target role", 2, min(2, len(target_match)), evidence=", ".join(target_match),
               deduction=f"Add role-relevant skills such as {', '.join(keyword_info['missing'][:3]) or 'the missing keywords'}."),
    ]
    return _category("skills", "Technical & Soft Skills", 15, checks)


def _score_projects(resume: dict) -> dict:
    projects = resume.get("projects", [])
    described = [project for project in projects if word_count(project.get("description", "")) >= 20]
    with_tech = [project for project in projects if project.get("technologies")]
    with_link = [project for project in projects if project.get("url")]
    checks = [
        _check("Project section present", 5, 5 if projects else 0, evidence=f"{len(projects)} project(s)",
               deduction="Add at least one project — it is the strongest evidence for a fresher resume."),
        _check("Portfolio depth", 3, 3 if len(projects) >= 2 else (1.5 if projects else 0), evidence=f"{len(projects)} projects",
               deduction="Add a second project so reviewers can see range and consistency."),
        _check("Descriptions explain the work", 4, round(4 * len(described) / len(projects), 1) if projects else 0,
               evidence=f"{len(described)} of {len(projects)} have 20+ word descriptions",
               deduction="Expand each project description: problem, your approach, tools and measurable result."),
        _check("Technologies stated", 2, round(2 * len(with_tech) / len(projects), 1) if projects else 0,
               evidence=f"{len(with_tech)} of {len(projects)} list technologies",
               deduction="List the technologies used so keyword matching can find them."),
        _check("Project link provided", 1, 1 if with_link else 0, evidence=f"{len(with_link)} link(s)",
               deduction="Add a repository or live demo link for at least one project."),
    ]
    return _category("projects", "Projects", 15, checks)


def _score_certifications(resume: dict) -> dict:
    certifications = resume.get("certifications", [])
    detailed = [cert for cert in certifications if cert.get("organization") and cert.get("issue_date")]
    checks = [
        _check("Certifications listed", 3, 3 if certifications else 0, evidence=f"{len(certifications)} certification(s)",
               deduction="Add relevant certifications, or remove the section if you have none."),
        _check("Issuer and date included", 2, round(2 * len(detailed) / len(certifications), 1) if certifications else 0,
               evidence=f"{len(detailed)} complete", deduction="Add the issuing organisation and issue date for each certificate."),
    ]
    return _category("certifications", "Certifications", 5, checks)


def _score_experience(resume: dict) -> dict:
    status = resume.get("experience_status", "has")
    entries = resume.get("experience", [])
    if status != "has" or not entries:
        reason = ("No experience section — expected for a fresher, but these 8 points cannot be earned."
                  if status in {"fresher", "skip"} else "No experience entries were added.")
        checks = [
            _check("Experience entries", 3, 0, deduction=reason),
            _check("Responsibilities described", 3, 0, deduction="Add internships or freelance work if you have any."),
            _check("Achievements quantified", 2, 0, deduction="Add measurable achievements where possible."),
        ]
        return _category("experience", "Experience", 8, checks)

    with_resp = [job for job in entries if word_count(job.get("responsibilities", "")) >= 10]
    with_ach = [job for job in entries if word_count(job.get("achievements", "")) >= 5]
    checks = [
        _check("Experience entries", 3, 3, evidence=f"{len(entries)} role(s)"),
        _check("Responsibilities described", 3, 3 if with_resp else round(1.5 * len(with_resp), 1),
               evidence=f"{len(with_resp)} of {len(entries)} described",
               deduction="Describe what you owned in each role using action verbs."),
        _check("Achievements quantified", 2, round(2 * len(with_ach) / len(entries), 1) if entries else 0,
               evidence=f"{len(with_ach)} with achievements",
               deduction="Add at least one measurable achievement per role."),
    ]
    return _category("experience", "Experience", 8, checks)


def _score_keywords(resume: dict, keyword_info: dict) -> dict:
    expected = keyword_info["expected"]
    matched = keyword_info["matched"]
    missing = keyword_info["missing"]
    ratio = len(matched) / len(expected) if expected else 0
    checks = [
        _check(
            f"Role keywords for {keyword_info['target']}",
            10,
            round(ratio * 10, 1),
            evidence=f"{len(matched)} of {len(expected)} expected keywords found",
            deduction=(
                "Missing keywords: " + ", ".join(missing[:8]) + "."
                if missing else ""
            ),
        ),
    ]
    return _category("keywords", "Relevant Keywords", 10, checks)


def _score_formatting(resume: dict, raw_text: str, meta: dict, mode: str) -> dict:
    text = raw_text or resume_service.resume_to_text(resume)
    lines = [line for line in text.splitlines() if line.strip()]
    long_lines = [line for line in lines if len(line) > 115]
    bullets = _bullets(resume)
    dates: list[str] = []
    for entry in resume.get("education", []):
        dates += [entry.get("start_year", ""), entry.get("grad_year", "")]
    for cert in resume.get("certifications", []):
        dates.append(cert.get("issue_date", ""))
    for job in resume.get("experience", []):
        dates.extend(part.strip() for part in re.split(r"[–—-]", job.get("duration", "")) if part.strip())
    dates = [date for date in dates if date]
    bad_dates = [date for date in dates if not DATE_RE.match(date.strip())]
    email_visible = bool(re.search(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", text[:1200]))
    has_tables = bool(meta.get("has_tables"))

    checks = [
        _check("Selectable text (not a scanned image)", 1, 1 if word_count(text) >= 120 or mode == "structured" else 0,
               evidence=f"{word_count(text)} words of text",
               deduction="The file has little selectable text; ATS software cannot read a scanned image. Export a text-based PDF."),
        _check("Bullet points used", 1, 1 if len(bullets) >= 2 else 0, evidence=f"{len(bullets)} bullet lines",
               deduction="Use short bullet points instead of paragraphs for projects and experience."),
        _check("Readable line lengths", 1, 0 if (long_lines and len(long_lines) > max(2, len(lines) * 0.1)) else 1,
               evidence=f"{len(long_lines)} long line(s)", deduction="Keep lines under about 115 characters so parsers do not merge fields."),
        _check("No table-based layout", 1, 0 if has_tables else 1, evidence="Tables detected" if has_tables else "No tables detected",
               deduction="Replace tables with simple headings and bullet lines; ATS parsers often scramble table content."),
        _check("Contact details in the text layer", 1, 1 if email_visible else 0,
               evidence="Email visible in text" if email_visible else "Email not found in text",
               deduction="Put your email as plain selectable text in the header, not in an image or text box."),
        _check("Consistent date formats", 1, 0 if bad_dates else 1,
               evidence="Dates parse cleanly" if not bad_dates else ", ".join(bad_dates[:3]),
               deduction="Use one date format (e.g. 'Jun 2024' or '2022 – 2024') everywhere."),
    ]
    return _category("formatting", "Formatting", 6, checks)


def _score_readability(resume: dict, raw_text: str) -> dict:
    bullets = _bullets(resume)
    lengths = [word_count(bullet) for bullet in bullets] or [0]
    average = round(sum(lengths) / len(lengths), 1) if bullets else 0
    action_start = sum(1 for bullet in bullets if bullet.split()[0].strip(",.").lower() in ACTION_VERBS)
    ratio = round(action_start / len(bullets) * 100, 0) if bullets else 0
    objective = clean_text(resume.get("objective", ""))
    objective_words = word_count(objective)
    first_person = bool(re.match(r"(?i)^\s*i\b", objective))
    caps_lines = [line for line in (raw_text or "").splitlines() if line.isupper() and len(line.split()) > 6]

    checks = [
        _check("Bullet length in a scannable range", 1.5, 1.5 if bullets and 8 <= average <= 24 else 0.75 if bullets else 0,
               evidence=f"Average {average} words per bullet",
               deduction="Aim for 10–20 words per bullet: long enough to show impact, short enough to scan."),
        _check("Action verbs lead the bullets", 1, round(min(1, ratio / 50), 1), evidence=f"{int(ratio)}% of bullets start with an action verb",
               deduction="Start bullets with verbs such as Built, Designed, Automated or Improved."),
        _check("Concise objective", 1, 1 if 0 < objective_words <= 80 else (0.5 if objective_words > 80 else 0),
               evidence=f"{objective_words} words", deduction="Keep the objective under 80 words so it is read in full."),
        _check("Professional voice", 0.5, 0.5 if not first_person and not caps_lines else 0,
               evidence="Third-person objective, no shouting" if not first_person and not caps_lines else "First-person or all-caps text found",
               deduction="Avoid 'I' openings and long ALL-CAPS lines; write in concise professional English."),
    ]
    category = _category("readability", "Readability", 4, checks)
    category["metrics"] = {"average_bullet_words": average, "action_verb_percent": int(ratio), "objective_words": objective_words}
    return category


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #
def keywords_for(resume: dict, target_role: str | None) -> dict:
    """Resolve the keyword target and compare it with the resume's content."""
    inferred = None
    target_name = (target_role or resume.get("target_role") or "").strip()
    career = career_service.career_by_name(target_name) if target_name else None
    if not career:
        skills = resume_service.all_skills(resume)
        if skills:
            career, _ranking = career_service.infer_role(skills)
        if career:
            target_name = f"{career['name']} (inferred from your skills)"
        else:
            target_name = target_name or "General technology roles"

    expected, label = career_service.expected_keywords(career["id"] if career else target_name)
    text = resume_service.resume_to_text(resume)
    candidates = list(resume_service.all_skills(resume))
    candidates += [line.strip() for line in text.splitlines() if line.strip()]
    matched = [keyword for keyword in expected if any(career_service.term_matches(keyword, candidate) for candidate in candidates)]
    missing = [keyword for keyword in expected if keyword not in matched]
    return {
        "expected": expected,
        "matched": matched,
        "missing": missing,
        "target": label,
        "career": career,
        "target_role": target_name,
    }


def analyze(
    resume: dict,
    *,
    raw_text: str = "",
    meta: dict | None = None,
    target_role: str | None = None,
    mode: str = "structured",
) -> dict:
    """Score a resume and produce strengths, gaps, suggestions and learning steps."""
    resume = resume_service.normalise_resume(resume)
    meta = meta or {}
    keyword_info = keywords_for(resume, target_role)

    categories = [
        _score_contact(resume),
        _score_objective(resume),
        _score_education(resume),
        _score_skills(resume, keyword_info),
        _score_projects(resume),
        _score_certifications(resume),
        _score_experience(resume),
        _score_keywords(resume, keyword_info),
        _score_formatting(resume, raw_text, meta, mode),
        _score_readability(resume, raw_text),
    ]
    total = round(sum(category["score"] for category in categories), 1)
    score = int(round(total))

    if score >= 85:
        grade, grade_class = "Excellent — ATS ready", "excellent"
    elif score >= 70:
        grade, grade_class = "Strong — small fixes needed", "strong"
    elif score >= 55:
        grade, grade_class = "Moderate — several gaps", "moderate"
    else:
        grade, grade_class = "Needs work", "weak"

    presence = resume_service.section_presence(resume)
    optional_missing = []
    if not presence["experience"]:
        optional_missing.append("Experience (optional for freshers)")

    strengths = _strengths(categories, resume, keyword_info)
    weaknesses = _weaknesses(categories)
    suggestions = _suggestions(resume, categories, keyword_info, presence)
    learning = _learning_plan(resume, keyword_info)

    coach = ai_service.ats_coach(
        score,
        [f"{category['label']}: {category['deductions'][0]}" for category in categories if category["deductions"]],
        keyword_info["missing"],
    )

    return {
        "score": score,
        "total_points": round(total, 1),
        "grade": grade,
        "grade_class": grade_class,
        "categories": categories,
        "weights": [{"key": key, "label": label, "points": points} for key, label, points in WEIGHTS],
        "presence": presence,
        "missing_sections": [label for key, label in (
            ("contact", "Contact Information"), ("objective", "Career Objective"), ("education", "Education"),
            ("skills", "Skills"), ("projects", "Projects"), ("certifications", "Certifications"),
        ) if not presence[key]],
        "optional_missing": optional_missing,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "suggestions": suggestions,
        "keyword_info": keyword_info,
        "missing_keywords": keyword_info["missing"][:18],
        "found_keywords": keyword_info["matched"],
        "learning": learning,
        "coach": coach,
        "mode": mode,
        "mode_label": "Structured builder data" if mode == "structured" else "Extracted from uploaded file",
        "consumer_note": (
            "Estimated ATS compatibility / resume-quality score from this app's open rule set. "
            "It is not a score from any employer's proprietary ATS."
        ),
        "scoring_method": "Deterministic rule-based engine (no random or fixed scores).",
        "metrics": {
            "word_count": word_count(raw_text) or word_count(resume_service.resume_to_text(resume)),
            "bullet_count": len(_bullets(resume)),
            "extraction": meta,
        },
    }


def _strengths(categories: list[dict], resume: dict, keyword_info: dict) -> list[str]:
    strength_map = {
        "contact": "Complete contact block so recruiters can reach you and verify your profiles.",
        "objective": "A focused objective that names your target role or core skills.",
        "education": "Education details are complete with institution, degree and dates.",
        "skills": "A broad, role-relevant skill set that ATS keyword matching can recognise.",
        "projects": "Project descriptions with technologies and outcomes — strong evidence for freshers.",
        "certifications": "Certifications are documented with issuer and date.",
        "experience": "Experience entries describe responsibilities and measurable achievements.",
        "keywords": f"Good keyword coverage for {keyword_info['target']}.",
        "formatting": "Clean, parser-friendly formatting with selectable text and consistent dates.",
        "readability": "Short, action-led bullets that are easy to scan.",
    }
    strengths = []
    for category in categories:
        if category["percent"] >= 75:
            strengths.append(strength_map.get(category["key"], category["label"]))
    if not strengths:
        strengths.append("The resume has a starting structure — use the suggestions below to build it up.")
    return strengths[:6]


def _weaknesses(categories: list[dict]) -> list[str]:
    weaknesses = []
    for category in sorted(categories, key=lambda item: item["percent"]):
        if category["percent"] < 60:
            for deduction in category["deductions"][:2]:
                weaknesses.append(f"{category['label']} — {deduction}")
    return weaknesses[:6]


def _suggestions(resume: dict, categories: list[dict], keyword_info: dict, presence: dict) -> list[dict]:
    suggestions: list[dict] = []
    for category in categories:
        if category["percent"] < 70:
            for check in category["checks"]:
                if check["deduction"]:
                    suggestions.append({
                        "title": check["label"],
                        "detail": check["deduction"],
                        "category": category["label"],
                        "priority": "High" if category["percent"] < 45 else "Medium",
                    })
    if keyword_info["missing"]:
        names = ", ".join(keyword_info["missing"][:6])
        suggestions.append({
            "title": "Add the missing role keywords",
            "detail": f"Work these into real project bullets where true: {names}. Do not keyword-stuff — show where you used them.",
            "category": "Keywords",
            "priority": "High",
        })
    short_projects = [p for p in resume.get("projects", []) if word_count(p.get("description", "")) < 20]
    if short_projects:
        suggestions.append({
            "title": "Use a problem–action–result structure",
            "detail": "For each project say what problem it solved, what you built and one measurable result (accuracy, time saved, users).",
            "category": "Projects",
            "priority": "Medium",
        })
    if not presence["certifications"]:
        career = keyword_info.get("career")
        if career and career.get("certifications"):
            suggestions.append({
                "title": "Add a relevant certification",
                "detail": f"Consider {career['certifications'][0]} or {career['certifications'][1]} for {career['name']} roles.",
                "category": "Certifications",
                "priority": "Low",
            })
    if resume.get("experience_status") in {"fresher", "skip"} and not resume.get("projects"):
        suggestions.append({
            "title": "Strengthen projects to offset missing experience",
            "detail": "With no work experience, two well-described projects with links are the strongest evidence you can add.",
            "category": "Experience",
            "priority": "High",
        })
    # De-duplicate by title while keeping the highest priority first.
    order = {"High": 0, "Medium": 1, "Low": 2}
    unique: dict[str, dict] = {}
    for item in suggestions:
        key = item["title"].lower()
        if key not in unique or order[item["priority"]] < order[unique[key]["priority"]]:
            unique[key] = item
    return sorted(unique.values(), key=lambda item: order[item["priority"]])[:9]


def _learning_plan(resume: dict, keyword_info: dict) -> dict:
    career = keyword_info.get("career")
    skills = resume_service.all_skills(resume)
    if not career:
        best, ranking = career_service.infer_role(skills)
        career = best
    if not career:
        return {"career": None, "roadmap": [], "resources": [], "skills_to_improve": []}
    profile = {"skills": skills, "interests": []}
    missing = [skill for skill in career["technical_skills"] if not any(career_service.term_matches(skill, item) for item in skills)]
    return {
        "career": {"id": career["id"], "name": career["name"], "category": career["category"]},
        "roadmap": career_service.roadmap_for(career, skills),
        "resources": career_service.resources_for_skills(missing, career)[:8],
        "skills_to_improve": missing[:8],
    }


def analyse_upload(file_path, original_name: str = "", target_role: str = "") -> dict:
    """Extract a file, score it, and return everything the result page needs."""
    from services import extract_service

    extracted = extract_service.extract_document(file_path)
    parsed = extracted["parsed"]
    resume = resume_service.blank_resume(source="uploaded")
    resume["personal"].update({key: value for key, value in parsed["personal"].items() if value})
    resume["objective"] = parsed["objective"]
    resume["education"] = parsed["education"]
    resume["skills"] = parsed["skills"]
    resume["projects"] = parsed["projects"]
    resume["certifications"] = parsed["certifications"]
    resume["experience"] = parsed["experience"]
    resume["experience_status"] = parsed["experience_status"]
    resume["original_file"] = {"name": original_name, "path": ""}
    analysis = analyze(
        resume,
        raw_text=extracted["text"],
        meta=extracted["meta"],
        target_role=target_role,
        mode="extracted",
    )
    analysis["extraction"] = {
        "warnings": extracted["warnings"],
        "scanned": extracted["scanned"],
        "confidence": parsed["confidence"],
        "meta": extracted["meta"],
        "preview_text": extracted["text"][:1800],
        "parsed_counts": {
            "education": len(parsed["education"]),
            "skills": len(parsed["skills"]["technical"]) + len(parsed["skills"]["soft"]),
            "projects": len(parsed["projects"]),
            "certifications": len(parsed["certifications"]),
            "experience": len(parsed["experience"]),
        },
    }
    analysis["resume"] = resume
    return analysis
