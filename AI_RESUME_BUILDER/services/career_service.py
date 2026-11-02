"""Rule-based career matching, roadmaps and learning resources.

Scoring is fully deterministic and deliberately simple to explain:

    Career Match % = (Skills Match % x 0.60) + (Interests Match % x 0.40)

Skills and interests are compared against each career profile after synonym
normalisation, so "ML", "Machine Learning" and "machine-learning" are one skill.
No randomness, no hidden boosts and no invented percentages.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from utils.helpers import clean_line, split_items

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "career_data.json"

SKILL_WEIGHT = 0.60
INTEREST_WEIGHT = 0.40

#: Aliases mapped to one canonical training term.
SYNONYMS = {
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "genai": "generative ai",
    "gen ai": "generative ai",
    "llm": "generative ai",
    "large language models": "generative ai",
    "large language model": "generative ai",
    "data analysis": "data analytics",
    "data analytic": "data analytics",
    "data analytics": "data analytics",
    "data visualisation": "data visualization",
    "js": "javascript",
    "java script": "javascript",
    "node": "nodejs",
    "node js": "nodejs",
    "node.js": "nodejs",
    "reactjs": "react",
    "react js": "react",
    "powerbi": "power bi",
    "power-bi": "power bi",
    "html5": "html",
    "css3": "css",
    "ui ux": "ui ux",
    "ux ui": "ui ux",
    "ui/ux": "ui ux",
    "ui design": "ui ux",
    "ux design": "ui ux",
    "user experience": "ui ux",
    "user interface design": "ui ux",
    "computer vision": "computer vision",
    "cv": "computer vision",
    "nlp": "natural language processing",
    "natural language processing": "natural language processing",
    "dl": "deep learning",
    "object oriented programming": "object oriented programming",
    "oop": "object oriented programming",
    "oo programming": "object oriented programming",
    "dsa": "data structures and algorithms",
    "data structures": "data structures and algorithms",
    "data structures and algorithm": "data structures and algorithms",
    "algorithms": "data structures and algorithms",
    "github": "git",
    "git and github": "git",
    "ci cd": "ci cd",
    "cicd": "ci cd",
    "ci/cd": "ci cd",
    "continuous integration": "ci cd",
    "k8s": "kubernetes",
    "amazon web services": "aws",
    "google cloud platform": "google cloud",
    "google cloud": "google cloud",
    "gcp": "google cloud",
    "microsoft azure": "azure",
    "sql server": "sql",
    "mysql": "sql",
    "postgresql": "sql",
    "postgres": "sql",
    "sqlite": "sql",
    "ms excel": "excel",
    "advanced excel": "excel",
    "microsoft excel": "excel",
    "excel vlookup": "excel",
    "rest apis": "rest api",
    "restful api": "rest api",
    "restful apis": "rest api",
    "api": "rest api",
    "apis": "rest api",
    "api development": "rest api",
    "problem solving": "problem solving",
    "problem-solving": "problem solving",
    "team work": "teamwork",
    "team-work": "teamwork",
    "communication skills": "communication",
    "financial modelling": "financial modeling",
    "statistical analysis": "statistics",
    "stats": "statistics",
    "power query": "power bi",
    "data cleaning": "data cleaning",
    "data wrangling": "data cleaning",
    "spreadsheets": "excel",
    "unity3d": "unity",
    "unity 3d": "unity",
    "c sharp": "c#",
    "c++": "cpp",
    "cpp": "cpp",
    "adobe photoshop": "photoshop",
    "adobe illustrator": "illustrator",
    "figma design": "figma",
    "penetration testing": "penetration testing",
    "pen testing": "penetration testing",
    "pentesting": "penetration testing",
    "ethical hacking": "penetration testing",
    "web security": "web security",
    "owasp top 10": "web security",
    "kali": "kali linux",
    "incident response": "incident response",
    "financial analysis": "financial analysis",
    "financial modelling and valuation": "financial modeling",
    "project management": "project management",
    "pm": "project management",
    "agile scrum": "agile",
    "scrum": "agile",
    "kanban": "agile",
    "machine-learning": "machine learning",
    "machine learning engineering": "machine learning",
    "artificial intelligence": "artificial intelligence",
    "artificial intelligence and data science": "artificial intelligence",
    "artificial intelligence & data science": "artificial intelligence",
    "digital art": "digital art",
    "illustration": "illustration",
    "video editing": "video editing",
    "premiere pro": "premiere pro",
    "after effects": "after effects",
    "davinci resolve": "davinci resolve",
    "content writing": "content writing",
    "copywriting": "content writing",
    "seo writing": "seo",
    "search engine optimization": "seo",
    "search engine optimisation": "seo",
    "google ads": "google ads",
    "social media marketing": "social media marketing",
    "email marketing": "email marketing",
    "digital marketing": "digital marketing",
    "business analysis": "business analysis",
    "business intelligence": "business intelligence",
    "requirement gathering": "requirement gathering",
    "requirements gathering": "requirement gathering",
    "process modeling": "process modeling",
    "process modelling": "process modeling",
    "hr": "human resources",
    "human resource": "human resources",
    "human resources": "human resources",
    "recruitment": "recruitment",
    "product management": "product management",
    "product strategy": "product strategy",
    "roadmapping": "roadmapping",
    "roadmap planning": "roadmapping",
    "classroom management": "classroom management",
    "lesson planning": "lesson planning",
    "teaching": "teaching",
    "curriculum development": "curriculum development",
    "cad": "cad",
    "solidworks": "cad",
    "autocad": "cad",
    "finite element analysis": "finite element analysis",
    "fea": "finite element analysis",
    "manufacturing": "manufacturing",
    "materials science": "materials science",
    "structural analysis": "structural analysis",
    "surveying": "surveying",
    "circuit design": "circuit design",
    "power systems": "power systems",
    "control systems": "control systems",
    "plc": "plc",
    "embedded systems": "embedded systems",
    "molecular biology": "molecular biology",
    "cell culture": "cell culture",
    "bioinformatics": "bioinformatics",
    "pcr": "pcr",
    "lab techniques": "lab techniques",
    "bioprocess engineering": "bioprocess engineering",
    "research methodology": "research methodology",
    "scientific writing": "scientific writing",
    "literature review": "literature review",
    "experimental design": "experimental design",
    "critical thinking": "critical thinking",
    "public speaking": "public speaking",
    "leadership": "leadership",
    "time management": "time management",
    "attention to detail": "attention to detail",
    "analytical thinking": "analytical thinking",
    "stakeholder management": "stakeholder management",
    "client management": "client management",
    "business acumen": "business acumen",
    "storytelling": "storytelling",
    "creativity": "creativity",
    "adaptability": "adaptability",
    "collaboration": "collaboration",
    "persistence": "persistence",
    "patience": "patience",
    "empathy": "empathy",
    "integrity": "integrity",
    "curiosity": "curiosity",
    "negotiation": "negotiation",
    "conflict resolution": "conflict resolution",
    "business skills": "business acumen",
    "commercial awareness": "business acumen",
}

#: Words too generic to prove a skill match on their own.
GENERIC_TOKENS = {
    "data", "analysis", "analytics", "design", "development", "management", "engineering",
    "science", "programming", "systems", "system", "applications", "application", "technology",
    "technologies", "tools", "basics", "fundamentals", "concepts", "skills", "knowledge",
    "software", "digital", "business", "visual", "creative", "professional", "advanced",
    "cloud", "web", "mobile", "game", "testing", "automation", "security", "marketing",
}

#: Lower-level skills that belong in the beginner stage of a roadmap.
BEGINNER_SKILLS = {
    "python", "java", "javascript", "html", "css", "sql", "excel", "git", "linux",
    "statistics", "figma", "communication", "teamwork", "problem solving", "typing",
    "networking", "oop", "object oriented programming", "data structures and algorithms",
    "digital marketing", "seo", "content writing", "photography", "typography", "canva",
    "photoshop", "illustrator", "microsoft office", "matlab", "cad", "circuit design",
}
ADVANCED_SKILLS = {
    "kubernetes", "terraform", "mlops", "distributed training", "model deployment",
    "system design", "microservices", "kafka", "spark", "transformers", "reinforcement learning",
    "penetration testing", "threat hunting", "incident response", "governance", "compliance",
    "financial modeling", "valuation", "product strategy", "programme management",
    "bioprocess engineering", "finite element analysis", "structural analysis",
    "high availability", "observability", "prompt engineering", "generative ai",
    "scientific writing", "experimental design", "data warehousing", "airflow",
}

#: Missing skill -> catalogue resource key (normalised skill names).
SKILL_RESOURCES = {
    "sql": "sql", "python": "python", "java": "java", "javascript": "javascript",
    "html": "htmlcss", "css": "htmlcss", "react": "react", "nodejs": "nodejs",
    "excel": "excel", "power bi": "powerbi", "tableau": "tableau", "statistics": "statistics",
    "machine learning": "ml", "deep learning": "deeplearning", "pytorch": "pytorch",
    "tensorflow": "tensorflow", "natural language processing": "nlp", "computer vision": "cv",
    "data analytics": "dataanalysis", "data visualization": "tableau", "data cleaning": "dataanalysis",
    "data science": "datascience", "spark": "spark", "airflow": "dataengineering",
    "etl": "dataengineering", "kafka": "dataengineering", "docker": "docker",
    "kubernetes": "kubernetes", "aws": "aws", "azure": "azure", "google cloud": "gcp",
    "linux": "linux", "networking": "networking", "cybersecurity": "cybersecurity",
    "penetration testing": "ethicalhacking", "web security": "ethicalhacking",
    "siem": "cybersecurity", "incident response": "cybersecurity", "firewalls": "networking",
    "cisco": "networking", "kali linux": "ethicalhacking", "terraform": "terraform",
    "ci cd": "devops", "monitoring": "devops", "rest api": "flask", "flask": "flask",
    "django": "django", "git": "git", "object oriented programming": "oop",
    "data structures and algorithms": "dsa", "c#": "csharp", "cpp": "cpp", "unity": "unity",
    "android": "android", "flutter": "flutter", "kotlin": "android", "swift": "mobile",
    "figma": "figma", "ui ux": "uiux", "photoshop": "digitalart", "illustration": "digitalart",
    "typography": "graphicdesign", "branding": "graphicdesign", "color theory": "graphicdesign",
    "premiere pro": "videoediting", "after effects": "videoediting", "davinci resolve": "videoediting",
    "motion graphics": "videoediting", "photography": "photography", "seo": "seo",
    "google analytics": "seo", "google ads": "digitalmarketing", "social media marketing": "digitalmarketing",
    "email marketing": "digitalmarketing", "content writing": "contentwriting",
    "digital marketing": "digitalmarketing", "financial modeling": "finance",
    "accounting": "accounting", "valuation": "finance", "recruitment": "hr",
    "human resources": "hr", "project management": "projectmgmt", "agile": "agile",
    "product strategy": "product", "user research": "uiux", "communication": "communication",
    "leadership": "leadership", "public speaking": "publicspeaking", "critical thinking": "criticalthinking",
    "problem solving": "problemsolving", "cad": "autocad", "matlab": "matlab",
    "circuit design": "electrical", "power systems": "electrical", "plc": "embedded",
    "embedded systems": "embedded", "structural analysis": "civil",
    "surveying": "civil", "molecular biology": "biotech", "bioinformatics": "biotech",
    "research methodology": "research", "scientific writing": "research",
    "teaching": "teaching", "classroom management": "teaching", "generative ai": "generativeai",
    "mlops": "devops", "terraform": "terraform", "game design": "unity", "animation": "videoediting",
    "business analysis": "excel", "business intelligence": "powerbi", "market research": "digitalmarketing",
}


@lru_cache(maxsize=1)
def load_data() -> dict:
    if not DATA_FILE.exists():
        return {"careers": [], "categories": [], "resources": {}}
    with DATA_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


def careers() -> list[dict]:
    return load_data().get("careers", [])


def categories() -> list[str]:
    return load_data().get("categories", [])


def career_by_id(career_id: str | None) -> dict | None:
    if not career_id:
        return None
    for career in careers():
        if career["id"] == career_id:
            return career
    return None


def career_by_name(name: str | None) -> dict | None:
    needle = normalise(name or "")
    if not needle:
        return None
    for career in careers():
        if normalise(career["name"]) == needle:
            return career
    return None


def career_choices() -> list[dict]:
    return [{"id": career["id"], "name": career["name"], "category": career["category"]} for career in careers()]


def normalise(term: str | None) -> str:
    """Lowercase, strip noise words, apply synonyms and singularise."""
    text = (term or "").lower().strip()
    if not text:
        return ""
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("&", " and ").replace(".js", " js ").replace("+", " plus ")
    text = re.sub(r"[^a-z0-9.#/\s-]", " ", text)
    text = re.sub(r"[\s\-_]+", " ", text).strip()
    text = re.sub(r"\b(basics?|fundamentals?|concepts?|knowledge|proficiency|expertise|advanced|intermediate)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\bskills?\b", " ", text).strip()
    if text in SYNONYMS:
        text = SYNONYMS[text]
    tokens = []
    for token in text.split():
        token = token.strip(".-_/")
        if not token:
            continue
        if len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "ics", "sis", "us", "is")):
            token = token[:-1]
        tokens.append(token)
    canonical = " ".join(tokens)
    return SYNONYMS.get(canonical, canonical)


def term_matches(required: str, user_term: str) -> bool:
    """True when a user skill/interest genuinely covers a required term."""
    required_norm = normalise(required)
    user_norm = normalise(user_term)
    if not required_norm or not user_norm:
        return False
    if required_norm == user_norm:
        return True

    required_tokens = set(required_norm.split())
    user_tokens = set(user_norm.split())
    shorter, longer = (required_tokens, user_tokens) if len(required_tokens) <= len(user_tokens) else (user_tokens, required_tokens)

    if shorter and shorter <= longer:
        if len(shorter) == 1:
            token = next(iter(shorter))
            return len(token) >= 3 and token not in GENERIC_TOKENS
        return True

    # Word-boundary containment for single-token skills ("excel" in "advanced excel").
    if len(shorter) == 1:
        token = next(iter(shorter))
        if len(token) < 3 or token in GENERIC_TOKENS:
            return False
        target = user_norm if shorter is required_tokens else required_norm
        if re.search(rf"\b{re.escape(token)}\b", target):
            return True
    return False


def matched_terms(required_terms: list[str], user_terms: list[str]) -> list[str]:
    """Return required terms covered by at least one user term (deduplicated)."""
    result: list[str] = []
    seen: set[str] = set()
    for required in required_terms:
        key = normalise(required)
        if key in seen:
            continue
        if any(term_matches(required, user) for user in user_terms):
            seen.add(key)
            result.append(required)
    return result


def _unique(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for term in terms:
        key = normalise(term)
        if key and key not in seen:
            seen.add(key)
            output.append(term)
    return output


def build_profile(raw: dict) -> dict:
    """Normalise the CareerGuide form into a profile dict."""
    skills = split_items(raw.get("skills") or raw.get("skills_text") or "", 30)
    interests = split_items(raw.get("interests") or raw.get("interests_text") or "", 30)
    return {
        "name": clean_line(raw.get("name"), 80),
        "qualification": clean_line(raw.get("qualification"), 80),
        "degree": clean_line(raw.get("degree"), 120),
        "skills": _unique(skills),
        "interests": _unique(interests),
        "preferred_domain": clean_line(raw.get("preferred_domain"), 80),
        "experience_level": clean_line(raw.get("experience_level"), 40),
    }


def score_career(career: dict, profile: dict) -> dict:
    required_skills = _unique(career.get("technical_skills", []) + career.get("soft_skills", []))
    required_interests = _unique(career.get("interests", []))
    user_skills = profile["skills"]
    user_interests = profile["interests"]

    skills_found = matched_terms(required_skills, user_skills)
    interests_found = matched_terms(required_interests, user_interests)
    missing_skills = [skill for skill in required_skills if skill not in skills_found]
    missing_interests = [interest for interest in required_interests if interest not in interests_found]

    skills_percent = round(len(skills_found) / len(required_skills) * 100, 1) if required_skills else 0.0
    interests_percent = round(len(interests_found) / len(required_interests) * 100, 1) if required_interests else 0.0
    match = round(skills_percent * SKILL_WEIGHT + interests_percent * INTEREST_WEIGHT, 1)

    if interests_percent >= 60:
        compatibility = "High"
    elif interests_percent >= 30:
        compatibility = "Moderate"
    else:
        compatibility = "Low"

    return {
        "career": career,
        "id": career["id"],
        "name": career["name"],
        "category": career["category"],
        "description": career["description"],
        "match": match,
        "skills_percent": skills_percent,
        "interests_percent": interests_percent,
        "interest_compatibility": compatibility,
        "matched_skills": skills_found,
        "missing_skills": missing_skills,
        "matched_interests": interests_found,
        "missing_interests": missing_interests,
        "required_skill_count": len(required_skills),
        "required_interest_count": len(required_interests),
    }


def recommend(profile: dict, limit: int = 5) -> dict:
    """Return the ranked career recommendations plus transparency notes."""
    scored = [score_career(career, profile) for career in careers()]
    scored.sort(key=lambda item: (-item["match"], -len(item["matched_skills"]), item["name"]))
    top = scored[:limit]
    for rank, item in enumerate(top, start=1):
        item["rank"] = rank
        item["is_best"] = rank == 1

    notes: list[str] = []
    preliminary = False
    if len(profile["skills"]) < 3:
        preliminary = True
        notes.append("Fewer than three skills were provided, so the skills match is based on very little evidence.")
    if len(profile["interests"]) < 2:
        preliminary = True
        notes.append("Fewer than two interests were provided, so the interests match is a weak signal.")
    if top and top[0]["match"] < 35:
        preliminary = True
        notes.append("No career scores above 35%; these results are preliminary. Add more specific skills and interests for a sharper match.")
    if not profile["skills"] and not profile["interests"]:
        notes.append("No skills or interests were entered, so every career scores 0%. Fill the form to get a real recommendation.")
    if profile["preferred_domain"]:
        notes.append(
            f"Your preferred domain is “{profile['preferred_domain']}”. The formula still ranks every career equally; "
            "the domain is used only to highlight relevant results below."
        )

    preferred = [item for item in scored if item["category"] == profile["preferred_domain"]][:4]
    return {
        "profile": profile,
        "results": top,
        "all_results": scored,
        "preferred_domain_matches": preferred,
        "preliminary": preliminary,
        "notes": notes,
        "method": {
            "skill_weight": SKILL_WEIGHT,
            "interest_weight": INTEREST_WEIGHT,
            "formula": "Career Match % = (Skills Match % x 0.60) + (Interests Match % x 0.40)",
            "engine": "rule-based",
        },
    }


def expected_keywords(target: str | None) -> tuple[list[str], str]:
    """Keyword list for ATS scoring, plus the career name it came from."""
    career = career_by_name(target) or career_by_id(target)
    if career:
        keywords = _unique(career["technical_skills"] + career["soft_skills"])
        return keywords, career["name"]
    # No target provided: union of the most common words across all profiles.
    return _unique([skill for career in careers()[:12] for skill in career["technical_skills"][:5]]), "General technology roles"


def infer_role(skills: list[str], interests: list[str] | None = None) -> tuple[dict | None, list[dict]]:
    """Pick the best career for a resume's skills (used when no target is chosen)."""
    profile = build_profile({"skills": ", ".join(skills), "interests": ", ".join(interests or [])})
    ranking = recommend(profile, limit=5)
    best = ranking["results"][0] if ranking["results"] and ranking["results"][0]["match"] > 0 else None
    return (career_by_id(best["id"]) if best else None), ranking["results"]


