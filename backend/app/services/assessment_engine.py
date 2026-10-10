from __future__ import annotations

import json
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, model_validator

from app.services.llm import ask_llm_json
from app.services.question_support import (
    QuestionGenerationUnavailable,
    build_lesson_grounded_mcqs,
    validate_mcq_explanation,
    validate_question_specific_mcqs,
    validate_single_answer_mcq,
)


class AssessmentOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=1, max_length=400)


class AssessmentQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=32)
    concept: str = Field(min_length=2, max_length=160)
    type: Literal["mcq", "code_output"]
    prompt: str = Field(min_length=10, max_length=1600)
    options: list[AssessmentOption] = Field(default_factory=list, max_length=5)
    code: Optional[str] = Field(default=None, max_length=2400)
    language: Optional[str] = Field(default=None, max_length=40)
    correct_answer: str = Field(min_length=1, max_length=1200)
    explanation: str = Field(min_length=20, max_length=1600)

    @model_validator(mode="after")
    def validate_shape(self, info: ValidationInfo) -> "AssessmentQuestion":
        if self.type == "mcq":
            validate_single_answer_mcq(
                self.options,
                self.correct_answer,
                "Assessment MCQs",
                allow_legacy_shape=bool(info.context and info.context.get("allow_legacy_mcq")),
            )
            if not (info.context and info.context.get("allow_legacy_mcq")):
                validate_mcq_explanation(
                    self.options,
                    self.correct_answer,
                    self.explanation,
                    "assessment MCQ",
                )
        elif self.options or not self.code:
            raise ValueError("Code-output questions require code and cannot include options.")
        return self


class AssessmentQuestionSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[AssessmentQuestion] = Field(min_length=3, max_length=8)

    @model_validator(mode="after")
    def validate_ids(self) -> "AssessmentQuestionSet":
        identifiers = [question.question_id for question in self.questions]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Assessment question IDs must be unique.")
        if any(question.type != "mcq" for question in self.questions):
            raise ValueError("New assessments may contain only multiple-choice questions.")
        validate_question_specific_mcqs(self.questions)
        return self


class AssessmentAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=32)
    answer: str = Field(min_length=1, max_length=6000)

    @model_validator(mode="after")
    def answer_must_not_be_blank(self) -> "AssessmentAnswer":
        if not self.answer.strip():
            raise ValueError("Assessment answers cannot be blank.")
        return self


class AssessmentSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[AssessmentAnswer] = Field(min_length=3, max_length=8)

    @model_validator(mode="after")
    def validate_unique_questions(self) -> "AssessmentSubmission":
        identifiers = [answer.question_id for answer in self.answers]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Submit only one answer per assessment question.")
        return self


def _fallback_questions(skill_id: str, lesson: dict) -> AssessmentQuestionSet:
    title = lesson.get("title") or skill_id
    grounded_questions = build_lesson_grounded_mcqs(
        lesson,
        title,
        count=3,
        max_option_length=400,
    )
    questions: list[dict] = []
    for item in grounded_questions:
        questions.append(
            {
                "question_id": f"q{len(questions) + 1}",
                "concept": item["answer_text"][:160],
                "type": "mcq",
                "prompt": item["prompt"],
                "options": item["options"],
                "code": None,
                "language": None,
                "correct_answer": item["correct_answer"],
                "explanation": item["explanation"],
            }
        )

    if len(questions) < 3:
        raise QuestionGenerationUnavailable(
            "The available lesson content does not support enough trustworthy multiple-choice assessment questions. "
            "Review the lesson and try again."
        )
    return AssessmentQuestionSet.model_validate({"questions": questions})


