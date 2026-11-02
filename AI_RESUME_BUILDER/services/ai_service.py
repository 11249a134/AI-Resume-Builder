"""Optional OpenAI integration.

The product must work with no API key at all. Every function here either returns
real model output (and says so) or an honest rule-based fallback (and says that
too). Nothing ever claims an AI call succeeded when it did not.
"""

from __future__ import annotations

import os

from utils.helpers import clean_line, clean_text, split_items, word_count

DEFAULT_MODEL = "gpt-4o-mini"


def ai_status() -> dict:
    """Report whether the OpenAI integration is usable right now."""
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    model = (os.getenv("OPENAI_MODEL") or DEFAULT_MODEL).strip()
    if not key:
        return {
            "available": False,
            "model": model,
            "reason": "OPENAI_API_KEY is not configured — rule-based logic is used.",
        }
    try:
        import openai  # noqa: F401
    except ImportError:
        return {
            "available": False,
            "model": model,
            "reason": "The openai package is not installed — rule-based logic is used.",
        }
    return {"available": True, "model": model, "reason": "OpenAI is configured."}


def _chat(system: str, user: str, max_tokens: int = 320) -> str | None:
    """One short chat completion, or ``None`` if the integration is unavailable."""
    status = ai_status()
    if not status["available"]:
        return None
    try:
        from openai import OpenAI

        timeout = float(os.getenv("OPENAI_TIMEOUT", "25") or 25)
        client = OpenAI(api_key=(os.getenv("OPENAI_API_KEY") or "").strip(), timeout=timeout, max_retries=0)
        response = client.chat.completions.create(
            model=status["model"],
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.4,
            max_tokens=max_tokens,
        )
        text = (response.choices[0].message.content or "").strip()
        return text or None
    except Exception:  # network, quota, auth, timeout — all fall back safely
        return None


# --------------------------------------------------------------------------- #
# Career objective
# --------------------------------------------------------------------------- #
def _profile_bits(profile: dict) -> dict:
    skills = split_items(profile.get("skills") or "", 12)
    soft = split_items(profile.get("soft_skills") or "", 8)
    interests = split_items(profile.get("interests") or "", 8)
    degree = clean_line(profile.get("degree"), 90)
    department = clean_line(profile.get("department"), 90)
    qualification = clean_line(profile.get("qualification"), 60)
    return {
        "name": clean_line(profile.get("name"), 60),
        "degree": degree,
        "department": department,
        "qualification": qualification,
        "skills": skills,
        "soft": soft,
        "interests": interests,
        "role": clean_line(profile.get("target_role"), 80),
        "status": clean_line(profile.get("experience_status"), 12) or "fresher",
    }


def _join(items: list[str], limit: int = 3) -> str:
    picked = [item for item in items[:limit] if item]
    if not picked:
        return ""
    if len(picked) == 1:
        return picked[0]
    return ", ".join(picked[:-1]) + " and " + picked[-1]


def rule_based_objective(profile: dict) -> str:
    bits = _profile_bits(profile)
    study = " ".join(part for part in (bits["degree"], f"({bits['department']})" if bits["department"] else "") if part)
    study = study or bits["qualification"] or "graduate"

    if bits["status"] == "has":
        opener = f"Early-career professional with a background in {study}"
    elif bits["qualification"] and "student" in bits["qualification"].lower():
        opener = f"Final-year {study} student"
    else:
        opener = f"Recent {study} graduate"

    skill_line = f" and practical exposure to {_join(bits['skills'])}" if bits["skills"] else ""
    soft_line = f", supported by strong {_join(bits['soft'], 2)}" if bits["soft"] else ""
    direction = bits["role"] or (bits["interests"][0] if bits["interests"] else "a growth-focused technology role")
    value_clause = (
        "Eager to contribute to measurable business outcomes while deepening expertise in "
        + _join(bits["interests"] or bits["skills"], 2)
    ) if (bits["interests"] or bits["skills"]) else "Eager to contribute to real projects while building specialist expertise"

    text = f"{opener}{skill_line}{soft_line}. Seeking a {direction} position where I can apply analytical thinking and hands-on skills to deliver reliable results. {value_clause}."
    # Keep it tight: 45-75 words reads best at the top of a one-page resume.
    words = text.split()
    if len(words) > 78:
        text = " ".join(words[:78]).rstrip(",;") + "."
    return text


