# AI Resume Builder & Career Recommendation System

A single Flask application that combines two working modules:

- **AI Resume Builder** — build a resume from scratch or upload an existing PDF/DOCX, edit every section, preview it live in three templates, download an ATS-friendly PDF, and score it with a transparent ATS checker.
- **CareerGuide** — a 40-career guidance system that matches a student's skills and interests, explains the score, and gives a three-level roadmap with real, clickable learning resources.

Everything runs locally. No database or cloud account is required, and the app is fully functional without an OpenAI key.

---

## 1. Quick start (Windows)

Requirements: **Python 3.10 or newer** (tested on Python 3.12). Use 3.11/3.12 if possible.

Open **Command Prompt** or **PowerShell** in the project folder (the folder that contains `app.py`):

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
python APP.PY
```

PowerShell users can replace `copy` with:

```powershell
Copy-Item .env.example .env
```

Then open **http://127.0.0.1:5000**.

> **About `python APP.PY`:** the file in the ZIP is `app.py`. Windows file names are case-insensitive, so `python APP.PY` and `python app.py` start the same file. On macOS/Linux use `python app.py` (case-sensitive).

### Generate a proper SECRET_KEY

The app runs without one, but sessions reset whenever the server restarts. Generate a key:

```bat
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste the output into `.env`:

```ini
SECRET_KEY=the-long-random-value-you-generated
```

`.env` is already listed in `.gitignore` — never commit it.

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open http://127.0.0.1:5000.

### Stopping and restarting

Press `Ctrl+C` in the terminal to stop the server. The resume you built is kept in `data/resumes/`, so it is still there next time as long as the browser session and `SECRET_KEY` are unchanged. Deleting `data/resumes/` and `data/uploads/` clears all saved local data.

---

## 2. Features

### Resume Builder

- Create a new resume or upload an existing **PDF/DOCX** and edit the extracted content.
- Sections: personal details, professional photo, career objective, education, technical/soft skills, projects, certifications (optional certificate files), and experience.
- Experience flow supports **I have experience**, **I am a fresher**, and **Skip this section**.
- Live preview, edit again, switch templates, go back, and download a PDF.
- Three templates: **Modern Professional**, **Classic Serif**, **Minimal Clean**.
- PDF mirrors the on-screen resume; photo sits at the top-right; all text stays selectable for ATS parsing.
- Projects and certificates accept links; certificate images are stored as attachments and never inserted into the resume body.
- Uploaded originals are preserved and can be downloaded later.

### ATS Checker

- Analyze the current resume or upload a separate PDF/DOCX for a one-off check.
- **Estimated score out of 100** from 10 weighted categories, with every point traceable to a named check.
- Shows category points, passed/failed checks, the reason for each deduction, missing role keywords, a prioritized improvement plan, and a learning plan.
- Re-run the analysis after editing; the score is recalculated from the current content.
- Clearly labelled: **this is not a score from any employer's proprietary ATS.**

### CareerGuide

- Home page with hero, guidance form, four feature cards, career library, About section, and the footer `© 2026 CareerGuide | Career Guidance System`.
- Form fields: name, qualification, degree/department, skills, interests, preferred domain, experience level.
- **40 careers** across 6 categories, each with description, technical skills, soft skills, related interests, responsibilities, projects, certifications, growth opportunities, a 3-level roadmap, and per-career learning resources.
- Matching formula: **Skills 60% + Interests 40%**, with synonym normalisation, top-5 ranking, and a detailed breakdown of matched and missing skills.
- Detail pages include a **Beginner → Intermediate → Advanced** roadmap, projects, growth paths, and **77 curated resources** (196 career-resource placements, 73 unique links) with free/paid status. Every link opens in a new tab with `target="_blank" rel="noopener noreferrer"`.
- Results are marked **preliminary** when the profile is too thin (fewer than 3 skills, fewer than 2 interests, or a top match below 35%).

### AI behaviour (honest fallback)

