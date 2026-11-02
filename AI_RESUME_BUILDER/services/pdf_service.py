"""PDF rendering with ReportLab.

The PDF mirrors the on-screen resume templates: same section order, same optional
sections, same photo position (top-right) and the same ATS-friendly plain-text
structure. Each template returns an in-memory PDF so nothing is left on disk.
"""

from __future__ import annotations

import re
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from services import resume_service
from utils.helpers import clean_text, escape, pretty_date, year_range

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_X = 16 * mm
MARGIN_Y = 14 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN_X
PHOTO_BOX = 30 * mm


TEMPLATE_STYLES = {
    "modern": {
        "font": "Helvetica",
        "bold": "Helvetica-Bold",
        "accent": colors.HexColor("#4338ca"),
        "text": colors.HexColor("#1f2937"),
        "muted": colors.HexColor("#4b5563"),
        "name_size": 21,
        "heading_size": 10,
        "body_size": 9.3,
        "leading": 12.6,
        "align": TA_LEFT,
        "heading_rule": True,
        "heading_transform": "upper",
        "bullet_color": colors.HexColor("#4338ca"),
    },
    "classic": {
        "font": "Times-Roman",
        "bold": "Times-Bold",
        "accent": colors.HexColor("#111827"),
        "text": colors.HexColor("#111827"),
        "muted": colors.HexColor("#374151"),
        "name_size": 22,
        "heading_size": 11.5,
        "body_size": 9.8,
        "leading": 13.2,
        "align": TA_CENTER,
        "heading_rule": True,
        "heading_transform": "upper",
        "bullet_color": colors.HexColor("#111827"),
    },
    "minimal": {
        "font": "Helvetica",
        "bold": "Helvetica-Bold",
        "accent": colors.HexColor("#0f766e"),
        "text": colors.HexColor("#111827"),
        "muted": colors.HexColor("#6b7280"),
        "name_size": 20,
        "heading_size": 9.4,
        "body_size": 9.1,
        "leading": 12.4,
        "align": TA_LEFT,
        "heading_rule": True,
        "heading_transform": "upper",
        "bullet_color": colors.HexColor("#0f766e"),
    },
}


def _styles(template_id: str) -> dict:
    spec = TEMPLATE_STYLES.get(template_id, TEMPLATE_STYLES["modern"])
    body = ParagraphStyle(
        "body", fontName=spec["font"], fontSize=spec["body_size"], leading=spec["leading"],
        textColor=spec["text"], spaceAfter=1.5,
    )
    return {
        "spec": spec,
        "name": ParagraphStyle(
            "name", fontName=spec["bold"], fontSize=spec["name_size"], leading=spec["name_size"] * 1.15,
            textColor=spec["accent"], alignment=spec["align"], spaceAfter=1,
        ),
        "role": ParagraphStyle(
            "role", fontName=spec["font"], fontSize=spec["body_size"] + 1, leading=13,
            textColor=spec["muted"], alignment=spec["align"], spaceAfter=3,
        ),
        "contact": ParagraphStyle(
            "contact", fontName=spec["font"], fontSize=8.5, leading=11.4,
            textColor=spec["muted"], alignment=spec["align"], spaceAfter=1,
        ),
        "heading": ParagraphStyle(
            "heading", fontName=spec["bold"], fontSize=spec["heading_size"], leading=spec["heading_size"] * 1.35,
            textColor=spec["accent"], spaceBefore=5, spaceAfter=3,
        ),
        "body": body,
        "bullet": ParagraphStyle(
            "bullet", parent=body, leftIndent=9, bulletIndent=1, spaceAfter=2.2,
        ),
        "entry": ParagraphStyle(
            "entry", fontName=spec["bold"], fontSize=spec["body_size"] + 0.4, leading=body.leading,
            textColor=spec["text"], spaceAfter=1,
        ),
        "meta": ParagraphStyle(
            "meta", fontName="Helvetica-Oblique", fontSize=8.4, leading=10.8,
            textColor=spec["muted"], spaceAfter=2,
        ),
    }


def _p(text: str, style) -> Paragraph:
    """Escape user text and convert newlines to paragraph breaks."""
    safe = escape(text).replace("\n", "<br/>")
    return Paragraph(safe, style)


