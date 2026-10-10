"""
Personalized 6-Week Learning Roadmap Generator for PlaceIQ (Phase 3.1)

Generates a structured, 6-week learning roadmap from the student's VTU-aware skill-gap analysis.
- Prioritizes higher-weight missing skills and prerequisites.
- Distinguishes "revise and add to resume" skills from "learn from scratch" skills.
- Provides actionable tasks, recommended resources, and explanations.
- Employs strict output validation and deterministic fallback for guaranteed reliability.
"""
from app.services.llm import ask_llm_json
from app.services.gap_analyzer import get_role_requirements


# ── Resources dictionary for canonical skills ────────────────────────────────
_CANONICAL_RESOURCES: dict[str, list[str]] = {
    "Python": ["Official Python Documentation", "Real Python Tutorials"],
    "Java": ["Oracle Java Documentation", "Baeldung Java Guides"],
    "C": ["C Programming Reference", "Programiz C Tutorials"],
    "C++": ["LearnCpp Guides", "C++ Reference Documentation"],
    "JavaScript": ["MDN Web Docs", "JavaScript.info Guides"],
    "TypeScript": ["Official TypeScript Handbook", "Total TypeScript"],
    "React": ["Official React Documentation", "freeCodeCamp React Guides"],
    "Node.js": ["Official Node.js Documentation", "Express.js Guides"],
    "SQL": ["SQLZoo Interactive Tutorials", "Mode Analytics SQL Guide"],
    "Database Design": ["Database Systems Handbook", "Lucidchart Database Design Guide"],
    "Data Structures": ["GeeksforGeeks Data Structures", "LeetCode Practice"],
    "Algorithms": ["CP-Algorithms Guide", "VisuAlgo Visualizations"],
    "Machine Learning": ["Scikit-Learn User Guide", "Coursera Machine Learning Specialization"],
    "Deep Learning": ["PyTorch Official Tutorials", "DeepLearning.AI Courses"],
    "AWS": ["AWS Getting Started Guides", "AWS Training & Certification"],
    "Cloud": ["Google Cloud Training", "AWS Free Tier Labs"],
    "Docker": ["Docker Official Documentation", "Docker Curriculum"],
    "Kubernetes": ["Kubernetes Official Tutorials", "Interactive Kubernetes Labs"],
    "DevOps": ["Roadmap.sh DevOps Guide", "GitLab CI/CD Documentation"],
    "Git": ["Git Official Documentation", "Learn Git Branching"],
    "Cybersecurity": ["Cybrary Courses", "OWASP Security Guides"],
    "Embedded Systems": ["Embedded.com Guides", "ARM Architecture Reference"],
    "Microcontrollers": ["Electronics Tutorials", "STMicroelectronics MCU Guides"],
    "VHDL": ["Nandland VHDL Tutorials", "VHDLwhiz Guides"],
    "Verilog": ["ASIC World Verilog Guide", "HDLBits Practice Labs"],
    "VLSI": ["All About Circuits VLSI Guide", "CMOSedu Tutorials"],
    "REST APIs": ["REST API Design Handbook", "Postman Learning Center"],
    "HTML": ["MDN Web Docs (HTML)", "W3Schools HTML Guide"],
    "CSS": ["CSS-Tricks Guides", "web.dev CSS Course"],
    "Agile": ["Scrum.org Guides", "Atlassian Agile Coach"],
    "Operating Systems": ["Operating System Concepts Textbook", "OSTEP Textbook"],
    "Computer Networks": ["Computer Networking: Top-Down Approach", "Wireshark Network Guides"],
}


# ── Helper functions ──────────────────────────────────────────────────────────

def _get_resources(skill: str) -> list[str]:
    """Return recommended online learning resources for a skill."""
    if skill in _CANONICAL_RESOURCES:
        return _CANONICAL_RESOURCES[skill]
    for key, res in _CANONICAL_RESOURCES.items():
        if key.lower() in skill.lower() or skill.lower() in key.lower():
            return res
    return ["documentation & online tutorials", "geeksforgeeks.org"]


