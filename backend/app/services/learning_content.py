from __future__ import annotations

import json
import logging
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.gap_analyzer import syllabus_db
from app.services.llm import ask_llm_json
from app.services.roadmap_generator import get_skill_resources
from app.services.skill_extractor import normalize_skill, skills_master

logger = logging.getLogger(__name__)


class LessonContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_id: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=3, max_length=120)
    introduction: str = Field(min_length=20, max_length=1200)
    explanation: str = Field(min_length=30, max_length=2400)
    example: str = Field(min_length=10, max_length=1200)
    code_example: Optional[str] = Field(default=None, max_length=1600)
    code_language: Optional[str] = Field(default=None, max_length=40)
    example_explanation: str = Field(min_length=20, max_length=1200)
    real_world_applications: list[str] = Field(min_length=1, max_length=4)
    common_mistakes: list[str] = Field(min_length=1, max_length=4)
    key_takeaways: list[str] = Field(min_length=1, max_length=4)
    quick_recap: str = Field(min_length=15, max_length=600)


class LearningContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    introduction: str = Field(min_length=20, max_length=1200)
    learning_objectives: list[str] = Field(min_length=2, max_length=6)
    lessons: list[LessonContent] = Field(min_length=2, max_length=5)
    quick_recap: str = Field(min_length=15, max_length=800)


def get_canonical_skill(skill_id: str) -> Optional[str]:
    """Resolve only exact canonical names or exact aliases; never fuzzy-match IDs."""
    cleaned = " ".join(skill_id.strip().split()).casefold()
    for canonical in skills_master:
        if canonical.casefold() == cleaned:
            return canonical

    for canonical, aliases in skills_master.items():
        if any(alias.strip().casefold() == cleaned for alias in aliases):
            return canonical
    return None


def map_roadmap_task_skill(task_text: object) -> Optional[str]:
    """Map an explicit canonical skill heading, optionally followed by a generic qualifier."""
    if not isinstance(task_text, str) or not task_text.strip():
        return None

    heading = task_text.strip().split(" - ", 1)[0]
    heading = re.sub(r"^\s*\[[^\]]+\]\s*", "", heading)
    heading = re.sub(r"\s*\(weight\s+\d+\s*/\s*\d+\)\s*$", "", heading, flags=re.IGNORECASE)
    exact_match = get_canonical_skill(heading)
    if exact_match:
        return exact_match

    qualifiers = {"advanced", "basics", "beginner", "concepts", "essentials", "fundamentals", "introduction", "intro", "overview"}
    normalized_heading = " ".join(heading.split())
    for canonical in sorted(skills_master, key=len, reverse=True):
        if not normalized_heading.casefold().startswith(canonical.casefold()):
            continue
        remainder = normalized_heading[len(canonical):].strip()
        if remainder and re.fullmatch(r"[A-Za-z ]+", remainder):
            words = remainder.casefold().split()
            if words and all(word in qualifiers for word in words):
                return canonical
    return None


