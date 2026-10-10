from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any

from app.services.llm import ask_llm_json
from app.services.question_support import (
    QuestionGenerationUnavailable,
    normalized_choice_text,
    validate_mcq_explanation,
    validate_single_answer_mcq,
)

logger = logging.getLogger(__name__)

TECHNICAL_QUESTION_COUNT = 5
HR_QUESTION_COUNT = 3


def _clean_text(value: Any, limit: int = 1000) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _validate_technical_question(question: Any, index: int) -> dict | None:
    if not isinstance(question, dict):
        return None
    prompt = _clean_text(question.get("question") or question.get("prompt"), 1500)
    concept = _clean_text(question.get("skill") or question.get("concept"), 160)
    explanation = _clean_text(question.get("explanation"), 1600)
    options = question.get("options")
    correct_answer = _clean_text(question.get("correct_answer"), 20)
    if not prompt or not concept or not explanation or not isinstance(options, list):
        return None

    clean_options = []
    for option in options:
        if not isinstance(option, dict):
            return None
        option_id = _clean_text(option.get("id"), 20)
        option_text = _clean_text(option.get("text"), 400)
        if not option_id or not option_text:
            return None
        clean_options.append({"id": option_id, "text": option_text})
    option_objects = [SimpleNamespace(**option) for option in clean_options]
    try:
        validate_single_answer_mcq(option_objects, correct_answer, "Interview MCQs")
        validate_mcq_explanation(
            option_objects, correct_answer, explanation, "interview MCQs"
        )
    except (ValueError, StopIteration):
        return None

    code = _clean_text(question.get("code"), 2400)
    return {
        "question_id": f"q{index + 1}",
        "type": "technical_mcq",
        "skill": concept,
        "question": prompt,
        "options": clean_options,
        "correct_answer": correct_answer,
        "explanation": explanation,
        "code": code or None,
    }


def _validate_interview_output(raw: Any) -> list[dict] | None:
    if not isinstance(raw, dict):
        return None
    technical = raw.get("technical_questions")
    hr = raw.get("hr_questions")
    if not isinstance(technical, list) or len(technical) != TECHNICAL_QUESTION_COUNT:
        return None
    if not isinstance(hr, list) or len(hr) != HR_QUESTION_COUNT:
        return None

    clean_technical = []
    for index, item in enumerate(technical):
        question = _validate_technical_question(item, index)
        if question is None:
            return None
        clean_technical.append(question)

    option_sets: list[set[str]] = []
    for item in clean_technical:
        normalized_options = {
            normalized_choice_text(option["text"]) for option in item["options"]
        }
        if any(len(normalized_options.intersection(previous)) >= 3 for previous in option_sets):
            return None
        option_sets.append(normalized_options)

    prompts = {normalized_choice_text(item["question"]) for item in clean_technical}
    for index, item in enumerate(hr):
        prompt = _clean_text(item.get("question") if isinstance(item, dict) else item, 1500)
        if not prompt or normalized_choice_text(prompt) in prompts:
            return None
        prompts.add(normalized_choice_text(prompt))
        clean_technical.append(
            {
                "question_id": f"q{TECHNICAL_QUESTION_COUNT + index + 1}",
                "type": "hr",
                "skill": None,
                "question": prompt,
                "options": [],
            }
        )

    return clean_technical


def generate_mock_interview(
    target_role: str,
    gap_skills: list[str],
    weak_skills: list[str],
    projects: list[dict],
    difficulty: str = "Intermediate",
    focus_area: str = "",
) -> dict:
    """Generate a validated five-MCQ, three-HR interview; use grounded templates on AI failure."""
    focus_skills = list(dict.fromkeys([*weak_skills, *gap_skills]))
    project = projects[0] if projects and isinstance(projects[0], dict) else {}
    project_name = _clean_text(project.get("name") or project.get("title"))
    project_tech = project.get("tech") or project.get("technologies") or []
    prompt = f"""
Create exactly five technical multiple-choice questions and three HR questions for a {difficulty}
interview for the role {json.dumps(target_role)}.
Focus area: {json.dumps(focus_area or "Use the candidate's verified skill gaps and weak skills")}.
Prioritized skills: {json.dumps(focus_skills[:8], ensure_ascii=True)}.
Resume project context: {json.dumps({"name": project_name, "technologies": project_tech}, ensure_ascii=True)}.

Technical question requirements:
- Test practical understanding relevant to the selected role and prioritized skills; include the project context
  in at least one scenario only when the project data supports it.
- Each technical item must have question, skill, exactly four distinct option objects with unique IDs and text,
  correct_answer (one option ID), explanation, and optional code.
- Exactly one option is correct. Each explanation must refer to the correct choice.
- Vary conceptual, application, debugging, and trade-off scenarios where relevant.
HR question requirements:
- Ask exactly three free-text questions about collaboration, adapting to change, and role motivation.
- Invite an honest academic, project, or personal example; do not presume or invent the candidate's experiences.
Return only JSON in this format:
{{
  "technical_questions": [
    {{
      "question": "Question text",
      "skill": "Relevant skill",
      "options": [
        {{"id": "a", "text": "Choice A"}},
        {{"id": "b", "text": "Choice B"}},
        {{"id": "c", "text": "Choice C"}},
        {{"id": "d", "text": "Choice D"}}
      ],
      "correct_answer": "a",
      "explanation": "Explain why choice A is correct.",
      "code": null
    }}
  ],
  "hr_questions": [
    {{"question": "Open-ended HR question"}}
  ]
}}
"""
    response = ask_llm_json(prompt, retries=2, max_tokens=3500)
    validated_questions = _validate_interview_output(response)
    if validated_questions is None:
        category = (
            "provider_unavailable"
            if isinstance(response, dict) and response.get("error")
            else "invalid_response_schema"
        )
        logger.warning(
            "Hybrid interview generation unavailable: stage=response_validation category=%s",
            category,
        )
        raise QuestionGenerationUnavailable(
            "A valid hybrid interview could not be generated."
        )

    return {
        "target_role": target_role,
        "difficulty": difficulty,
        "focus_area": focus_area,
        "questions": validated_questions,
        "content_source": "llm",
    }
