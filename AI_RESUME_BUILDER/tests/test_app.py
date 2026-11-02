"""End-to-end verification for the resume + career application (Flask test client)."""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

from PIL import Image
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from docx import Document

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from app import app  # noqa: E402
from services import career_service  # noqa: E402
PASS, FAIL = [], []


def check(label, condition, detail=""):
    (PASS if condition else FAIL).append(label)
    print(("PASS " if condition else "FAIL ") + label + (f" :: {detail}" if detail and not condition else ""))


def make_jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (600, 600), (70, 82, 190)).save(buffer, "JPEG")
    buffer.seek(0)
    return buffer.getvalue()


def pdf_text(blob: bytes) -> str:
    reader = PdfReader(io.BytesIO(blob))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def session_resume_id(client):
    with client.session_transaction() as sess:
        return sess.get("resume_id")


def resume_form(resume: dict) -> dict:
    """Convert stored resume JSON back into builder form fields."""
    data = {
        "resume_id": resume["id"],
        "full_name": resume["personal"]["full_name"],
        "email": resume["personal"]["email"],
        "phone": resume["personal"]["phone"],
        "location": resume["personal"]["location"],
        "linkedin": resume["personal"]["linkedin"],
        "github": resume["personal"]["github"],
        "portfolio": resume["personal"]["portfolio"],
        "target_role": resume.get("target_role", ""),
        "objective": resume.get("objective", ""),
        "template": resume.get("template", "modern"),
        "skills_technical": ", ".join(resume["skills"]["technical"]),
        "skills_soft": ", ".join(resume["skills"]["soft"]),
        "experience_status": resume.get("experience_status", "has"),
        "max_upload_bytes": "8388608",
        "max_photo_bytes": "4194304",
        "edu_institution": [e.get("institution", "") for e in resume["education"]],
        "edu_degree": [e.get("degree", "") for e in resume["education"]],
        "edu_department": [e.get("department", "") for e in resume["education"]],
        "edu_start_year": [e.get("start_year", "") for e in resume["education"]],
        "edu_grad_year": [e.get("grad_year", "") for e in resume["education"]],
        "edu_score": [e.get("score", "") for e in resume["education"]],
        "project_title": [p.get("title", "") for p in resume["projects"]],
        "project_description": [p.get("description", "") for p in resume["projects"]],
        "project_technologies": [p.get("technologies", "") for p in resume["projects"]],
        "project_url": [p.get("url", "") for p in resume["projects"]],
        "cert_name": [c.get("name", "") for c in resume["certifications"]],
        "cert_org": [c.get("organization", "") for c in resume["certifications"]],
        "cert_date": [c.get("issue_date", "") for c in resume["certifications"]],
        "cert_id": [c.get("credential_id", "") for c in resume["certifications"]],
        "cert_url": [c.get("url", "") for c in resume["certifications"]],
        "exp_company": [j.get("company", "") for j in resume["experience"]],
        "exp_title": [j.get("title", "") for j in resume["experience"]],
        "exp_duration": [j.get("duration", "") for j in resume["experience"]],
        "exp_responsibilities": [j.get("responsibilities", "") for j in resume["experience"]],
        "exp_achievements": [j.get("achievements", "") for j in resume["experience"]],
    }
    return data