def _fallback_content(skill_id: str) -> LearningContent:
    resources = ", ".join(get_skill_resources(skill_id))
    lessons = [
        {
            "lesson_id": "lesson-1",
            "title": f"Getting oriented with {skill_id}",
            "introduction": f"Start by understanding what {skill_id} is for and the kind of problems it helps solve.",
            "explanation": (
                f"Think of {skill_id} as a set of ideas and tools for solving a particular class of problems. "
                "Before memorizing details, identify the input you start with, the result you need, and the "
                "main steps that connect them. Use the recommended references to learn the terminology specific "
                f"to {skill_id}."
            ),
            "example": f"A beginner studying {skill_id} can choose one small problem, describe its input and expected output, then identify which {skill_id} concepts are needed.",
            "code_example": None,
            "code_language": None,
            "example_explanation": "Keeping the problem small makes it easier to connect a new term to a concrete result and check whether the idea was understood.",
            "real_world_applications": [f"Applying {skill_id} to solve a focused task in a software or engineering project."],
            "common_mistakes": ["Trying to learn every advanced feature before understanding the basic purpose."],
            "key_takeaways": [f"Understand the problem area addressed by {skill_id}.", "Begin with a small, observable example."],
            "quick_recap": f"First identify what {skill_id} helps you do, then study one small example from the recommended references.",
        },
        {
            "lesson_id": "lesson-2",
            "title": f"Build a learning path for {skill_id}",
            "introduction": "Turn a broad topic into a sequence of manageable concepts.",
            "explanation": (
                f"Use the roadmap task and the recommended references ({resources}) to identify the first "
                f"foundational concept in {skill_id}. Learn its vocabulary, follow a worked example, and then "
                "summarize the steps in your own words. Move to the next concept only after you can explain the "
                "current one clearly."
            ),
            "example": f"For a {skill_id} topic, write down one key term, explain it in plain language, and connect it to an example from a trusted reference.",
            "code_example": None,
            "code_language": None,
            "example_explanation": "This approach keeps the learning focused and helps distinguish a real understanding from simply recognizing terminology.",
            "real_world_applications": ["Breaking a larger project requirement into concepts that can be learned and reviewed independently."],
            "common_mistakes": ["Relying on a single explanation without checking a trusted reference."],
            "key_takeaways": ["Follow prerequisites in order.", "Use examples and references to check your understanding."],
            "quick_recap": "Learn one foundational concept at a time, explain it yourself, and verify it against a reliable source.",
        },
        {
            "lesson_id": "lesson-3",
            "title": f"Connect {skill_id} to projects",
            "introduction": "Relate concepts to the work you may encounter in an engineering project.",
            "explanation": (
                f"Once the foundations of {skill_id} are clear, look for a small, low-risk way to apply them in a "
                "project. Record the goal, the concept used, and the result. Compare your approach with the "
                "reference material and note any assumptions or limitations."
            ),
            "example": f"Choose a small project feature where {skill_id} is relevant, describe the intended result, and document which concept from your lesson supports it.",
            "code_example": None,
            "code_language": None,
            "example_explanation": "A concrete project connection makes abstract ideas easier to recall and gives you a specific example to revisit.",
            "real_world_applications": [f"Using {skill_id} as one part of a larger application or engineering system."],
            "common_mistakes": ["Copying a project example without understanding its assumptions or limitations."],
            "key_takeaways": ["Connect concepts to a specific project goal.", "Document what you tried and what you learned."],
            "quick_recap": f"Apply one {skill_id} concept to a small project feature and explain why it fits.",
        },
    ]
    code_examples = {
        "Python": ("python", "scores = [72, 88, 91]\naverage = sum(scores) / len(scores)\nprint(average)"),
        "JavaScript": ("javascript", "const scores = [72, 88, 91];\nconst average = scores.reduce((sum, score) => sum + score, 0) / scores.length;\nconsole.log(average);"),
        "TypeScript": ("typescript", "const scores: number[] = [72, 88, 91];\nconst average: number = scores.reduce((sum, score) => sum + score, 0) / scores.length;\nconsole.log(average);"),
        "SQL": ("sql", "SELECT department, COUNT(*) AS employee_count\nFROM employees\nGROUP BY department;"),
        "Data Structures": ("python", "stack = []\nstack.append('first')\nstack.append('second')\nlatest = stack.pop()"),
        "Algorithms": ("python", "def contains(values, target):\n    for value in values:\n        if value == target:\n            return True\n    return False"),
        "React": ("jsx", "function Welcome({ name }) {\n  return <h1>Hello, {name}!</h1>;\n}"),
        "HTML": ("html", "<main>\n  <h1>Course overview</h1>\n  <p>Organized learning content.</p>\n</main>"),
        "CSS": ("css", ".lesson-card {\n  padding: 1rem;\n  border-radius: 0.75rem;\n}"),
        "C": ("c", "int scores[] = {72, 88, 91};\nint count = sizeof(scores) / sizeof(scores[0]);\nint total = 0;\nfor (int i = 0; i < count; i++) total += scores[i];"),
        "C++": ("cpp", "std::vector<int> scores{72, 88, 91};\nint total = 0;\nfor (int score : scores) total += score;"),
        "Java": ("java", "int[] scores = {72, 88, 91};\nint total = 0;\nfor (int score : scores) total += score;\ndouble average = (double) total / scores.length;"),
        "REST APIs": ("python", "@app.get(\"/courses/{course_id}\")\ndef get_course(course_id: int):\n    return {\"course_id\": course_id}"),
    }
    if skill_id in code_examples:
        code_language, code_example = code_examples[skill_id]
        lessons[0]["code_language"] = code_language
        lessons[0]["code_example"] = code_example
        lessons[0]["example"] = f"Use this small {skill_id} example to inspect a basic input and the result it produces."
        lessons[0]["example_explanation"] = (
            f"The example uses {skill_id} to work with a small, visible input. Trace each step and compare the result "
            "with what you expect; then change one input and observe what changes."
        )
    return LearningContent.model_validate(
        {
            "introduction": (
                f"This structured starter guide introduces {skill_id} in small steps. "
                f"Use it alongside the recommended learning references: {resources}."
            ),
            "learning_objectives": [
                f"Explain the purpose of {skill_id} in beginner-friendly language.",
                f"Use a trusted reference to explore a foundational {skill_id} concept.",
                f"Describe one way {skill_id} can contribute to a small project.",
            ],
            "lessons": lessons,
            "quick_recap": f"Understand the purpose of {skill_id}, learn its concepts step by step, and connect one idea to a small project.",
        }
    )


