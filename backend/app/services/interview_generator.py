"""
Core Mock Interview Engine for PlaceIQ (Phase 4.1)

Generates personalized 8-question interview sessions (5 Technical + 3 HR) tailored to:
- Student's VTU-aware skill gaps
- Weak skills from prior interview sessions
- Target placement role
- Specific resume projects from the student's latest resume
"""
from app.services.llm import ask_llm_json
from app.services.gap_analyzer import analyze_skill_gap, get_role_requirements


def _validate_interview_output(raw: dict, target_role: str) -> list[str]:
    """
    Validate and sanitize LLM interview questions output.
    Ensures a list of exactly 8 non-empty string questions (5 Technical + 3 HR).
    """
    if not isinstance(raw, dict):
        raw = {}

    questions_raw = raw.get("questions")
    if not isinstance(questions_raw, list):
        questions_raw = []

    clean_qs = []
    seen = set()
    for q in questions_raw:
        if isinstance(q, str) and q.strip():
            q_clean = q.strip()
            if q_clean.lower() not in seen:
                seen.add(q_clean.lower())
                clean_qs.append(q_clean)

    return clean_qs


def _deterministic_interview_fallback(
    target_role: str,
    gap_skills: list[str],
    weak_skills: list[str],
    project_name: str,
    project_tech: list[str],
) -> list[str]:
    """
    Generate a deterministic fallback list of exactly 8 questions (5 Technical + 3 HR)
    personalized with the student's project, skill gaps, weak points, and target role.
    """
    primary_gap = gap_skills[0] if gap_skills else "Core Architecture"
    secondary_gap = gap_skills[1] if len(gap_skills) > 1 else "Data Structures"
    weak_focus = weak_skills[0] if weak_skills else primary_gap
    proj = project_name or "your technical project"
    tech_stack = ", ".join(project_tech[:3]) if project_tech else "the tech stack used"

    tech_qs = [
        # Tech 1: Skill gap & weak skill focus
        f"For the role of {target_role}, how would you approach learning and implementing {weak_focus} in a production environment?",
        # Tech 2: Project-specific technical question
        f"In your project '{proj}' ({tech_stack}), what was the most challenging technical obstacle you faced and how did you resolve it?",
        # Tech 3: Core skill gap / architecture
        f"Explain the core principles of {primary_gap} and how it applies to building scalable applications in {target_role}.",
        # Tech 4: Secondary gap / problem solving
        f"How do you ensure data integrity, error handling, and performance optimization when working with {secondary_gap}?",
        # Tech 5: Role-specific technical scenarios
        f"Walk me through how you would design a mini-system or component for {target_role}, highlighting key technical tradeoffs.",
    ]

    hr_qs = [
        # HR 1: Teamwork & Conflict Resolution
        f"Tell me about a time when you had to work in a team for a technical project. How did you handle differences of opinion?",
        # HR 2: Adaptability & Handling Pressure
        f"Describe a situation where a project deadline or technical requirement changed unexpectedly. How did you adapt?",
        # HR 3: Career Alignment & Motivation
        f"Why are you specifically interested in the {target_role} position, and where do you see your technical skills evolving over the next two years?",
    ]

    return tech_qs + hr_qs


def generate_mock_interview(
    target_role: str,
    gap_skills: list[str],
    weak_skills: list[str],
    projects: list[dict],
) -> dict:
    """
    Generate an 8-question mock interview session (5 Technical + 3 HR)
    personalized with the student's project, skill gaps, weak points, and target role.
    """
    # Extract project details
    proj_obj = projects[0] if (projects and isinstance(projects[0], dict)) else {}
    proj_name = str(proj_obj.get("name") or proj_obj.get("title") or "").strip()
    proj_tech = proj_obj.get("tech") or proj_obj.get("technologies") or []
    if isinstance(proj_tech, str):
        proj_tech = [proj_tech]

    # Combined focus skills
    focus_skills = list(dict.fromkeys(weak_skills + gap_skills))

    prompt = f"""
    Act as a senior technical hiring manager for the job role: "{target_role}".
    Generate EXACTLY 8 interview questions (5 Technical + 3 HR/Behavioral) personalized for this engineering candidate.

    Candidate Profile:
    - Target Role: {target_role}
    - Key Technical Skill Gaps / Weak Skills to test: {', '.join(focus_skills[:5]) if focus_skills else 'Data Structures, REST APIs, System Design'}
    - Key Resume Project: Name: "{proj_name or 'Engineering Project'}", Tech Stack: {', '.join(proj_tech) if proj_tech else 'General Tech'}

    Requirements:
    - Questions 1 to 5 MUST be TECHNICAL questions.
      - At least 1 technical question MUST explicitly reference their resume project "{proj_name or 'Engineering Project'}".
      - At least 2 technical questions MUST test their skill gaps ({', '.join(focus_skills[:3]) if focus_skills else 'core skills'}).
    - Questions 6 to 8 MUST be HR / BEHAVIORAL questions assessing teamwork, problem solving under pressure, and career goals for {target_role}.

    Return EXACTLY this JSON structure with NO markdown formatting:
    {{
      "target_role": "{target_role}",
      "questions": [
        "Tech Q1...",
        "Tech Q2 (referencing project {proj_name or 'Engineering Project'})...",
        "Tech Q3...",
        "Tech Q4...",
        "Tech Q5...",
        "HR Q1...",
        "HR Q2...",
        "HR Q3..."
      ]
    }}
    """

    ai_response = ask_llm_json(prompt, retries=2)

    if isinstance(ai_response, dict) and "questions" in ai_response:
        clean_qs = _validate_interview_output(ai_response, target_role)
        if len(clean_qs) == 8:
            return {"target_role": target_role, "questions": clean_qs}

    # Safe deterministic fallback if LLM response is invalid or missing questions
    fallback_qs = _deterministic_interview_fallback(
        target_role=target_role,
        gap_skills=gap_skills,
        weak_skills=weak_skills,
        project_name=proj_name,
        project_tech=proj_tech,
    )
    return {"target_role": target_role, "questions": fallback_qs}