def main() -> int:
    app.config.update(TESTING=True)
    client = app.test_client()

    # ---------------------------------------------------------------- builder
    form = {
        "full_name": "Aarav Sharma",
        "email": "aarav.sharma@example.com",
        "phone": "+91 98765 43210",
        "location": "Bengaluru, Karnataka, India",
        "linkedin": "linkedin.com/in/aarav-sharma",
        "github": "github.com/aarav-dev",
        "portfolio": "",
        "target_role": "Data Analyst",
        "objective": "Final-year B.Tech student in Artificial Intelligence and Data Science with practical exposure to Python, SQL and Power BI. Seeking a Data Analyst role where I can turn raw data into clear, decision-ready insight while deepening my statistics and dashboarding skills.",
        "edu_institution": ["ABC Institute of Technology", "XYZ Public School"],
        "edu_degree": ["B.Tech", "12th (CBSE)"],
        "edu_department": ["Artificial Intelligence & Data Science", "Science"],
        "edu_start_year": ["2022", "2020"],
        "edu_grad_year": ["2026", "2022"],
        "edu_score": ["8.6 CGPA", "88%"],
        "skills_technical": "Python, SQL, Power BI, Excel, Statistics, Machine Learning, Data Visualization, Pandas, NumPy, Tableau",
        "skills_soft": "Communication, Problem Solving, Attention to Detail",
        "project_title": ["Sales performance dashboard", "Customer churn analysis", "Automated reporting pipeline"],
        "project_description": [
            "Built an interactive Power BI dashboard over a 200k-row sales dataset, showing regional revenue trends and product gaps. Automated the weekly refresh with SQL views and documented the data model.",
            "Analysed churn drivers using SQL and pandas across 12 monthly cohorts. Presented three retention recommendations that the project mentor adopted for the cohort study.",
            "Scheduled a Python job that validates incoming CSV data, refreshes a summary table and emails a PDF report. Added anomaly checks and failure alerts so silent data issues are caught early.",
        ],
        "project_technologies": ["Power BI, SQL, Excel", "Python, pandas, SQL", "Python, Flask, SQLite, cron"],
        "project_url": ["https://github.com/aarav-dev/sales-dashboard", "https://github.com/aarav-dev/churn-analysis", ""],
        "cert_name": ["Google Data Analytics Professional Certificate", "Microsoft Power BI Data Analyst Associate"],
        "cert_org": ["Google / Coursera", "Microsoft"],
        "cert_date": ["Jun 2025", "2025-03"],
        "cert_id": ["GDA-998877", "PL300-4455"],
        "cert_url": ["https://coursera.org/verify/example", ""],
        "exp_company": ["Acme Analytics"],
        "exp_title": ["Data Analyst Intern"],
        "exp_duration": ["Jun 2025 – Aug 2025"],
        "exp_responsibilities": "Cleaned and reconciled three marketing datasets in SQL.\nBuilt weekly Excel reports for the growth team.",
        "exp_achievements": "Reduced manual reporting time by 6 hours per week through a Python automation script.",
        "experience_status": "has",
        "template": "modern",
        "max_upload_bytes": str(8 * 1024 * 1024),
        "max_photo_bytes": str(4 * 1024 * 1024),
    }
    response = client.post(
        "/resume/generate",
        data={**form, "photo": (io.BytesIO(make_jpeg()), "profile.jpg")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)
    check("generate resume returns preview", response.status_code == 200 and "resume-sheet" in body, f"status {response.status_code}")
    check("preview shows name", "Aarav Sharma" in body)
    check("preview shows target role", "Data Analyst" in body)
    check("preview shows education", "ABC Institute of Technology" in body)
    check("preview shows certifications", "Google Data Analytics Professional Certificate" in body)
    check("preview shows experience", "Acme Analytics" in body)
    rid = session_resume_id(client)
    check("resume id stored in session", bool(rid), str(rid))

    stored = json.loads((BASE / "data" / "resumes" / f"{rid}.json").read_text())
    check("photo stored and resized", bool(stored["personal"]["photo"]), stored["personal"].get("photo", ""))
    photo = client.get(f"/resume/photo/{rid}")
    check("profile photo endpoint serves image", photo.status_code == 200 and photo.data[:2] == b"\xff\xd8")
    check("photo size under 4 MB", len(photo.data) < 4 * 1024 * 1024, str(len(photo.data)))

    # ---------------------------------------------------------------- PDF
    pdf = client.get("/resume/download")
    check("PDF download returns PDF", pdf.status_code == 200 and pdf.data[:4] == b"%PDF", str(pdf.data[:8]))
    text = pdf_text(pdf.data)
    for token in ["Aarav Sharma", "CAREER OBJECTIVE", "EDUCATION", "SKILLS", "PROJECTS", "CERTIFICATIONS", "EXPERIENCE", "Acme Analytics"]:
        check(f"PDF contains {token}", token.lower() in text.lower())
    check("PDF has no template artifacts", "None" not in text and "{{" not in text)
    check("PDF is at least one page", len(PdfReader(io.BytesIO(pdf.data)).pages) >= 1)

    # ---------------------------------------------------------------- template switching
    switched = client.post("/resume/template", data={"template": "classic"}, follow_redirects=True)
    body = switched.get_data(as_text=True)
    check("template switch works", "tpl-classic" in body)
    client.post("/resume/template", data={"template": "minimal"}, follow_redirects=True)
    body = client.get("/resume/preview").get_data(as_text=True)
    check("minimal template renders", "tpl-minimal" in body)
    invalid_template = client.post("/resume/template", data={"template": "bogus"}, follow_redirects=True)
    check("invalid template rejected", "not available" in invalid_template.get_data(as_text=True))

    # ---------------------------------------------------------------- ATS stored
    ats = client.post("/ats/analyze", data={"source": "stored", "target_role": "Data Analyst"})
    body = ats.get_data(as_text=True)
    score_match = re.search(r'class="gauge-inner"><strong>(\d+)</strong>', body)
    strong_score = int(score_match.group(1)) if score_match else -1
    check("ATS analysis renders", ats.status_code == 200 and "Score breakdown" in body)
    check("ATS score in 0-100", 0 <= strong_score <= 100, str(strong_score))
    check("ATS lists categories", all(label in body for label in ["Contact Information", "Career Objective", "Projects", "Keywords", "Readability"]))
    check("ATS declares estimate", "estimated" in body.lower())
    check("ATS shows deductions or checks", "checks" in body)
    check("ATS keyword target named", "Data Analyst" in body)

    # A deliberately weak resume must score lower.
    weak_form = {
        "full_name": "Weak Candidate",
        "email": "weak@example.com",
        "skills_technical": "Python",
        "edu_institution": [""],
        "experience_status": "skip",
        "template": "modern",
    }
    weak = client.post("/resume/generate", data=weak_form, follow_redirects=False)
    weak_ok = weak.status_code in (400, 302)
    check("weak resume handled (validation or saved)", weak_ok, str(weak.status_code))
    weak_id = session_resume_id(client)
    weak_ats = client.post("/ats/analyze", data={"source": "stored", "target_role": "Data Analyst"})
    weak_match = re.search(r'class="gauge-inner"><strong>(\d+)</strong>', weak_ats.get_data(as_text=True))
    weak_score = int(weak_match.group(1)) if weak_match else 100
    check("score changes with resume quality", weak_score < strong_score, f"{weak_score} < {strong_score}")

    # Restore the strong resume for the remaining tests.
    client.post("/resume/generate", data=resume_form(stored), content_type="multipart/form-data", follow_redirects=True)

    # ---------------------------------------------------------------- upload & edit (PDF)
    upload = client.post(
        "/resume/upload",
        data={"resume_file": (io.BytesIO(pdf.data), "old_resume.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    body = upload.get_data(as_text=True)
    check("PDF upload accepted", upload.status_code == 200 and "Uploaded resume detected" in body)
    check("PDF text extraction fills name", 'value="Aarav Sharma"' in body)
    check("PDF extraction fills email", "aarav.sharma@example.com" in body)
    check("PDF extraction fills skills", "Python" in body and "Power BI" in body)
    extracted_id = session_resume_id(client)
    extracted = json.loads((BASE / "data" / "resumes" / f"{extracted_id}.json").read_text())
    check("original upload preserved", bool(extracted.get("original_file", {}).get("path")), str(extracted.get("original_file")))
    check(
        "email domain not captured as a portfolio URL",
        extracted["personal"]["portfolio"] == "",
        str(extracted["personal"]["portfolio"]),
    )
    original = client.get(f"/resume/original/{extracted_id}")
    check("original resume downloadable", original.status_code == 200 and original.data[:4] == b"%PDF")
    check("extracted education detected", len(extracted["education"]) >= 1, str(extracted["education"]))
    check("extracted projects detected", len(extracted["projects"]) >= 1, str(len(extracted["projects"])))

    # Add a certification to the extracted resume and regenerate.
    edited_form = resume_form(extracted)
    edited_form["cert_name"] = edited_form["cert_name"] + ["AWS Certified Cloud Practitioner"]
    edited_form["cert_org"] = edited_form["cert_org"] + ["Amazon Web Services"]
    edited_form["cert_date"] = edited_form["cert_date"] + ["2026-01"]
    edited_form["skills_technical"] = edited_form["skills_technical"] + ", AWS"
    regenerated = client.post("/resume/generate", data=edited_form, content_type="multipart/form-data", follow_redirects=True)
    body = regenerated.get_data(as_text=True)
    check("updated resume generates", regenerated.status_code == 200 and "AWS Certified Cloud Practitioner" in body)
    check("existing information preserved after update", "ABC Institute of Technology" in body and "Aarav Sharma" in body)
    updated = json.loads((BASE / "data" / "resumes" / f"{session_resume_id(client)}.json").read_text())
    check("original file preserved after update", bool(updated.get("original_file", {}).get("path")))

    # ---------------------------------------------------------------- DOCX upload
    doc = Document()
    for line in [
        "PRIYA MENON",
        "priya.menon@example.com | +91 90000 11111 | Kochi, India",
        "linkedin.com/in/priyamenon | github.com/priyamenon",
        "CAREER OBJECTIVE",
        "Recent B.Tech graduate in Computer Science seeking a backend developer role with Python and SQL.",
        "EDUCATION",
        "Cochin University of Science and Technology",
        "B.Tech in Computer Science",
        "2019 - 2023",
        "8.2 CGPA",
        "SKILLS",
        "Python, Java, SQL, Flask, Docker, Git, Communication, Teamwork",
        "PROJECTS",
        "Campus Resource API",
        "Built a Flask REST API for campus resources with authentication and tests.",
        "Technologies: Python, Flask, SQLite",
        "CERTIFICATIONS",
        "AWS Cloud Practitioner - Amazon Web Services - 2024",
        "EXPERIENCE",
        "Backend Developer Intern at Kochi Tech Labs | Jan 2023 - Jun 2023",
        "Implemented API endpoints for a logistics dashboard.",
    ]:
        doc.add_paragraph(line)
    docx_buffer = io.BytesIO()
    doc.save(docx_buffer)
    docx_buffer.seek(0)
    docx_upload = client.post(
        "/resume/upload",
        data={"resume_file": (docx_buffer, "priya_resume.docx")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    body = docx_upload.get_data(as_text=True)
    check("DOCX upload accepted", docx_upload.status_code == 200 and "Uploaded resume detected" in body)
    check("DOCX name extracted", "Priya Menon" in body or "PRIYA MENON" in body)
    docx_resume = json.loads((BASE / "data" / "resumes" / f"{session_resume_id(client)}.json").read_text())
    check("DOCX skills extracted", len(docx_resume["skills"]["technical"]) >= 3, str(docx_resume["skills"]))
    check("DOCX education extracted", bool(docx_resume["education"]), str(docx_resume["education"]))
    check("DOCX experience extracted", bool(docx_resume["experience"]), str(docx_resume["experience"]))
    check("DOCX certifications extracted", bool(docx_resume["certifications"]), str(docx_resume["certifications"]))

    # ---------------------------------------------------------------- scanned PDF
    blank = io.BytesIO()
    c = canvas.Canvas(blank)
    c.rect(50, 50, 400, 700, fill=1)
    c.showPage()
    c.save()
    blank.seek(0)
    scanned = client.post(
        "/resume/upload",
        data={"resume_file": (blank, "scanned.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    body = scanned.get_data(as_text=True)
    check("scanned PDF handled gracefully", scanned.status_code == 200 and "OCR is not available" in body)

    # ---------------------------------------------------------------- ATS uploaded
    upload_pdf = io.BytesIO(pdf.data)
    ats_upload = client.post(
        "/ats/analyze",
        data={"source": "upload", "resume_file": (upload_pdf, "analyse.pdf"), "target_role": "Data Analyst"},
        content_type="multipart/form-data",
    )
    body = ats_upload.get_data(as_text=True)
    check("ATS upload analysis works", ats_upload.status_code == 200 and "Analysed from extracted text" in body)
    uploaded_match = re.search(r'class="gauge-inner"><strong>(\d+)</strong>', body)
    check("uploaded ATS score present", bool(uploaded_match), body[:200])
    check("ATS upload cleaned up", not list((BASE / "data" / "uploads").glob("ats_*")))

    # ---------------------------------------------------------------- objective API (fallback)
    objective = client.post("/api/objective", json={"mode": "generate", "name": "Aarav", "degree": "B.Tech", "department": "AI & DS", "skills": "Python, SQL, Power BI", "soft_skills": "Communication", "target_role": "Data Analyst", "experience_status": "fresher"})
    payload = objective.get_json()
    check("objective API responds", objective.status_code == 200 and bool(payload.get("text")), str(payload)[:200])
    check("objective provenance labelled", payload.get("source") in {"ai", "rule-based"}, str(payload.get("source")))
    check("objective is editable text", 20 <= len(payload.get("text", "").split()) <= 90, str(len(payload.get("text", "").split())))

    # ---------------------------------------------------------------- CareerGuide
    career_form = {
        "name": "Ananya Rao",
        "qualification": "Undergraduate student",
        "degree": "B.Tech, Artificial Intelligence & Data Science",
        "skills": "Python, SQL, Machine Learning, Data Analysis, Excel, Communication",
        "interests": "Data Analysis, Machine Learning, Statistics, Dashboards",
        "preferred_domain": "Artificial Intelligence & Data Science",
        "experience_level": "Student / fresher",
    }
    career = client.post("/career-recommendation", data=career_form, follow_redirects=True)
    body = career.get_data(as_text=True)
    check("career recommendation renders", career.status_code == 200 and "Top 5 career recommendations" in body)
    check("career profile shown", "Ananya Rao" in body)
    check("best match highlighted", "Best match" in body)
    with client.session_transaction() as sess:
        stored_profile = sess.get("career_profile")
    ranking = career_service.recommend(career_service.build_profile(stored_profile), limit=5)
    scores = [item["match"] for item in ranking["results"]]
    check("five recommendations returned", len(ranking["results"]) == 5, str(len(ranking["results"])))
    check("recommendations sorted descending", scores == sorted(scores, reverse=True), str(scores))
    check("no fabricated 100% match", max(scores) < 100, str(scores))
    best = ranking["results"][0]
    check("formula consistency", abs(best["match"] - round(best["skills_percent"] * 0.6 + best["interests_percent"] * 0.4, 1)) < 0.11, str(best["match"]))
    check("data-analyst ranks for data profile", "Data Analyst" in [item["name"] for item in ranking["results"]], str([item["name"] for item in ranking["results"]]))
    check("detail link present", f"/career/detail/{best['id']}" in body)

    detail = client.get(f"/career/detail/{best['id']}")
    detail_body = detail.get_data(as_text=True)
    check("career detail renders", detail.status_code == 200 and best["name"] in detail_body)
    check("detail has roadmap", "Beginner" in detail_body and "Advanced" in detail_body)
    check("detail has clickable resources", 'target="_blank"' in detail_body and "rel=\"noopener noreferrer\"" in detail_body)
    check("detail has responsibilities", "Typical responsibilities" in detail_body)
    check("detail has growth", "Career growth opportunities" in detail_body)
    check(
        "all three roadmap levels have labelled resources",
        detail_body.count('class="level-resources"') == 3 and 'class="res-cost"' in detail_body,
    )

    resources = ranking["results"][0]["career"]["resources"]
    check("career dataset has resources", len(resources) >= 4, str(len(resources)))
    check("all resource URLs are https", all(str(item["url"]).startswith("https://") for item in resources))

    # Incomplete profile must be flagged preliminary, not inflated.
    thin = client.post("/career-recommendation", data={"name": "Test", "qualification": "Undergraduate student", "degree": "B.Sc", "skills": "Painting", "interests": "Art"}, follow_redirects=True)
    thin_body = thin.get_data(as_text=True)
    check("thin profile flagged preliminary", "preliminary" in thin_body.lower())

    # Validation errors
    invalid = client.post("/career-recommendation", data={"name": "", "qualification": "", "degree": "", "skills": "", "interests": ""})
    check("career form validation", invalid.status_code == 400 and "Please enter your name" in invalid.get_data(as_text=True))

    # GET result page re-renders from session
    get_result = client.get("/career-recommendation")
    check("GET career result works", get_result.status_code == 200)

    # ---------------------------------------------------------------- security / misc
    other = app.test_client()
    check("photo protected from other session", other.get(f"/resume/photo/{rid}").status_code == 404)
    check("unknown resume 404", client.get("/resume/photo/deadbeef").status_code == 404)
    check("health endpoint", client.get("/health").status_code == 200)

    print("\n===== RESULT =====")
    print(f"passed={len(PASS)} failed={len(FAIL)}")
    for item in FAIL:
        print("FAILED:", item)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
