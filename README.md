# PlaceIQ

PlaceIQ is an AI-powered placement readiness platform for engineering students, aligned with the **official VTU 2025 scheme** curriculum standard.

## Features & Highlights

- **Skill Intelligence (Phase 2.1)**: Canonical skill normalization O(1) + rapidfuzz matching across 100+ technical skills and aliases.
- **ATS & Resume Hardening (Phase 2.2)**: Reliable PDF text extraction, structured output validation, blended ATS scoring (LLM + structural), and zero-AI job description keyword matching.
- **VTU 2025 Scheme Alignment (Phase 2.3)**: Complete syllabus-to-skill mapping for CSE, ISE, and ECE branches across Semesters 3 through 8. Accurately determines syllabus-covered skills vs. resume skills vs. missing gaps for placement roles.
- **Personalized 6-Week Roadmap (Phase 3.1, 3.2, 3.3)**: Tailored 6-week technical study roadmap derived from VTU skill-gap reports. Distinguishes syllabus revision (`[REVISE]`) from new skill acquisition (`[LEARN]`), prioritizes higher-weight skills, provides clean general learning resource recommendations, and persists completion progress in SQLite.
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
│   │   │   ├── llm.py                # Groq LLM integration & repair
│   │   │   ├── resume_parser.py      # Hardened PDF text extractor
│   │   │   ├── roadmap_generator.py  # Personalized 6-week roadmap engine
│   │   │   └── skill_extractor.py    # Skill normalization & validation
│   │   └── tests/                    # Phase test suites
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
```