def _assessment_prompt(skill_id: str, lesson: dict, context: dict) -> str:
    return f"""
Create an objective assessment for the specified PlaceIQ lesson and canonical skill.
Skill: {json.dumps(skill_id)}
Available student context: {json.dumps(context, ensure_ascii=True)}
Lesson (the only permitted subject matter): {json.dumps(lesson, ensure_ascii=True)}

Return exactly 3 to 6 multiple-choice questions. Questions must assess lesson concepts, not facts absent
from the lesson. Include a concise
concept label for each question so the result can identify concepts that went well and concepts to review.
Every MCQ must contain exactly four distinct, plausible options with unique IDs and text, and exactly one
correct answer whose ID matches correct_answer. Every question must have question_id, concept, type ("mcq"),
prompt, options, optional code and language, correct_answer (one option ID), and an explanation tied to
the correct choice. Use code snippets only inside an MCQ when the lesson supports a code-output or debugging
question. Do not include code-output or free-response question types.
Use IDs q1, q2, ...; return only JSON:
{{
  "questions": [
    {{
      "question_id": "q1",
      "concept": "Concept label",
      "type": "mcq",
      "prompt": "Question text",
      "options": [
        {{"id": "a", "text": "Choice A"}},
        {{"id": "b", "text": "Choice B"}},
        {{"id": "c", "text": "Choice C"}},
        {{"id": "d", "text": "Choice D"}}
      ],
      "code": null,
      "language": null,
      "correct_answer": "a",
      "explanation": "Explain the correct answer using the lesson."
    }}
  ]
}}
"""


def generate_assessment(skill_id: str, lesson: dict, context: dict) -> tuple[AssessmentQuestionSet, str]:
    response = ask_llm_json(_assessment_prompt(skill_id, lesson, context), retries=2)
    if isinstance(response, dict) and "error" not in response:
        try:
            questions = response.get("questions")
            if isinstance(questions, list):
                for index, question in enumerate(questions, start=1):
                    if isinstance(question, dict):
                        question["question_id"] = f"q{index}"
            return AssessmentQuestionSet.model_validate(response), "llm"
        except (ValidationError, TypeError):
            pass
    return _fallback_questions(skill_id, lesson), "fallback"


def _normalized_output(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.strip().splitlines()).strip()


def score_assessment(question_data: list[dict], submitted_answers: dict[str, str]) -> dict:
    questions = [
        AssessmentQuestion.model_validate(item, context={"allow_legacy_mcq": True})
        for item in question_data
    ]
    if set(submitted_answers) != {question.question_id for question in questions}:
        raise ValueError("Submit exactly one answer for every assessment question.")

    reviewed_questions = []
    concept_results: dict[str, dict[str, int]] = {}
    correct_count = 0
    for question in questions:
        answer = submitted_answers[question.question_id]
        if question.type == "mcq":
            if answer not in {option.id for option in question.options}:
                raise ValueError(f"Choose an available option for {question.question_id}.")
            submitted_display = next(option.text for option in question.options if option.id == answer)
            correct_answer = next(option.text for option in question.options if option.id == question.correct_answer)
            is_correct = answer == question.correct_answer
        else:
            submitted_display = answer
            correct_answer = question.correct_answer
            is_correct = _normalized_output(answer) == _normalized_output(correct_answer)

        if is_correct:
            correct_count += 1
        concept_result = concept_results.setdefault(question.concept, {"questions": 0, "correct": 0})
        concept_result["questions"] += 1
        concept_result["correct"] += int(is_correct)
        reviewed_questions.append(
            {
                "question_id": question.question_id,
                "concept": question.concept,
                "type": question.type,
                "prompt": question.prompt,
                "answer": submitted_display,
                "correct_answer": correct_answer,
                "is_correct": is_correct,
                "explanation": question.explanation,
            }
        )

    total = len(questions)
    score_pct = round(correct_count / total * 100, 1)
    concept_summary = [
        {
            "concept": concept,
            "correct": counts["correct"],
            "total": counts["questions"],
            "status": "strength" if counts["correct"] == counts["questions"] else "review",
        }
        for concept, counts in concept_results.items()
    ]
    return {
        "correct": correct_count,
        "total": total,
        "score_pct": score_pct,
        "questions": reviewed_questions,
        "concepts": concept_summary,
        "notice": "This is the result of this assessment attempt, not a skill-mastery score or placement-readiness measure.",
    }
