# PlaceIQ

PlaceIQ is an AI-powered placement readiness platform for engineering students, aligned with the **official VTU 2025 scheme** curriculum standard.

## Features & Highlights

- **Skill Intelligence (Phase 2.1)**: Canonical skill normalization O(1) + rapidfuzz matching across 100+ technical skills and aliases.
- **ATS & Resume Hardening (Phase 2.2)**: Reliable PDF text extraction, structured output validation, blended ATS scoring (LLM + structural), and zero-AI job description keyword matching.
- **VTU 2025 Scheme Alignment (Phase 2.3)**: Complete syllabus-to-skill mapping for CSE, ISE, and ECE branches across Semesters 3 through 8. Accurately determines syllabus-covered skills vs. resume skills vs. missing gaps for placement roles.
- **Personalized 6-Week Roadmap (Phase 3.1, 3.2, 3.3)**: Tailored 6-week technical study roadmap derived from VTU skill-gap reports. Distinguishes syllabus revision (`[REVISE]`) from new skill acquisition (`[LEARN]`), prioritizes higher-weight skills, provides clean general learning resource recommendations, and persists completion progress in SQLite.
- **Structured Skill Learning (Phase 1)**: Open a canonical skill from a mapped roadmap task, study validated concept-based lessons with role and VTU context, navigate lesson-by-lesson, and resume persisted lesson completion. Lesson completion is progress tracking, not a skill-mastery score.
- **Lesson Practice Engine (Learning Phase 2)**: Start a practice set from a lesson, answer validated multiple-choice, code-output, debugging, and coding/problem-solving questions, review feedback, and resume user-owned attempts. Practice performance remains separate from lesson completion and skill mastery.
- **Lesson Assessment Engine (Learning Phase 3)**: Start a structured assessment from a lesson, submit a complete answer set, receive deterministic scoring and answer explanations, and review concepts that went well or need review. Each result belongs to a student's attempt and is not a skill-mastery or placement-readiness score.
- **Assessment-Evidence Skill Mastery (Learning Phase 4)**: View per-canonical-skill progress, concept strengths and review areas, and a chronological evidence history derived exclusively from submitted assessment results.
- **Adaptive Learning Recommendations (Phase 5.1)**: Deterministically prioritize assessment-backed concept review and reassessment, then upcoming roadmap and role skill-gap study tasks. Every recommendation includes its reason, supporting evidence, and next action; it does not change mastery, assessments, roadmap tasks, or readiness.
- **Adaptive Roadmap Priorities (Phase 5.2)**: Adapt priorities on the student's existing roadmap using Phase 5.1 recommendations and submitted assessment evidence. Labels distinguish assessment-supported weaknesses, insufficient evidence (not failure), and upcoming learning without a demonstrated weakness. Only mapped, incomplete tasks receive annotations; task order, completion, indices, and historical roadmaps remain intact.
- **Adaptive Learning Feedback Loop (Phase 5.3)**: Newly submitted assessments immediately flow through the existing mastery and recommendation services; students can explicitly refresh roadmap priorities from the assessment result and follow recommendations to the relevant lesson action. Practice remains excluded from mastery evidence.
- **AI Study Coach (Phase 6)**: Ask for a beginner-friendly explanation, progressive hints, and an example for a selected lesson concept. The authenticated Groq-backed coach uses the student's available profile, mapped VTU subject names, lesson content, and a compact assessment-only mastery summary; invalid or unavailable AI output falls back to the stored lesson without changing learning progress or mastery.
- **Core Mock Interview Engine (Phase 4.1)**: Generates personalized 8-question mock interview sessions (5 Technical + 3 HR/Behavioral) tailored to the student's target role, VTU-aware skill gaps, weak points from prior sessions, and specific resume projects.

## Architecture & Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy, SQLite, Pydantic v2, RapidFuzz, pdfplumber, Groq API (Qwen/Developer tier text models).
- **Frontend**: React 18, Vite, Tailwind CSS, Lucide icons, Framer Motion.
- **Curriculum Standard**: Official VTU 2025 Scheme (Semesters 3–8 for CSE, ISE, and ECE).

## Project Structure