# --------------------------------------------------------------------------- #
# Learning roadmap + resources
# --------------------------------------------------------------------------- #
def _skill_tier(skill: str) -> str:
    key = normalise(skill)
    if key in {normalise(item) for item in ADVANCED_SKILLS}:
        return "advanced"
    if key in {normalise(item) for item in BEGINNER_SKILLS}:
        return "beginner"
    return "intermediate"


def resources_for_skills(skills: list[str], career: dict | None = None) -> list[dict]:
    """Map missing skills to real resources; fall back to the career's own list."""
    catalogue = load_data().get("resources", {})
    picked: list[dict] = []
    seen: set[str] = set()
    for skill in skills:
        key = SKILL_RESOURCES.get(normalise(skill))
        if key and key in catalogue and key not in seen:
            item = dict(catalogue[key])
            item["key"] = key
            item["why"] = f"Recommended to close your {skill} gap for this role."
            seen.add(key)
            picked.append(item)
    if career:
        for item in career.get("resources", []):
            if item.get("key") not in seen:
                picked.append(dict(item, why=item.get("why") or f"Core learning resource for {career['name']}."))
                seen.add(item.get("key"))
    return picked


def roadmap_for(career: dict, user_skills: list[str] | None = None) -> list[dict]:
    """Three-level personalised roadmap for a career."""
    user_skills = user_skills or []
    required = _unique(career.get("technical_skills", []) + career.get("soft_skills", []))
    missing = [skill for skill in required if not any(term_matches(skill, user) for user in user_skills)]
    levels_meta = [
        ("beginner", "Level 1 · Beginner", "Fundamentals and first working projects"),
        ("intermediate", "Level 2 · Intermediate", "Real-world application and portfolio depth"),
        ("advanced", "Level 3 · Advanced", "Specialisation and industry-level delivery"),
    ]
    levels: list[dict] = []
    buckets = {"beginner": [], "intermediate": [], "advanced": []}
    for skill in missing:
        buckets[_skill_tier(skill)].append(skill)

    catalogue = load_data().get("resources", {})
    used_urls: set[str] = set()
    for key, label, summary in levels_meta:
        topics = list(career.get("roadmap", {}).get(key, []))
        focus_skills = buckets[key]
        if focus_skills:
            topics = topics + [f"Build working ability in {skill}" for skill in focus_skills[:4]]
        projects = [project for project in career.get("projects", []) if project.get("level") == key]
        resources = []
        seen: set[str] = set()
        for skill in focus_skills:
            resource_key = SKILL_RESOURCES.get(normalise(skill))
            if resource_key and resource_key in catalogue and resource_key not in seen:
                item = dict(catalogue[resource_key])
                if item["url"] in used_urls:
                    continue
                item["key"] = resource_key
                item["why"] = f"Close your {skill} gap at this stage."
                resources.append(item)
                seen.add(resource_key)
                used_urls.add(item["url"])
                if len(resources) >= 2:
                    break
        levels.append(
            {
                "key": key,
                "label": label,
                "summary": summary,
                "topics": topics,
                "focus_skills": focus_skills,
                "projects": projects,
                "resources": resources,
            }
        )

    # Every level keeps at least one real resource, even when the student already
    # has all required skills or the career has no advanced-level link.
    for level in levels:
        if level["resources"]:
            continue
        pool = [item for item in career.get("resources", []) if item["url"] not in used_urls]
        preferred = [item for item in pool if (item.get("level") or "").lower() == level["key"]]
        for item in (preferred or pool or career.get("resources", []))[:1]:
            level["resources"].append(dict(item))
            used_urls.add(item["url"])
    return levels


def career_detail(career_id: str, profile: dict) -> dict | None:
    career = career_by_id(career_id)
    if not career:
        return None
    scored = score_career(career, profile)
    return {
        "career": career,
        "match": scored,
        "roadmap": roadmap_for(career, profile.get("skills", [])),
        "resources": resources_for_skills(scored["missing_skills"], career),
        "existing_skills": scored["matched_skills"],
        "skills_to_learn": scored["missing_skills"],
        "interests_matched": scored["matched_interests"],
    }