def _section(title: str, styles: dict, flowables: list) -> list:
    spec = styles["spec"]
    label = title.upper() if spec["heading_transform"] == "upper" else title
    parts = [Paragraph(escape(label), styles["heading"])]
    if spec["heading_rule"]:
        parts.append(HRFlowable(width="100%", thickness=0.7, color=spec["accent"], spaceBefore=0, spaceAfter=5))
    parts.extend(flowables)
    parts.append(Spacer(1, 3.5 * mm))
    return [KeepTogether(parts)] if len(parts) < 6 else parts


def _photo_flowable(resume: dict):
    path = resume_service.stored_path(resume["personal"].get("photo"))
    if not path:
        return None
    try:
        from PIL import Image as PILImage

        with PILImage.open(path) as probe:
            width, height = probe.size
        if width <= 0 or height <= 0:
            return None
        scale = min(PHOTO_BOX / width, PHOTO_BOX / height)
        return Image(str(path), width=width * scale, height=height * scale)
    except Exception:
        return None


def _header(resume: dict, styles: dict) -> list:
    personal = resume["personal"]
    spec = styles["spec"]
    left: list = [Paragraph(escape(personal.get("full_name") or "Resume"), styles["name"])]
    if resume.get("target_role"):
        left.append(Paragraph(escape(resume["target_role"]), styles["role"]))

    contact_bits = [bit for bit in (personal.get("email"), personal.get("phone"), personal.get("location")) if bit]
    if contact_bits:
        separator = "  •  "
        left.append(Paragraph(escape(separator.join(contact_bits)), styles["contact"]))

    links = []
    for key in ("linkedin", "github", "portfolio"):
        url = personal.get(key)
        if not url:
            continue
        # Show the readable URL itself (not just a label) so the text layer stays ATS-parsable.
        display = re.sub(r"^https?://(www\.)?", "", url).rstrip("/")
        if len(display) > 52:
            display = display[:50] + "…"
        links.append(f'<link href="{escape(url)}" color="#1d4ed8">{escape(display)}</link>')
    if links:
        left.append(Paragraph("  |  ".join(links), styles["contact"]))

    photo = _photo_flowable(resume)
    if not photo:
        return [*left, Spacer(1, 2 * mm)]

    photo_cell = Table([[photo]], colWidths=[PHOTO_BOX + 2 * mm], rowHeights=[PHOTO_BOX + 2 * mm])
    photo_cell.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    layout = Table([[left, photo_cell]], colWidths=[CONTENT_WIDTH - PHOTO_BOX - 6 * mm, PHOTO_BOX + 6 * mm])
    layout.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [layout, Spacer(1, 4 * mm)]


def _education(resume: dict, styles: dict) -> list:
    items = []
    for entry in resume.get("education", []):
        years = year_range(entry.get("start_year"), entry.get("grad_year"))
        degree = " — ".join(filter(None, [entry.get("degree"), entry.get("department")]))
        line_one = escape(entry.get("institution", "") or "Institution")
        if degree:
            line_one += f'  <font color="#4b5563">|</font>  {escape(degree)}'
        if years:
            line_one += f'  <font color="#4b5563">|</font>  {escape(years)}'
        items.append(Paragraph(line_one, styles["body"]))
        if entry.get("score"):
            items.append(Paragraph(f"Score: {escape(entry['score'])}", styles["meta"]))
    return items


def _skills(resume: dict, styles: dict) -> list:
    skills = resume["skills"]
    items = []
    if skills.get("technical"):
        items.append(Paragraph(
            f"<b>Technical Skills:</b> {escape(', '.join(skills['technical']))}", styles["body"]
        ))
    if skills.get("soft"):
        items.append(Paragraph(
            f"<b>Soft Skills:</b> {escape(', '.join(skills['soft']))}", styles["body"]
        ))
    return items