```
placeiq/
├── backend/
│   ├── app/
│   │   ├── data/
│   │   │   ├── roles.json            # Target placement role definitions
│   │   │   ├── skills_master.json   # Canonical skill dictionary & aliases
│   │   │   └── syllabus.json        # VTU 2025 scheme syllabus mapping
│   │   ├── routers/                  # FastAPI routers (auth, gap, resume, roadmap, interview, etc.)
│   │   ├── services/                 # Core engine services
│   │   │   ├── ats_engine.py         # Deterministic ATS & JD matcher
│   │   │   ├── gap_analyzer.py       # VTU syllabus gap analyzer
│   │   │   ├── interview_generator.py # Core mock interview engine (5 Tech + 3 HR)
│   │   │   ├── learning_content.py  # Structured skill lessons & safe fallback
│   │   │   ├── study_coach.py       # Lesson-focused Groq guidance & bounded fallback
│   │   │   ├── assessment_engine.py # Validated lesson assessments & scoring
│   │   │   ├── adaptive_recommendations.py # Evidence-based learning next steps
│   │   │   ├── adaptive_roadmap.py # Explainable priorities on the existing roadmap
│   │   │   ├── practice_engine.py   # Validated practice questions, grading & fallback
│   │   │   ├── skill_mastery.py     # Deterministic mastery policy over assessment evidence
│   │   │   ├── llm.py                # Groq LLM integration & repair
│   │   │   ├── resume_parser.py      # Hardened PDF text extractor
│   │   │   ├── roadmap_generator.py  # Personalized 6-week roadmap engine
│   │   │   └── skill_extractor.py    # Skill normalization & validation
│   │   └── tests/                    # Phase test suites
│   │       ├── test_learning.py
│   │       ├── test_assessment.py
│   │       ├── test_adaptive_recommendations.py
│   │       ├── test_adaptive_roadmap.py
│   │       ├── test_skill_mastery.py
│   │       ├── test_practice.py
│   │       ├── test_phase21.py
│   │       ├── test_phase22.py
│   │       ├── test_phase23.py
│   │       ├── test_phase31.py
│   │       ├── test_phase32.py
│   │       ├── test_phase33.py
│   │       └── test_phase41.py
└── frontend/                         # React UI application
```

## Running Tests

From `backend/`:

### Provisioning the first local admin

Register the account normally first, then run this from `backend/` while using
the intended local SQLite database:

```powershell
.\venv\Scripts\python.exe scripts\promote_first_admin.py --email you@example.com --confirm-local-development
```

The command only changes the role of the matching existing student account. It
does not create accounts, change passwords, or alter profile data. It refuses
to run against non-file SQLite databases and is available only while no admin
exists. The email must exactly match the account used at registration. Do not
use the legacy demo seeder; it is disabled.

### Local-only placement access recovery

If the existing admin password is unavailable, the following break-glass
command is limited to the configured, local SQLite database. Stop the backend
first. Run from `backend/` in dry-run mode before applying:

```powershell
$db = (Resolve-Path .\placeiq.db).Path
.\venv\Scripts\python.exe scripts\recover_placement_staff.py --database "$db" --confirm-database "$db" --user-id 14 --confirm-user-id 14 --backup "$db.placement-staff-backup.db"
```

Review the dry-run target and planned backup. For the write, keep the backend
stopped and run the same command with `--apply --confirm-backend-stopped`.
The script creates a new SQLite-API backup, verifies its integrity, schema, and
row counts, then asks you to type the exact verified backup path before changing
anything. It changes only user 14's `role`, requires that account to still be a
student, and verifies existing admin access afterward. It refuses noncanonical,
missing, non-SQLite, remote, or non-configured database targets and never
overwrites a backup.

### Granting local placement-staff access

When an admin already exists, use the existing admin-only API rather than the
first-admin command. Start the local backend, then run from `backend/`:

```powershell
.\venv\Scripts\python.exe scripts\grant_placement_staff.py --admin-email existing-admin@example.com --user-id 14
```

The command prompts for the existing admin password with hidden input, signs in
through `/auth/login`, and sends the grant through
`PUT /auth/admin/users/{user_id}/placement-staff`. It is restricted to
localhost/loopback and does not print or persist the password or access token.
Only an existing admin can grant the role; a student running the command is
rejected by the backend. If you cannot authenticate as an admin, ask the
existing admin to grant access or recover that account through a trusted
operator process; this command does not bypass admin authorization.

