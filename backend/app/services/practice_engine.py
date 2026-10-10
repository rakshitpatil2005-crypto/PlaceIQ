from __future__ import annotations

import json
import logging
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, model_validator

from app.services.llm import ask_llm_json
from app.services.question_support import (
    QuestionGenerationUnavailable,
    build_lesson_grounded_mcqs,
    validate_single_answer_mcq,
    validate_question_specific_mcqs,
)

logger = logging.getLogger(__name__)


class PracticeOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=300)


class PracticeQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=32)
    type: Literal["mcq", "code_output", "debugging", "coding", "short_answer"]
    prompt: str = Field(min_length=10, max_length=1500)
    options: list[PracticeOption] = Field(default_factory=list, max_length=5)
    code: Optional[str] = Field(default=None, max_length=2400)
    language: Optional[str] = Field(default=None, max_length=40)
    starter_code: Optional[str] = Field(default=None, max_length=1600)
    correct_answer: str = Field(min_length=1, max_length=1600)
    accepted_keywords: list[str] = Field(default_factory=list, max_length=12)
    explanation: str = Field(min_length=20, max_length=1600)
    reference_answer: str = Field(min_length=1, max_length=2400)

    @model_validator(mode="after")
    def validate_question_shape(self, info: ValidationInfo) -> "PracticeQuestion":
        if self.type == "mcq":
            validate_single_answer_mcq(
                self.options,
                self.correct_answer,
                "Practice MCQs",
                allow_legacy_shape=bool(info.context and info.context.get("allow_legacy_mcq")),
            )
        elif self.options:
            raise ValueError("Only MCQ questions may include answer options.")

        if self.type == "code_output" and not self.code:
            raise ValueError("Code-output questions must include code.")
        if self.type in {"debugging", "coding", "short_answer"} and not self.accepted_keywords:
            raise ValueError("Open-response questions need grading keywords.")
        return self


class PracticeSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[PracticeQuestion] = Field(min_length=2, max_length=6)

    @model_validator(mode="after")
    def validate_question_ids(self) -> "PracticeSet":
        question_ids = [question.question_id for question in self.questions]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("Question IDs must be unique.")
        if any(question.type != "mcq" for question in self.questions):
            raise ValueError("New practice sets may contain only multiple-choice questions.")
        validate_question_specific_mcqs(self.questions)
        return self


class PracticeEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_correct: bool
    feedback: str = Field(min_length=5, max_length=1200)
    explanation: str = Field(min_length=10, max_length=1600)


class AnswerGrade(BaseModel):
    is_correct: bool
    feedback: str
    explanation: str
    evaluation_source: Literal["deterministic", "llm"]


def _build_prompt(skill_id: str, lesson: dict, context: dict) -> str:
    return f"""
Create a multiple-choice practice set that tests understanding of this exact lesson for {skill_id}.
Student context (use only if relevant): {json.dumps(context, ensure_ascii=True)}
Lesson: {json.dumps(lesson, ensure_ascii=True)}

Create 3 to 5 distinct MCQs about the selected lesson concept. Vary the questions with conceptual,
application, comparison, code-output, or debugging scenarios when supported by the lesson. Do not force
code into non-programming topics or ask about facts absent from the lesson. Avoid trick questions.
Every question must have exactly four distinct, plausible answer options with unique IDs and exactly one
correct answer whose ID matches correct_answer. Explain why that specific option is correct using the lesson.
For every question provide: question_id, type ("mcq"), prompt, options (each with id and text), code (optional),
language (optional), starter_code (optional), correct_answer (one option ID), accepted_keywords (empty array),
explanation, and reference_answer (the correct option text).
Use question IDs q1, q2, etc. Return only JSON:
{{
  "questions": [
    {{
      "question_id": "q1",
      "type": "mcq",
      "prompt": "Question text",
      "options": [
        {{"id": "a", "text": "Option A"}},
        {{"id": "b", "text": "Option B"}},
        {{"id": "c", "text": "Option C"}},
        {{"id": "d", "text": "Option D"}}
      ],
      "code": null,
      "language": null,
      "starter_code": null,
      "correct_answer": "a",
      "accepted_keywords": [],
      "explanation": "Explain why the selected answer is correct.",
      "reference_answer": "The correct answer is Option A."
    }}
  ]
}}
"""