def get_skill_resources(skill: str) -> list[str]:
    """Return the existing resource recommendations for use by other services."""
    return _get_resources(skill)


def _extract_skill_lists(gap_data: dict, target_role: str) -> tuple[list[dict], list[dict]]:
    """
    Extract and prioritize:
    1. Syllabus skills to revise ("revise and add to resume")
    2. Missing skills to learn ("learn from scratch")

    Sorted by role requirement weights descending (3=high, 2=med, 1=low).
    """
    weights = get_role_requirements(target_role)

    # 1. Syllabus revise skills
    revise_skills = []
    for item in gap_data.get("covered_by_syllabus", []):
        if item.get("status") == "revise and add to resume":
            sk = item.get("skill")
            w = weights.get(sk, 1)
            revise_skills.append({"skill": sk, "weight": w, "type": "revise"})

    # Sort revise skills by weight descending
    revise_skills.sort(key=lambda x: x["weight"], reverse=True)

    # 2. Missing skills to learn from scratch
    missing_skills = []
    for item in gap_data.get("missing", []):
        sk = item.get("skill")
        w = weights.get(sk, 1)
        missing_skills.append({"skill": sk, "weight": w, "type": "learn"})

    # Sort missing skills by weight descending
    missing_skills.sort(key=lambda x: x["weight"], reverse=True)

    return revise_skills, missing_skills


def _validate_roadmap_output(raw) -> dict:
    """
    Validate and sanitize the LLM roadmap output.
    Handles raw output whether it is a dict ({"weeks": [...]}) or a list ([{"week": 1, ...}]).
    Guarantees a clean dict with a 'weeks' list of exactly 6 week objects,
    where each week has 'week', 'theme', and 'tasks' (each task with 'task' and 'completed').
    """
    if isinstance(raw, list):
        raw_weeks = raw
    elif isinstance(raw, dict):
        raw_weeks = raw.get("weeks") or raw.get("roadmap") or raw.get("weeks_plan") or raw.get("plan") or []
        if not isinstance(raw_weeks, list):
            raw_weeks = []
    else:
        raw_weeks = []

    validated_weeks = []

    for i in range(1, 7):
        # Find matching week dict or create fallback
        w_dict = None
        for w in raw_weeks:
            if isinstance(w, dict) and w.get("week") == i:
                w_dict = w
                break

        if not w_dict and i - 1 < len(raw_weeks) and isinstance(raw_weeks[i - 1], dict):
            w_dict = raw_weeks[i - 1]

        theme = str(w_dict.get("theme") if w_dict else f"Week {i}: Skill Development & Practice").strip()
        if not theme:
            theme = f"Week {i}: Skill Development & Practice"

        raw_tasks = w_dict.get("tasks") if w_dict else []
        if not isinstance(raw_tasks, list):
            raw_tasks = []

        validated_tasks = []
        for t in raw_tasks:
            if isinstance(t, str) and t.strip():
                desc = t.strip()
                comp = False
            elif isinstance(t, dict):
                desc = str(t.get("task") or t.get("description") or t.get("name") or "").strip()
                comp = bool(t.get("completed", False))
            else:
                desc = ""

            if desc:
                # Preserve the supplied task text exactly; only fallback-generated tasks
                # should receive structured type tags in the deterministic generator.
                validated_tasks.append({"task": desc, "completed": comp})

        # Ensure at least 2 tasks per week
        if len(validated_tasks) == 0:
            validated_tasks = [
                {"task": f"[STUDY] Review core concepts and prerequisites for Week {i}", "completed": False},
                {"task": f"[PRACTICE] Hands-on coding exercises and project application for Week {i}", "completed": False},
            ]
        elif len(validated_tasks) == 1:
            validated_tasks.append(
                {"task": f"[PRACTICE] Hands-on coding exercises and technical practice for Week {i}", "completed": False}
            )

        validated_weeks.append({
            "week": i,
            "theme": theme,
            "tasks": validated_tasks,
        })

    return {"weeks": validated_weeks}