```bash
# Run Phase 2.1 tests (Skill Intelligence)
python -m app.tests.test_phase21

# Run Phase 2.2 tests (ATS Engine & Validation)
python -m app.tests.test_phase22

# Run Phase 2.3 tests (VTU 2025 Syllabus & Gap Analysis)
python -m app.tests.test_phase23

# Run Phase 3.1 tests (Personalized 6-Week Roadmap Engine)
python -m app.tests.test_phase31

# Run Phase 3.2 tests (SQLite Task Toggle & Persistence)
python -m app.tests.test_phase32

# Run Phase 3.3 tests (Final Roadmap Quality & UI Completion)
python -m app.tests.test_phase33

# Run Phase 4.1 tests (Core Mock Interview Engine)
python -m app.tests.test_phase41

# Run Phase 1 skill learning tests
python -m pytest app/tests/test_learning.py

# Run Learning Phase 2 practice tests
python -m pytest app/tests/test_practice.py

# Run Learning Phase 3 assessment tests
python -m pytest app/tests/test_assessment.py

# Run Learning Phase 4 skill mastery tests
python -m pytest app/tests/test_skill_mastery.py

# Run Learning Phase 5.1 recommendation tests
python -m pytest app/tests/test_adaptive_recommendations.py

# Run Learning Phase 5.2 adaptive roadmap tests
python -m pytest app/tests/test_adaptive_roadmap.py

# Run Learning Phase 5.3 adaptive feedback-loop tests
python -m pytest app/tests/test_adaptive_feedback_loop.py

# Run Study Coach and learning API tests
python -m pytest app/tests/test_learning.py
```

## Razorpay Test Mode (Premium)

Razorpay checkout is optional and disabled until a configured
`PREMIUM_AMOUNT_MINOR` and all three Razorpay Test Mode credentials are present. The
amount is an integer in the currency's minor unit (for INR, paise); no default
sale price is supplied. Configure `PREMIUM_CURRENCY` (three uppercase letters)
and the backend-only `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and
`RAZORPAY_WEBHOOK_SECRET` in `backend/.env`. Start from
[`backend/.env.example`](backend/.env.example); replace its placeholders with
credentials created in the Razorpay Dashboard's **Test Mode** only. Never put a
secret in a `VITE_*` variable or frontend source. Install the additive SDK
dependency in the backend environment with:

```powershell
pip install -r backend\requirements-payment.txt
```

In the Razorpay Dashboard, switch to Test Mode, generate the API Key ID and
Key Secret, and copy them directly into the backend `.env` without sharing or
committing them. Run the API and Vite frontend in separate terminals:

```powershell
Set-Location backend
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

```powershell
Set-Location frontend
npm run dev
```

The authenticated `POST /premium/payment/orders` contract accepts no browser
price, currency, user, or plan. It returns `payment_order_id`, Razorpay
`order_id`, configured `amount` and `currency`, the public Test Mode `key_id`,
and a plan description. `POST /premium/payment/verify` accepts only
`razorpay_order_id`, `razorpay_payment_id`, and `razorpay_signature`.
`GET /premium/payment/orders/{payment_order_id}` reconciles saved attempts with
Razorpay for a safe status refresh. The unauthenticated
`POST /premium/payment/webhook` requires a valid signature over the raw body
and the Razorpay `x-razorpay-event-id` header.

Premium activates only after server-side checkout-signature verification and a
server-side Razorpay payment fetch reports `captured` with the matching local
order, amount, and currency, or a valid `payment.captured` webhook reports the
same matching evidence. An order, access request, failed or merely authorized
payment never grants access. Checkout-signature validity alone does not prove
settlement. Duplicate events and captured-payment callbacks are idempotent;
older failed/authorized notifications cannot downgrade a captured order.
If order creation times out ambiguously, its stable server receipt is reconciled
before another payable order can be created.