def _projects(resume: dict, styles: dict) -> list:
    items = []
    for project in resume.get("projects", []):
        heading = f"<b>{escape(project.get('title', 'Project'))}</b>"
        if project.get("url"):
            heading += f'  <link href="{escape(project["url"])}" color="#1d4ed8"><font size="8">demo</font></link>'
        items.append(Paragraph(heading, styles["body"]))
        if project.get("technologies"):
            items.append(Paragraph(f"<i>{escape(project['technologies'])}</i>", styles["meta"]))
        for bullet in _bullet_list(project.get("description")):
            items.append(Paragraph(escape(bullet), styles["bullet"], bulletText="•"))
        if project.get("url"):
            items.append(Paragraph(
                f'<link href="{escape(project["url"])}" color="#1d4ed8">{escape(project["url"])}</link>',
                styles["meta"],
            ))
        items.append(Spacer(1, 1.2 * mm))
    return items


def _certifications(resume: dict, styles: dict) -> list:
    items = []
    for cert in resume.get("certifications", []):
        bits = [f"<b>{escape(cert.get('name', 'Certification'))}</b>"]
        if cert.get("organization"):
            bits.append(escape(cert["organization"]))
        if cert.get("issue_date"):
            bits.append(escape(pretty_date(cert["issue_date"])))
        if cert.get("credential_id"):
            bits.append(f"ID: {escape(cert['credential_id'])}")
        text = " — ".join(bits)
        if cert.get("url"):
            text += f'  <link href="{escape(cert["url"])}" color="#1d4ed8"><font size="8">verify</font></link>'
        items.append(Paragraph(text, styles["bullet"], bulletText="•"))
    return items


def _experience(resume: dict, styles: dict) -> list:
    items = []
    if not resume.get("experience") and resume.get("experience_status") == "fresher":
        return [Paragraph(
            "Fresher — actively building practical skills through academic projects and certifications.",
            styles["body"],
        )]
    for job in resume.get("experience", []):
        line = f"<b>{escape(job.get('title') or job.get('company') or 'Role')}</b>"
        if job.get("company") and job.get("title"):
            line += f"  |  {escape(job['company'])}"
        if job.get("duration"):
            line += f"  |  {escape(job['duration'])}"
        items.append(Paragraph(line, styles["body"]))
        for bullet in _bullet_list(job.get("responsibilities")):
            items.append(Paragraph(escape(bullet), styles["bullet"], bulletText="•"))
        for bullet in _bullet_list(job.get("achievements")):
            items.append(Paragraph(escape(bullet), styles["bullet"], bulletText="•"))
        items.append(Spacer(1, 1.2 * mm))
    return items


def _bullet_list(text: str | None) -> list[str]:
    if not text:
        return []
    lines = [line.strip(" •-*·\t") for line in str(text).replace("\r", "\n").split("\n")]
    return [line for line in lines if len(line) > 2]


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7.2)
    canvas.setFillColor(colors.HexColor("#9ca3af"))
    canvas.drawRightString(PAGE_WIDTH - MARGIN_X, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf(resume: dict, template_id: str | None = None) -> bytes:
    """Render the resume to PDF bytes."""
    resume = resume_service.normalise_resume(resume)
    template_id = template_id if template_id in TEMPLATE_STYLES else resume.get("template", "modern")
    resume["template"] = template_id
    styles = _styles(template_id)

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_Y,
        bottomMargin=12 * mm,
        title=f"{resume['personal'].get('full_name') or 'Resume'} — Resume",
        author=resume["personal"].get("full_name") or "Candidate",
        subject="Resume",
    )

    story: list = []
    story.extend(_header(resume, styles))

    objective = clean_text(resume.get("objective", ""))
    if objective:
        story.extend(_section("Career Objective", styles, [_p(objective, styles["body"])]))

    education = _education(resume, styles)
    if education:
        story.extend(_section("Education", styles, education))

    skills = _skills(resume, styles)
    if skills:
        story.extend(_section("Skills", styles, skills))

    projects = _projects(resume, styles)
    if projects:
        story.extend(_section("Projects", styles, projects))

    certifications = _certifications(resume, styles)
    if certifications:
        story.extend(_section("Certifications", styles, certifications))

    experience = _experience(resume, styles)
    if experience and (resume.get("experience") or resume.get("experience_status") == "fresher"):
        story.extend(_section("Experience", styles, experience))

    document.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def pdf_filename(resume: dict) -> str:
    name = (resume.get("personal", {}).get("full_name") or "resume").strip()
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in name.replace(" ", "_"))
    return f"{safe or 'resume'}_resume.pdf"