def _deterministic_roadmap_fallback(gap_data: dict, target_role: str) -> dict:
    """
    Generate a deterministic 6-week roadmap directly from gap analysis data
    if the LLM is unavailable or fails.
    """
    revise_skills, missing_skills = _extract_skill_lists(gap_data, target_role)

    all_revise_names = [s["skill"] for s in revise_skills]
    all_missing_names = [s["skill"] for s in missing_skills]

    # Distribute across 6 weeks
    # Week 1: Prerequisites & Syllabus Revision
    w1_skills = all_revise_names[:2] if all_revise_names else ["Foundational Engineering"]
    w1_tasks = []
    for s in w1_skills:
        res = ", ".join(_get_resources(s))
        w1_tasks.append({
            "task": f"[REVISE] {s} - Re-read VTU notes, refresh core concepts, and add to resume. (Resources: {res})",
            "completed": False,
        })

    # Week 2: Advanced Syllabus Revision & Practice
    w2_skills = all_revise_names[2:] if len(all_revise_names) > 2 else (all_revise_names or ["Core Problem Solving"])
    w2_tasks = []
    for s in w2_skills:
        res = ", ".join(_get_resources(s))
        w2_tasks.append({
            "task": f"[REVISE & PRACTICE] {s} - Solve 5 practice problems and document projects on resume. (Resources: {res})",
            "completed": False,
        })

    # Weeks 3-5: Learn Missing Skills from Scratch
    chunk_size = max(1, (len(all_missing_names) + 2) // 3) if all_missing_names else 1
    w3_missing = all_missing_names[:chunk_size] if all_missing_names else ["Core Role Architecture"]
    w4_missing = all_missing_names[chunk_size:2*chunk_size] if len(all_missing_names) > chunk_size else [f"{target_role} Fundamentals"]
    w5_missing = all_missing_names[2*chunk_size:] if len(all_missing_names) > 2*chunk_size else ["Advanced Industry Tools"]

    w3_tasks = [
        {
            "task": f"[LEARN] {s} - Master fundamental concepts and build mini-exercises. (Explanation: Essential core skill for {target_role}. | Resources: {', '.join(_get_resources(s))})",
            "completed": False,
        }
        for s in w3_missing
    ]

    w4_tasks = [
        {
            "task": f"[LEARN] {s} - Deep dive into intermediate topics and framework integration. (Explanation: High-priority placement skill. | Resources: {', '.join(_get_resources(s))})",
            "completed": False,
        }
        for s in w4_missing
    ]

    w5_tasks = [
        {
            "task": f"[LEARN] {s} - Advanced implementations, performance optimization, and testing. (Resources: {', '.join(_get_resources(s))})",
            "completed": False,
        }
        for s in w5_missing
    ]

    # Ensure at least 2 tasks per week across all weeks
    for w_tasks, label in [(w1_tasks, "Foundations"), (w2_tasks, "Revision"), (w3_tasks, "Core Concepts"), (w4_tasks, "Intermediate Skills"), (w5_tasks, "Advanced Practice")]:
        if len(w_tasks) == 0:
            w_tasks.append({"task": f"[STUDY] Review {label} and core concepts for {target_role}.", "completed": False})
            w_tasks.append({"task": f"[PRACTICE] Hands-on coding exercises and project application for {target_role}.", "completed": False})
        elif len(w_tasks) == 1:
            w_tasks.append({"task": f"[PRACTICE] Hands-on coding exercises and project application for {label} in {target_role}.", "completed": False})

    # Week 6: Portfolio Project & Placement Preparation
    w6_tasks = [
        {
            "task": f"[PROJECT & RESUME] Build a comprehensive capstone project integrating {', '.join((all_missing_names + all_revise_names)[:3]) or target_role} and push to GitHub.",
            "completed": False,
        },
        {
            "task": f"[MOCK PREP] Update resume with newly mastered skills and practice top 20 technical interview questions for {target_role}.",
            "completed": False,
        },
    ]

    return {
        "weeks": [
            {"week": 1, "theme": "Week 1: Foundations & Syllabus Revision", "tasks": w1_tasks},
            {"week": 2, "theme": "Week 2: Advanced Revision & Resume Alignment", "tasks": w2_tasks},
            {"week": 3, "theme": f"Week 3: Core {target_role} Skills (Priority High)", "tasks": w3_tasks},
            {"week": 4, "theme": f"Week 4: Intermediate {target_role} Tools & Frameworks", "tasks": w4_tasks},
            {"week": 5, "theme": f"Week 5: Advanced Skill Integration & Optimization", "tasks": w5_tasks},
            {"week": 6, "theme": "Week 6: Capstone Project & Placement Interview Prep", "tasks": w6_tasks},
        ]
    }


# ── Main API ──────────────────────────────────────────────────────────────────

def generate_personalized_roadmap(gap_data: dict, target_role: str) -> dict:
    """
    Generate a 6-week personalized learning roadmap from the VTU skill gap data.

    Prioritizes:
    1. Syllabus skills to revise ("revise and add to resume") in Weeks 1-2.
    2. Missing skills to learn from scratch in Weeks 3-5, sorted by weight.
    3. Capstone project and interview readiness in Week 6.
    """
    revise_skills, missing_skills = _extract_skill_lists(gap_data, target_role)

    revise_names = [s["skill"] for s in revise_skills]
    missing_names = [f"{s['skill']} (Weight {s['weight']}/3)" for s in missing_skills]

    prompt = f"""
    Create a highly structured 6-week personalized technical study roadmap for a VTU engineering student aiming for the job role: "{target_role}".

    Student Skill Profile:
    - Syllabus Skills to REVISE (studied in college, need refresh & adding to resume): {', '.join(revise_names) if revise_names else 'None'}
    - Missing Skills to LEARN FROM SCRATCH (ranked by priority weight 1-3): {', '.join(missing_names) if missing_names else 'Advanced System Design'}

    Weekly Structure Instructions:
    - Week 1 & 2: Focus on REVISING syllabus skills ({', '.join(revise_names[:4]) if revise_names else 'Foundational prerequisites'}). Distinguish these clearly as REVISE tasks.
    - Week 3, 4 & 5: Focus on LEARNING missing skills from scratch, prioritizing higher-weight skills first. Distinguish these as LEARN tasks.
    - Week 6: Focus on a hands-on Capstone Portfolio Project integrating the new skills, resume updating, and mock interview preparation.

    Task Formatting Requirement:
    Each task MUST be an object with key "task" (string) and "completed" (false).
    Format the "task" string to include:
    1. Type tag: [REVISE] or [LEARN] or [PROJECT]
    2. Skill name & specific study action
    3. Short explanation of why this skill matters for {target_role}
    4. Recommended learning resources/tutorials

    Return EXACTLY this JSON structure with NO extra markdown formatting:
    {{
      "weeks": [
        {{
          "week": 1,
          "theme": "Week 1: Foundations & Syllabus Revision",
          "tasks": [
            {{
              "task": "[REVISE] Data Structures - Review arrays & linked lists notes from sem 3 and add mini-project to resume. (Explanation: Core foundation for technical interviews | Resources: geeksforgeeks.org, leetcode.com)",
              "completed": false
            }}
          ]
        }}
      ]
    }}
    """

    ai_response = ask_llm_json(prompt, retries=2)

    if isinstance(ai_response, dict) and "error" in ai_response:
        return _deterministic_roadmap_fallback(gap_data, target_role)

    validated = _validate_roadmap_output(ai_response)
    if not validated.get("weeks"):
        return _deterministic_roadmap_fallback(gap_data, target_role)

    return validated