def generate_objective(profile: dict) -> dict:
    """Generate an editable career objective plus provenance metadata."""
    bits = _profile_bits(profile)
    system = (
        "You are a senior resume writer for early-career technology candidates. "
        "Write a single career objective of 45-70 words. First person implied but do not start every "
        "sentence with 'I'. No clichés, no invented employers, degrees, years of experience or metrics. "
        "Use only the facts supplied. Plain text, no headings, no markdown, no quotation marks."
    )
    user = (
        f"Name: {bits['name'] or 'Not provided'}\n"
        f"Qualification: {bits['qualification'] or 'Not provided'}\n"
        f"Degree: {bits['degree'] or 'Not provided'}\n"
        f"Department: {bits['department'] or 'Not provided'}\n"
        f"Technical skills: {', '.join(bits['skills']) or 'Not provided'}\n"
        f"Soft skills: {', '.join(bits['soft']) or 'Not provided'}\n"
        f"Interests: {', '.join(bits['interests']) or 'Not provided'}\n"
        f"Target role: {bits['role'] or 'Not provided'}\n"
        f"Experience level: {bits['status']}\n"
        "Return only the objective text."
    )
    text = _chat(system, user, max_tokens=220)
    if text:
        return {
            "text": clean_text(text.strip().strip('"'), 900),
            "source": "ai",
            "label": "Generated with OpenAI (editable)",
            "note": "AI-generated — review before submitting.",
        }
    reason = ai_status()["reason"]
    return {
        "text": rule_based_objective(profile),
        "source": "rule-based",
        "label": "Generated by rule-based writer (AI unavailable)",
        "note": reason,
    }


def polish_objective(text: str, profile: dict) -> dict:
    """Improve an existing objective; falls back to a deterministic rewrite."""
    existing = clean_text(text, 1200)
    status = ai_status()
    if status["available"] and existing:
        bits = _profile_bits(profile)
        system = (
            "Rewrite the supplied resume career objective. Keep every fact truthful, do not invent "
            "employers, degrees, tools or achievements. 45-70 words, ATS-friendly, plain text, no markdown, "
            "no heading, no quotation marks."
        )
        user = (
            f"Existing objective:\n{existing}\n\n"
            f"Facts available — skills: {', '.join(bits['skills']) or 'none listed'}; "
            f"interests: {', '.join(bits['interests']) or 'none listed'}; "
            f"target role: {bits['role'] or 'not specified'}; "
            f"degree: {bits['degree'] or 'not specified'}.\nReturn only the improved objective."
        )
        improved = _chat(system, user, max_tokens=220)
        if improved:
            return {
                "text": clean_text(improved.strip().strip('"'), 900),
                "source": "ai",
                "label": "Improved with OpenAI (editable)",
                "note": "AI-generated rewrite — review before submitting.",
            }
        note = "OpenAI could not be reached; the rule-based objective writer was used."
    else:
        note = status["reason"] if not status["available"] else "No objective text was provided."

    bits = _profile_bits(profile)
    has_facts = any((bits["degree"], bits["qualification"], bits["role"], bits["skills"], bits["interests"]))
    if not existing or has_facts:
        # The deterministic writer builds a complete 45-75 word objective from the
        # saved facts; it is a genuine rewrite, not a relabelled copy of the input.
        fallback = rule_based_objective(profile)
    else:
        sentences = [s.strip() for s in existing.replace("\n", " ").split(". ") if s.strip()]
        tightened = ". ".join(sentence[0].upper() + sentence[1:] for sentence in sentences[:3])
        fallback = tightened if tightened.endswith(".") else tightened + "."
        if word_count(fallback) < 20:
            fallback = rule_based_objective(profile)
    return {
        "text": fallback,
        "source": "rule-based",
        "label": "Rule-based improvement (AI unavailable)",
        "note": note,
    }


def ats_coach(score: int, findings: list[str], missing_keywords: list[str]) -> dict:
    """Optional AI coaching paragraph layered on top of deterministic findings."""
    status = ai_status()
    if not status["available"]:
        return {
            "text": "",
            "source": "rule-based",
            "note": "AI coaching is off; the suggestions below are generated from the scoring rules.",
        }
    system = (
        "You are an ATS resume coach. Given a resume quality score and the exact findings from a "
        "deterministic analyser, write 3 short sentences of specific, encouraging coaching. Do not "
        "invent new findings, new scores, employers or metrics."
    )
    user = (
        f"Score: {score}/100\nFindings:\n- " + "\n- ".join(findings[:8]) +
        f"\nMissing keywords: {', '.join(missing_keywords[:10]) or 'none'}\nReturn only the coaching text."
    )
    text = _chat(system, user, max_tokens=200)
    if not text:
        return {"text": "", "source": "rule-based", "note": "The AI coach did not respond; rule-based suggestions are shown."}
    return {"text": clean_text(text, 700), "source": "ai", "note": "AI coaching based on the deterministic findings above."}