def _fallback_questions(skill_id: str, lesson: dict) -> PracticeSet:
    title = lesson.get("title") or skill_id
    grounded_questions = build_lesson_grounded_mcqs(
        lesson,
        title,
        count=4,
        max_option_length=300,
    )
    questions: list[dict] = []
    for item in grounded_questions:
        questions.append(
            {
                "question_id": f"q{len(questions) + 1}",
                "type": "mcq",
                "prompt": item["prompt"],
                "options": item["options"],
                "code": None,
                "language": None,
                "starter_code": None,
                "correct_answer": item["correct_answer"],
                "accepted_keywords": [],
                "explanation": item["explanation"],
                "reference_answer": item["answer_text"],
            }
        )

    if len(questions) < 2:
        raise QuestionGenerationUnavailable(
            "The available lesson content does not support enough trustworthy multiple-choice practice questions. "
            "Review the lesson and try again."
        )
    return PracticeSet.model_validate({"questions": questions})


def generate_practice_set(skill_id: str, lesson: dict, context: dict) -> tuple[PracticeSet, str]:
    response = ask_llm_json(_build_prompt(skill_id, lesson, context), retries=2)
    if isinstance(response, dict) and "error" not in response:
        try:
            questions = response.get("questions")
            if isinstance(questions, list):
                for index, question in enumerate(questions, start=1):
                    if isinstance(question, dict):
                        question["question_id"] = f"q{index}"
            return PracticeSet.model_validate(response), "llm"
        except (ValidationError, TypeError):
            logger.warning(
                "Practice question response rejected: stage=schema_validation category=invalid_response_schema",
                extra={
                    "groq_stage": "schema_validation",
                    "groq_category": "invalid_response_schema",
                },
            )
    else:
        error = response.get("error") if isinstance(response, dict) else None
        category = "malformed_json" if isinstance(error, str) and error.startswith("JSON decode failed") else "provider_failure"
        logger.warning(
            "Practice question generation unavailable: stage=provider_result category=%s",
            category,
            extra={
                "groq_stage": "provider_result",
                "groq_category": category,
            },
        )
    return _fallback_questions(skill_id, lesson), "fallback"


def _normalized_output(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.strip().splitlines()).strip()


def _deterministic_open_answer_grade(question: PracticeQuestion, answer: str) -> AnswerGrade:
    required = [keyword.casefold() for keyword in question.accepted_keywords]
    response = answer.casefold()
    matched = [keyword for keyword in required if keyword in response]
    correct = bool(required) and len(matched) >= max(1, (len(required) + 1) // 2)
    if correct:
        feedback = f"Your response includes key ideas: {', '.join(matched)}."
    else:
        missing = [keyword for keyword in required if keyword not in matched]
        feedback = f"Review these key ideas and try again: {', '.join(missing)}."
    return AnswerGrade(
        is_correct=correct,
        feedback=feedback,
        explanation=question.explanation,
        evaluation_source="deterministic",
    )


def grade_answer(question_data: dict, answer: str) -> AnswerGrade:
    question = PracticeQuestion.model_validate(question_data, context={"allow_legacy_mcq": True})
    if question.type == "mcq":
        selected = next((option for option in question.options if option.id == answer), None)
        if selected is None:
            raise ValueError("Select one of the available answer options.")
        correct = answer == question.correct_answer
        return AnswerGrade(
            is_correct=correct,
            feedback="Correct answer." if correct else "That is not the correct answer. Review the explanation and try again.",
            explanation=question.explanation,
            evaluation_source="deterministic",
        )

    if question.type == "code_output":
        correct = _normalized_output(answer) == _normalized_output(question.correct_answer)
        return AnswerGrade(
            is_correct=correct,
            feedback="Correct output." if correct else "The output does not match. Trace the code step by step and try again.",
            explanation=question.explanation,
            evaluation_source="deterministic",
        )

    prompt = f"""
Evaluate the learner's response to this practice question. Be constructive and grade only this response.
Question: {json.dumps(question.prompt, ensure_ascii=True)}
Reference solution: {json.dumps(question.reference_answer, ensure_ascii=True)}
Expected key ideas: {json.dumps(question.accepted_keywords, ensure_ascii=True)}
Learner response: {json.dumps(answer, ensure_ascii=True)}
Return only JSON with exactly: is_correct (boolean), feedback (short string), explanation (string).
Mark correct only if the response demonstrates the essential solution; do not require exact wording.
"""
    response = ask_llm_json(prompt, retries=2)
    if isinstance(response, dict) and "error" not in response:
        try:
            evaluation = PracticeEvaluation.model_validate(response)
            return AnswerGrade(
                is_correct=evaluation.is_correct,
                feedback=evaluation.feedback,
                explanation=evaluation.explanation,
                evaluation_source="llm",
            )
        except ValidationError:
            pass
    return _deterministic_open_answer_grade(question, answer)