To test webhooks, create a webhook in the Razorpay Dashboard while in Test Mode,
set its callback URL to the reachable HTTPS development URL ending in
`/premium/payment/webhook` (Razorpay cannot call plain localhost), enable
`payment.captured`, `payment.authorized`, and `payment.failed`, choose a webhook
secret in the Dashboard, and set the same value only as backend
`RAZORPAY_WEBHOOK_SECRET`. Use the
provider's test checkout tools to exercise captured, failed, and cancelled
flows; retry a signed captured event with the same event ID to test duplicate
delivery. A tampered signature must be rejected. Verify delayed settlement
using the authenticated status-refresh route. Never send real card details to
PlaceIQ.

For a deployed SQLite database, stop the backend and create a timestamped
backup before applying
[`backend/migrations/002_add_premium_payment_tables.sql`](backend/migrations/002_add_premium_payment_tables.sql);
the exact PowerShell/SQLite commands are in
[`backend/migrations/README.md`](backend/migrations/README.md). Tests use
temporary SQLite databases and do not run migrations against
`backend/placeiq.db`. Confirm Core endpoints still work and existing pending
access requests remain pending after testing. Razorpay Test Mode does not
collect real money. Live Mode, recurring billing, refunds, and operational paid
upgrades are not implemented; a verified test capture activates the existing
Premium entitlement solely for test integration.

The authenticated practice API is available under `/learning/practice`: create a session with a canonical `skill_id` and lesson ID, retrieve it by session ID, and submit answers to its question IDs. Session responses omit answer keys; attempts are scoped to their owning student.

The authenticated assessment API is available under `/learning/assessment`: create an attempt with a canonical `skill_id` and lesson ID, retrieve it by attempt ID, and submit one answer for every question to `/learning/assessment/{assessment_id}/submit`. Correct answers and explanations are withheld until submission; results are owned by the authenticated student.

The authenticated mastery APIs are `GET /learning/mastery` (all skills with submitted assessment evidence) and `GET /learning/mastery/{skill_id}` (one canonical skill and its history). Scoring policy: each submitted assessment question contributes one equally weighted correct/incorrect observation; repeated submitted assessments are all retained and older attempts are not discarded. Fewer than two submitted assessments or six answered questions yields `insufficient_evidence` and a `null` skill evidence score. Otherwise, the displayed evidence score is cumulative accuracy across all submitted questions. `demonstrated_proficiency` requires both cumulative accuracy of at least 80% and at least 70% accuracy on the latest assessment; other sufficiently evidenced results are `developing`. A concept is assigned `strength` at 80% or higher, otherwise `review`, only after at least two assessment questions for that concept across two distinct assessments. Resume, syllabus, roadmap completion, lesson completion, practice, and interview feedback are excluded. Mastery history is reconstructed chronologically from the existing immutable submitted assessment attempts; no new database table is required.

The authenticated Phase 5.1 endpoint is `GET /learning/recommendations`, optionally filtered by a canonical `skill_id`. It prioritizes repeated assessment concept review, reassessment when mastery evidence is insufficient, and then incomplete roadmap or role-gap study tasks. Missing assessment evidence is explicitly not treated as failure. Roadmap and gap reports are planning context only; no records are updated. The dashboard shows up to two next steps returned by this endpoint.
The authenticated Phase 5.2 endpoint is `POST /roadmap/adapt`. It adds deterministic, explainable priority annotations to canonical-skill tasks on the student's current roadmap using assessment-evidence recommendations. It never reorders tasks, changes completed tasks, generates a replacement roadmap, or changes assessment, mastery, or readiness records. Existing task indices remain stable for the completion API.

The authenticated Phase 6 endpoint is `POST /learning/coach`. Send `skill_id`, `lesson_id`, `concept`, and an optional `question` (maximum 500 characters). The endpoint resolves the canonical skill, verifies the lesson belongs to the authenticated student's stored course, and returns bounded `explanation`, progressive `hints`, `example`, `source` (`groq` or `lesson_fallback`), an assessment-evidence summary, and validated lesson/practice/assessment actions. Profile and mastery context are loaded server-side; only compact evidence counts/status/score are sent to Groq, never assessment answers. VTU context is limited to mapped subject names available for the student's branch and semester. Provider errors and invalid output do not expose raw provider details: they produce guidance grounded in the selected stored lesson. The request is explicit from the Learning page; the coach does not maintain chat history, update lesson progress, alter mastery, or change assessment, roadmap, or readiness data.