def _build_prompt(skill_id: str, context: dict) -> str:
    return f"""
Create a beginner-friendly, structured learning guide for the canonical skill "{skill_id}".
Use only the supplied student context. Do not invent VTU subjects, student experience, or mastery claims.
Context (some fields may be null): {json.dumps(context, ensure_ascii=True)}

Return 3 lessons in a sensible learning order. Each lesson is a manageable concept and must contain:
title, introduction, explanation, a concrete example, optional code_example and code_language when code is suitable,
example_explanation, real_world_applications, common_mistakes, key_takeaways, and quick_recap.
Use accurate, beginner-friendly explanations. Use code only when it is appropriate for this skill.
Use roadmap context to emphasize revision or learning-from-scratch where present, without claiming lesson completion
proves mastery. Keep the top-level introduction, learning_objectives, and quick_recap relevant to the skill.
Return this JSON shape, with no additional fields:
{{
  "introduction": "A clear introduction to the skill.",
  "learning_objectives": ["Objective one", "Objective two"],
  "lessons": [
    {{
      "title": "Concept one",
      "introduction": "A short introduction.",
      "explanation": "A beginner-friendly explanation of at least a few sentences.",
      "example": "A concrete example.",
      "code_example": null,
      "code_language": null,
      "example_explanation": "Explain how the example demonstrates the concept.",
      "real_world_applications": ["A practical application."],
      "common_mistakes": ["A common beginner mistake."],
      "key_takeaways": ["A key point."],
      "quick_recap": "A short recap."
    }}
  ],
  "quick_recap": "A short overall recap."
}}
"""


def generate_learning_content(skill_id: str, context: dict) -> tuple[LearningContent, str]:
    response = ask_llm_json(_build_prompt(skill_id, context), retries=2)
    if isinstance(response, dict) and "error" not in response:
        try:
            raw_lessons = response.get("lessons")
            if isinstance(raw_lessons, list):
                for index, lesson in enumerate(raw_lessons, start=1):
                    if isinstance(lesson, dict):
                        lesson["lesson_id"] = f"lesson-{index}"
            return LearningContent.model_validate(response), "llm"
        except ValidationError as error:
            logger.warning(
                "Groq lesson response rejected by schema: stage=schema_validation "
                "category=invalid_response_schema operation=lesson_generation errors=%d",
                len(error.errors()),
                extra={
                    "groq_stage": "schema_validation",
                    "groq_category": "invalid_response_schema",
                    "groq_operation": "lesson_generation",
                    "groq_error_count": len(error.errors()),
                },
            )
    return _fallback_content(skill_id), "fallback"


def get_vtu_subjects(branch: Optional[str], semester: Optional[int], skill_id: str) -> list[str]:
    if not branch or semester is None:
        return []

    subjects = []
    for semester_number, entries in syllabus_db.get(branch, {}).items():
        if int(semester_number) > semester:
            continue
        for entry in entries:
            skills = entry.get("skills", [])
            if any(normalize_skill(item) == skill_id for item in skills):
                subjects.append(entry["subject"])
    return subjects
