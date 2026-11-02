"""AI Resume Builder and Career Recommendation System.

A single Flask application hosting two modules:
  * AI Resume Builder — create, upload/edit, preview, PDF export and ATS analysis
  * CareerGuide       — rule-based career matching, roadmaps and learning resources

Run locally with:  python app.py
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.exceptions import RequestEntityTooLarge

load_dotenv()

from services import ai_service, ats_service, career_service, extract_service, pdf_service, resume_service  # noqa: E402
from utils.helpers import (  # noqa: E402
    RESUME_EXTENSIONS,
    clean_line,
    new_id,
    save_document_upload,
)

BASE_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "8") or 8)
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_PHOTO_BYTES = 4 * 1024 * 1024

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32),
    MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES + 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "0") == "1",
    TEMPLATES_AUTO_RELOAD=os.getenv("FLASK_ENV") != "production",
    JSON_SORT_KEYS=False,
)

resume_service.ensure_dirs()


# --------------------------------------------------------------------------- #
# Shared template context
# --------------------------------------------------------------------------- #
@app.context_processor
def inject_globals() -> dict:
    return {
        "site_name": "AI Resume Builder & Career Recommendation",
        "app_year": 2026,
        "ai_status": ai_service.ai_status(),
        "templates_catalog": resume_service.TEMPLATES,
        "career_categories": career_service.categories(),
        "saved_resume_id": session.get("resume_id"),
        "max_upload_mb": MAX_UPLOAD_MB,
    }


@app.template_filter("pretty")
def pretty_filter(value: str) -> str:
    from utils.helpers import pretty_date

    return pretty_date(value)


@app.template_filter("initials")
def initials_filter(value: str) -> str:
    parts = [part for part in (value or "").split() if part]
    return "".join(part[0].upper() for part in parts[:2]) or "CV"


def current_resume() -> dict | None:
    return resume_service.get_resume(session.get("resume_id"))


def _owned_resume(resume_id: str) -> dict:
    """Fetch a resume that belongs to this browser session, or 404."""
    if session.get("resume_id") != resume_id:
        abort(404)
    resume = resume_service.get_resume(resume_id)
    if not resume:
        abort(404)
    return resume


def _safe_next(target: str | None, fallback: str) -> str:
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return fallback


# --------------------------------------------------------------------------- #
# Unified homepage
# --------------------------------------------------------------------------- #
@app.route("/")
def home():
    top_careers = career_service.career_choices()[:6]
    return render_template(
        "index.html",
        saved_resume=current_resume(),
        top_careers=top_careers,
        career_count=len(career_service.careers()),
    )


# --------------------------------------------------------------------------- #
# Resume module
# --------------------------------------------------------------------------- #
@app.route("/resume")
def resume_entry():
    return render_template("resume/entry.html", saved_resume=current_resume())


@app.route("/resume/new")
def resume_new():
    resume = resume_service.blank_resume()
    resume["id"] = new_id()
    session["resume_id"] = None
    return render_template(
        "resume/builder.html",
        resume=resume,
        errors=[],
        warnings=[],
        mode="create",
        career_choices=career_service.career_choices(),
    )


@app.route("/resume/edit")
def resume_edit():
    resume = current_resume()
    if not resume:
        flash("Start a resume first, then you can edit it.", "info")
        return redirect(url_for("resume_entry"))
    return render_template(
        "resume/builder.html",
        resume=resume,
        errors=[],
        warnings=(resume.get("extraction") or {}).get("warnings", []) if resume.get("extraction") else [],
        mode="edit",
        career_choices=career_service.career_choices(),
    )


@app.route("/generate", methods=["GET", "POST"])
def generate():
    """Legacy route kept for the existing project. Alias of the builder flow."""
    if request.method == "GET":
        return redirect(url_for("resume_new"))
    return resume_generate()


@app.route("/resume/generate", methods=["POST"])
def resume_generate():
    existing = current_resume()
    if request.form.get("resume_id") and existing and request.form.get("resume_id") != existing["id"]:
        existing = None

    resume, errors, warnings = resume_service.parse_form(request.form, request.files, existing)
    resume["template"] = request.form.get("template") or (existing or {}).get("template") or resume_service.DEFAULT_TEMPLATE
    if resume.get("extraction") is None and existing:
        resume["extraction"] = existing.get("extraction")
    if existing and existing.get("original_file"):
        resume["original_file"] = existing["original_file"]
        resume["source"] = existing.get("source", resume["source"])
    if existing:
        resume["created_at"] = existing.get("created_at", resume["created_at"])

    resume = resume_service.save_resume(resume)
    session["resume_id"] = resume["id"]

    if errors:
        for error in errors:
            flash(error, "error")
        return render_template(
            "resume/builder.html",
            resume=resume,
            errors=errors,
            warnings=warnings,
            mode="edit",
            career_choices=career_service.career_choices(),
        ), 400

    for warning in warnings:
        flash(warning, "warning")
    flash("Resume generated. Review the preview, switch templates, or download the PDF.", "success")
    return redirect(url_for("resume_preview"))


@app.route("/resume/upload", methods=["POST"])
def resume_upload():
    upload = request.files.get("resume_file")
    if not upload or not upload.filename:
        flash("Choose a PDF or DOCX file to upload.", "error")
        return redirect(url_for("resume_entry"))

    resume_id = new_id()
    folder = resume_service.upload_dir(resume_id)
    stored, error = save_document_upload(upload, folder, RESUME_EXTENSIONS, MAX_UPLOAD_BYTES, prefix="original")
    if error:
        flash(error, "error")
        return redirect(url_for("resume_entry"))

    path = folder / stored
    extracted = extract_service.extract_document(path)

    resume = resume_service.blank_resume(source="uploaded")
    resume["id"] = resume_id
    resume["original_file"] = {"name": clean_line(upload.filename, 160), "path": f"{resume_id}/{stored}"}
    parsed = extracted["parsed"]
    resume = resume_service.merge_extracted(resume, parsed)
    resume["extraction"] = {
        "warnings": extracted["warnings"],
        "scanned": extracted["scanned"],
        "confidence": parsed["confidence"],
        "meta": extracted["meta"],
        "preview_text": extracted["text"][:4000],
    }
    resume = resume_service.save_resume(resume)
    session["resume_id"] = resume["id"]

    flash("We extracted the text and filled the form as far as possible. Check every field, then generate the updated resume.", "success")
    if extracted["scanned"]:
        flash(
            "OCR is not available, so a scanned PDF could not be read. The original file is preserved — please type the details manually.",
            "warning",
        )
    return redirect(url_for("resume_edit"))


@app.route("/resume/preview")
def resume_preview():
    resume = current_resume()
    if not resume:
        flash("Create or upload a resume to preview it.", "info")
        return redirect(url_for("resume_entry"))
    return render_template("resume/preview.html", resume=resume)


@app.route("/resume/template", methods=["POST"])
def resume_template():
    resume = current_resume()
    if not resume:
        return redirect(url_for("resume_entry"))
    template_id = clean_line(request.form.get("template"), 30)
    if template_id not in resume_service.TEMPLATE_IDS:
        flash("That template is not available.", "error")
    else:
        resume["template"] = template_id
        resume = resume_service.save_resume(resume)
        flash(f"Template changed to {resume_service.template_by_id(template_id)['name']}.", "success")
    return redirect(_safe_next(request.form.get("next"), url_for("resume_preview")))


@app.route("/resume/download")
def resume_download():
    resume = current_resume()
    if not resume:
        flash("Create a resume first.", "info")
        return redirect(url_for("resume_entry"))
    try:
        pdf_bytes = pdf_service.build_pdf(resume)
    except Exception as exc:  # never show a stack trace to the user
        app.logger.exception("PDF generation failed")
        flash(f"The PDF could not be generated ({exc.__class__.__name__}). Please try again.", "error")
        return redirect(url_for("resume_preview"))
    from io import BytesIO

    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=pdf_service.pdf_filename(resume),
        max_age=0,
    )


@app.route("/resume/photo/<resume_id>")
def resume_photo(resume_id: str):
    resume = _owned_resume(resume_id)
    path = resume_service.stored_path(resume["personal"].get("photo"))
    if not path:
        abort(404)
    return send_file(path, mimetype="image/jpeg", max_age=0)


@app.route("/resume/original/<resume_id>")
def resume_original(resume_id: str):
    resume = _owned_resume(resume_id)
    original = resume.get("original_file") or {}
    path = resume_service.stored_path(original.get("path"))
    if not path:
        abort(404)
    return send_file(path, as_attachment=True, download_name=original.get("name") or path.name, max_age=0)


@app.route("/resume/certificate/<resume_id>/<int:index>")
def resume_certificate(resume_id: str, index: int):
    resume = _owned_resume(resume_id)
    certifications = resume.get("certifications", [])
    if index < 0 or index >= len(certifications):
        abort(404)
    path = resume_service.stored_path(certifications[index].get("attachment_path"))
    if not path:
        abort(404)
    return send_file(path, as_attachment=True, download_name=certifications[index].get("attachment") or path.name, max_age=0)


@app.route("/resume/delete", methods=["POST"])
def resume_delete():
    resume = current_resume()
    if resume:
        resume_service.delete_resume_files(resume["id"])
        try:
            (resume_service.RESUMES_DIR / f"{resume['id']}.json").unlink(missing_ok=True)
        except OSError:
            pass
        session.pop("resume_id", None)
        flash("The saved resume and its uploaded files were deleted from this machine.", "success")
    return redirect(url_for("resume_entry"))


@app.route("/api/objective", methods=["POST"])
def api_objective():
    """AI-assisted objective with an honest rule-based fallback."""
    payload = request.get_json(silent=True) or {}
    profile = {
        "name": payload.get("name"),
        "qualification": payload.get("qualification"),
        "degree": payload.get("degree"),
        "department": payload.get("department"),
        "skills": payload.get("skills"),
        "soft_skills": payload.get("soft_skills"),
        "interests": payload.get("interests"),
        "target_role": payload.get("target_role"),
        "experience_status": payload.get("experience_status"),
    }
    mode = payload.get("mode")
    if mode == "improve":
        result = ai_service.polish_objective(payload.get("text") or "", profile)
    else:
        result = ai_service.generate_objective(profile)
    return jsonify(result)


# --------------------------------------------------------------------------- #
# ATS module
# --------------------------------------------------------------------------- #
@app.route("/ats")
def ats_page():
    resume = current_resume()
    return render_template(
        "resume/ats.html",
        resume=resume,
        analysis=None,
        target_role=(resume or {}).get("target_role", ""),
        career_choices=career_service.career_choices(),
    )


@app.route("/resume/ats")
def ats_alias():
    return redirect(url_for("ats_page"))


@app.route("/ats/analyze", methods=["POST"])
def ats_analyze():
    resume = current_resume()
    source = request.form.get("source", "stored")
    target_role = clean_line(request.form.get("target_role"), 90)
    analysis = None
    uploaded_name = ""

    upload = request.files.get("resume_file")
    if source == "upload" or (upload and upload.filename):
        if not upload or not upload.filename:
            flash("Choose a PDF or DOCX file, or analyze your saved resume instead.", "error")
            return redirect(url_for("ats_page"))
        from utils.helpers import is_allowed

        if not is_allowed(upload.filename, RESUME_EXTENSIONS):
            flash("Unsupported file type. Upload a PDF or DOCX resume.", "error")
            return redirect(url_for("ats_page"))
        temp_id = new_id()
        folder = resume_service.upload_dir(f"ats_{temp_id}")
        stored, error = save_document_upload(upload, folder, RESUME_EXTENSIONS, MAX_UPLOAD_BYTES, prefix="ats")
        if error:
            flash(error, "error")
            return redirect(url_for("ats_page"))
        try:
            analysis = ats_service.analyse_upload(folder / stored, original_name=upload.filename, target_role=target_role)
            uploaded_name = clean_line(upload.filename, 160)
        finally:
            # Uploaded ATS files are analysed in memory and then removed.
            resume_service.delete_resume_files(f"ats_{temp_id}")
        if not analysis:
            flash("That file could not be analysed.", "error")
            return redirect(url_for("ats_page"))
    else:
        if not resume:
            flash("Create a resume first, or upload an existing resume for analysis.", "error")
            return redirect(url_for("ats_page"))
        analysis = ats_service.analyze(resume, target_role=target_role or resume.get("target_role"))

    return render_template(
        "resume/ats.html",
        resume=resume,
        analysis=analysis,
        target_role=analysis.get("keyword_info", {}).get("target_role", target_role),
        career_choices=career_service.career_choices(),
        uploaded_name=uploaded_name,
    )


# --------------------------------------------------------------------------- #
# CareerGuide module
# --------------------------------------------------------------------------- #
def _career_groups() -> list[dict]:
    """Group every career profile by category for the CareerGuide library."""
    grouped: dict[str, list[dict]] = {category: [] for category in career_service.categories()}
    for career in career_service.careers():
        grouped.setdefault(career["category"], []).append({"id": career["id"], "name": career["name"]})
    return [{"category": category, "careers": items} for category, items in grouped.items() if items]


@app.route("/career")
def career_home():
    profile = session.get("career_profile") or {}
    return render_template(
        "career/home.html",
        profile=profile,
        categories=career_service.categories(),
        sample_careers=career_service.career_choices()[:8],
        career_groups=_career_groups(),
        career_count=len(career_service.careers()),
    )


@app.route("/career-recommendation", methods=["GET", "POST"])
def career_recommendation():
    if request.method == "GET":
        profile = session.get("career_profile")
        if not profile:
            flash("Tell us about yourself to see career recommendations.", "info")
            return redirect(url_for("career_home"))
        profile = career_service.build_profile(profile)
        return _render_career_results(profile)

    raw = {
        "name": request.form.get("name"),
        "qualification": request.form.get("qualification"),
        "degree": request.form.get("degree"),
        "skills": request.form.get("skills"),
        "interests": request.form.get("interests"),
        "preferred_domain": request.form.get("preferred_domain"),
        "experience_level": request.form.get("experience_level"),
    }
    profile = career_service.build_profile(raw)
    errors: list[str] = []
    if not profile["name"]:
        errors.append("Please enter your name.")
    if not profile["qualification"]:
        errors.append("Select your educational qualification.")
    if not profile["degree"]:
        errors.append("Enter your degree or department.")
    if not profile["skills"]:
        errors.append("Add at least one skill.")
    if not profile["interests"]:
        errors.append("Add at least one interest.")

    if errors:
        for error in errors:
            flash(error, "error")
        return render_template(
            "career/home.html",
            profile={**profile, "skills_text": ", ".join(profile["skills"]), "interests_text": ", ".join(profile["interests"])},
            categories=career_service.categories(),
            sample_careers=career_service.career_choices()[:8],
            career_groups=_career_groups(),
            career_count=len(career_service.careers()),
            errors=errors,
        ), 400

    session["career_profile"] = profile
    return _render_career_results(profile)


def _render_career_results(profile: dict):
    ranking = career_service.recommend(profile, limit=5)
    best = ranking["results"][0] if ranking["results"] else None
    best_detail = career_service.career_detail(best["id"], profile) if best else None
    return render_template(
        "career/results.html",
        profile=profile,
        ranking=ranking,
        results=ranking["results"],
        best=best,
        best_detail=best_detail,
        notes=ranking["notes"],
        preliminary=ranking["preliminary"],
        preferred_matches=ranking.get("preferred_domain_matches") or [],
        categories=career_service.categories(),
    )


@app.route("/career/detail/<career_id>")
def career_detail(career_id: str):
    profile_raw = session.get("career_profile")
    if not profile_raw:
        flash("Fill the career guidance form to see this career in context.", "info")
        return redirect(url_for("career_home"))
    profile = career_service.build_profile(profile_raw)
    detail = career_service.career_detail(career_id, profile)
    if not detail:
        abort(404)
    ranking = career_service.recommend(profile, limit=5)
    others = [item for item in ranking["results"] if item["id"] != career_id]
    return render_template(
        "career/detail.html",
        profile=profile,
        career=detail["career"],
        match=detail["match"],
        roadmap=detail["roadmap"],
        resources=detail["resources"],
        existing_skills=detail["existing_skills"],
        skills_to_learn=detail["skills_to_learn"],
        others=others,
        categories=career_service.categories(),
    )


@app.route("/career/reset", methods=["POST"])
def career_reset():
    session.pop("career_profile", None)
    flash("Entered details cleared. You can start a new career exploration.", "info")
    return redirect(url_for("career_home"))


# --------------------------------------------------------------------------- #
# Misc pages + errors
# --------------------------------------------------------------------------- #
@app.route("/about")
def about():
    return redirect(url_for("career_home") + "#about")


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "careers": len(career_service.careers()),
        "ai": ai_service.ai_status(),
    })


@app.errorhandler(404)
def not_found(error):
    return render_template("errors/error.html", code=404, title="Page not found",
                           message="That page does not exist. Use the navigation above to get back on track."), 404


@app.errorhandler(RequestEntityTooLarge)
def too_large(error):
    return render_template(
        "errors/error.html",
        code=413,
        title="File too large",
        message=f"Uploads are limited to {MAX_UPLOAD_MB} MB. Compress the file or upload a smaller version.",
    ), 413


@app.errorhandler(500)
def server_error(error):
    return render_template(
        "errors/error.html",
        code=500,
        title="Something went wrong",
        message="An unexpected error occurred. Your saved resume is still available — go back and try again.",
    ), 500


if __name__ == "__main__":
    if not os.getenv("SECRET_KEY"):
        app.logger.warning("SECRET_KEY is not set — using an ephemeral key. Copy .env.example to .env for stable sessions.")
    app.run(host="127.0.0.1", port=5000, debug=os.getenv("FLASK_DEBUG", "0") == "1")