- The app works with **no AI key**. A rule-based writer handles objective generation/improvement.
- When `OPENAI_API_KEY` is set, the server may call OpenAI for objective generation, objective improvement, and an ATS coaching paragraph.
- Every result is labelled with its source (`Generated with OpenAI` vs `Generated by rule-based writer (AI unavailable)`).
- If a call fails (no key, timeout, quota, network), the app silently falls back and says so in the UI. It never claims an AI call succeeded when it did not.
- ATS scores and career matches are **always deterministic** and are never generated by AI.

---

## 3. Project structure

```
AI_RESUME_BUILDER/
├── app.py                      # Flask app: all routes, config, error handlers
├── career_data.json            # 40 careers, roadmap data, 77-resource catalogue
├── requirements.txt
├── .env.example                # environment template (copy to .env)
├── .gitignore
├── README.md
├── data/
│   ├── resumes/                # saved resume JSON (created at runtime)
│   ├── uploads/                # uploaded originals, photos, certificates
│   └── .gitkeep
├── services/
│   ├── resume_service.py       # schema, JSON storage, form parsing, templates
│   ├── extract_service.py      # PDF/DOCX extraction + section heuristics
│   ├── ats_service.py          # deterministic 10-category scoring
│   ├── career_service.py       # normalisation, scoring, ranking, roadmaps
│   ├── pdf_service.py          # ReportLab PDF for all three templates
│   └── ai_service.py           # optional OpenAI + honest rule-based fallback
├── utils/
│   └── helpers.py              # validation, safe filenames, sizing, formatting
├── templates/
│   ├── shared/base.html
│   ├── index.html
│   ├── resume/{entry,builder,preview,ats}.html
│   ├── career/{_subnav,home,results,detail}.html
│   └── errors/error.html
├── static/
│   ├── css/{base,home,resume,career}.css
│   └── js/{base,chips,builder,ats,career}.js
└── tests/
    └── test_app.py             # 80 end-to-end checks (Flask test client)
```

---

## 4. Configuration

Copy `.env.example` to `.env` and edit:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | random per start | Signs the session cookie. Set a stable value so resumes survive restarts. |
| `FLASK_ENV` | `development` | Template auto-reload unless set to `production`. |
| `FLASK_DEBUG` | `0` | Set `1` only for local debugging. Never expose debug mode publicly. |
| `SESSION_COOKIE_SECURE` | `0` | Set `1` when serving over HTTPS. |
| `MAX_UPLOAD_MB` | `8` | Maximum document upload size in MB. |
| `OPENAI_API_KEY` | empty | Optional. Enables the three AI-assisted text features. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model used when a key is configured. |
| `OPENAI_TIMEOUT` | `25` | Seconds before falling back to the rule-based writer. |

The OpenAI key is read server-side only. It is never sent to the browser, logged, or written into uploaded files.

---

## 5. Routes

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/` | Unified homepage |
| GET | `/resume` | Resume start screen (new / upload / saved) |
| GET | `/resume/new` | Blank builder |
| GET | `/resume/edit` | Edit the current resume |
| POST | `/resume/generate` | Validate and save builder form |
| POST | `/resume/upload` | Upload PDF/DOCX and extract |
| GET | `/resume/preview` | Live preview |
| POST | `/resume/template` | Switch template |
| GET | `/resume/download` | Download the generated PDF |
| GET | `/resume/photo/<resume_id>` | Session-protected profile photo |
| GET | `/resume/original/<resume_id>` | Session-protected original upload |
| GET | `/resume/certificate/<resume_id>/<index>` | Session-protected certificate file |
| POST | `/resume/delete` | Delete the current saved resume |
| GET | `/ats` | ATS checker |
| GET | `/resume/ats` | Alias that redirects to `/ats` |
| POST | `/ats/analyze` | Analyze builder resume or uploaded file |
| POST | `/api/objective` | Generate/improve objective (JSON) |
| GET | `/career` | CareerGuide home and form |
| GET, POST | `/career-recommendation` | Validate profile and show top 5 |
| GET | `/career/detail/<career_id>` | Career details and 3-level roadmap |
| POST | `/career/reset` | Clear saved career profile |
| GET | `/generate` | Alias for the resume start flow |
| GET | `/about` | Redirects to the CareerGuide About section |
| GET | `/health` | Health check (JSON) |

---

## 6. How the ATS score is calculated

The score is an **estimate of resume quality and ATS compatibility** produced by this app's open rule set. It is not a score from an employer's ATS, and no employer-specific ranking is implied. There are no random or fixed scores: every category is recomputed from the resume text and structured fields each time.

Weights sum to exactly **100**:

| Category | Max points | What is checked |
| --- | ---: | --- |
| Contact Information | 12 | Full name, valid email, 10–15 digit phone, location, at least one professional link |
| Career Objective | 10 | Objective present, 20–85 words, target role or relevant skills named |
| Education | 15 | At least one entry, institution + degree, dates, CGPA/percentage |
| Technical & Soft Skills | 15 | Technical breadth, total skill count, soft skills, clean labels, role-relevant skills |
| Projects | 15 | Section present, at least two projects, 20+ word descriptions, technologies, link |
| Certifications | 5 | Certifications listed, issuer and date present |
| Experience | 8 | Entries, responsibilities, quantified achievements (freshers can still score elsewhere) |
| Relevant Keywords | 10 | Share of the target role's expected keywords found in the resume |
| Formatting | 6 | Selectable text, bullets, readable line lengths, no tables, email in text layer, consistent dates |
| Readability | 4 | Bullet length, action verbs, concise objective, professional voice |

- **Builder analysis** uses the structured resume plus the text it would export.
- **Uploaded analysis** extracts the PDF/DOCX text, keeps formatting evidence (such as tables), infers the closest role when no target is given, and scores the actual file content.
- Each category reports earned points, the checks that passed or failed, and a specific reason for every deduction.
- The keyword target comes from the selected role or is inferred from the resume's skills. Missing keywords are listed.
- Suggestions are ordered by impact, and low scores produce a learning plan tied to real resources.
- Scanned PDFs without a text layer are detected and explained; OCR is not bundled, so those files cannot be scored fairly.

The full algorithm lives in `services/ats_service.py`, including the `WEIGHTS` constant and every `_check(...)` deduction message.

---

## 7. How career matching works

1. Skills and interests are split, trimmed, lowercased, and normalised through a synonym map (for example `js` → JavaScript, `ml` → Machine Learning, `powerbi` → Power BI).
2. For each of the 40 careers:
   - **Skills match** = matched required technical + soft skills ÷ total required skills × 100.
   - **Interests match** = matched related interests ÷ total related interests × 100.
   - **Career match** = `(Skills match × 0.60) + (Interests match × 0.40)`.
3. Careers are sorted by match descending, then by number of matched skills, then name. The top five are shown.
4. Partial matches are not inflated: if a career lists 10 required skills and the student has 4, the skills component is 40%.
5. The preferred domain does **not** change the score. It only highlights relevant careers in a separate strip on the results page.
6. Notes explain weak evidence and flag results as preliminary when appropriate.

The formula is printed on the results page, and the code is in `services/career_service.py` (`score_career`, `recommend`).

---

## 8. Data, uploads, and security

- Resumes are stored as JSON in `data/resumes/<id>.json`; the session stores only the resume ID.
- Uploaded originals, photos, and certificates live in `data/uploads/<resume_id>/` and are served only through session-ownership-checked routes. The `data/` folder is not a public static folder.
- Documents: PDF/DOCX only, default 8 MB limit, with a per-file byte check as well as Flask's global request limit.
- Photos: JPG/JPEG/PNG, maximum 4 MB; images are verified with Pillow, cropped square, and re-encoded as JPEG.
- Certificate attachments: PDF/JPG/JPEG/PNG; they are stored but intentionally excluded from the resume layout.
- Uploaded file names are sanitised; stored names are prefixed with random IDs.
- Sessions are HTTP-only, `SameSite=Lax`, and optionally secure behind HTTPS.
- Forms validate required fields, email format, URLs, and field lengths. Error pages cover 404, 413 (file too large), and 500 without exposing tracebacks.
- No API keys are embedded in HTML, CSS, or JavaScript.
- The app is intended for local/single-user use. There is no login system and no multi-tenant database; use a real database and authentication before exposing it publicly.

---

## 9. Testing

Run the automated suite from the project root:

```bat
python tests/test_app.py
```

The suite uses Flask's test client, so no server or browser is needed. It writes temporary test resumes under `data/`; delete those folders to reset the demo data. Latest result on **1 November 2026**:

```
passed=80 failed=0
```

It covers, among other things:

- Resume generation, preview, photo handling, template switching, PDF text content.
- PDF/DOCX upload, extraction into the builder, preservation of the original file, scanned-PDF handling.
- ATS scoring bounds, category breakdown, deduction explanations, keyword targeting, reanalysis, uploaded-file cleanup.
- Objective API provenance labels and rule-based fallback.
- Career recommendations, five-result ranking, formula consistency, synonym matching, thin-profile warnings, detail pages, roadmaps, and clickable resources.
- Validation failures, session ownership of photos, unknown resume 404, and `/health`.

Additional verification performed for this release:

- **73/73 unique learning-resource URLs** returned a reachable HTTP response (checked 1 November 2026).
- All 40 career roadmaps were checked with empty, partial, and complete skill profiles (120 combinations); every Beginner, Intermediate, and Advanced level had at least one real, labelled resource.
- All public pages returned 200/redirect as expected.
- `python -m compileall app.py services utils` passed.
- The packaged ZIP was extracted into a clean directory and the same test suite was run against the extracted copy.

External links can change after the check date; the app opens the real provider rather than embedding content.

---

## 10. Limitations

- The ATS score is a **transparent estimate**, not a hiring prediction and not a proprietary ATS result.
- OCR is not included: image-only/scanned PDFs cannot be read. The original is preserved and the user is asked to type details manually.
- PDF extraction is heuristic. Complex multi-column layouts, tables, and unusual section names may need manual correction in the builder.
- Resume PDFs intentionally avoid tables for ATS safety; photo placement is fixed per template.
- Career guidance relies only on the entered profile. It does not use live job-market data, salaries, or employer demand.
- Recommendations are authored guidance, not guarantees of eligibility or employment.
- AI text features are optional and never required for scoring or recommendations.
- Data is local JSON rather than a database; there is no login, cloud sync, or multi-user isolation beyond the browser session.
- The development server is not a production WSGI deployment. Put it behind a production server and HTTPS before any real deployment.

---

## 11. Troubleshooting

**`'python' is not recognized`**
Install Python 3.10+ from python.org and enable "Add Python to PATH". On Windows you can also try `py -3 APP.PY`.

**Port 5000 already in use**
Stop the other process (`netstat -ano | findstr :5000`, then end that PID) or run the app after freeing the port. The app is configured for port 5000.

**`python APP.PY` says file not found on Windows**
Make sure you are in the folder containing `app.py`. Windows is case-insensitive, so the exact case of `APP.PY` is not the issue.

**Sessions reset after restart**
Set a stable `SECRET_KEY` in `.env`.

**Upload does not fill the form**
The file may be scanned or unusually structured. The app explains this in a warning; type the fields manually and use the original download link to compare. ATS analysis of a text-based upload still works.

**Photo rejected**
Use JPG, JPEG, or PNG under 4 MB. Very large photos should be resized first.

**OpenAI is not used**
That is expected without `OPENAI_API_KEY`. The UI labels the rule-based fallback; no feature is blocked.

**PDF download fails**
Reinstall requirements (`pip install -r requirements.txt`), confirm you are running Python 3.10+, and check the terminal for the error page's server-side details.

---

## 12. Credits and disclaimer

Built as a complete local project for resume building and career guidance. CareerGuide content is educational guidance, and ATS scores are estimates from the documented rule set. Resume and career data stay on the machine where the app runs.
