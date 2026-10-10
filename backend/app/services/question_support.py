from __future__ import annotations

import re
from collections.abc import Sequence
from itertools import combinations
from typing import Protocol


class QuestionGenerationUnavailable(RuntimeError):
    pass


class OptionLike(Protocol):
    id: str
    text: str


class PracticeQuestionLike(Protocol):
    prompt: str
    type: str
    options: Sequence[OptionLike]
    correct_answer: str
    explanation: str


def validate_mcq_explanation(
    options: Sequence[OptionLike],
    correct_answer: str,
    explanation: str,
    label: str,
) -> None:
    correct_option = next(option for option in options if option.id == correct_answer)
    if not meaningful_words(correct_option.text).intersection(meaningful_words(explanation)):
        raise ValueError(f"Each {label} explanation must refer to its correct option.")


def normalized_choice_text(text: str) -> str:
    return " ".join(text.casefold().split())


_STOP_WORDS = {
    "about", "after", "also", "because", "before", "being", "between", "could",
    "does", "from", "have", "into", "just", "less", "more", "most", "other",
    "over", "same", "should", "some", "such", "than", "that", "their", "them",
    "then", "there", "these", "they", "this", "through", "under", "using",
    "very", "what", "when", "where", "which", "while", "with", "would", "your",
    "and", "are", "for", "not", "the", "use", "was",
}


def meaningful_words(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE)
        if len(word) >= 4 and word not in _STOP_WORDS
    }


def validate_question_specific_mcqs(questions: Sequence[PracticeQuestionLike]) -> None:
    option_sets: list[frozenset[str]] = []
    prompts: set[str] = set()
    for question in questions:
        prompt = normalized_choice_text(question.prompt)
        if prompt in prompts:
            raise ValueError("Questions must use distinct prompts.")
        prompts.add(prompt)

        if question.type != "mcq":
            continue

        validate_mcq_explanation(
            question.options,
            question.correct_answer,
            question.explanation,
            "MCQ",
        )
        option_set = frozenset(normalized_choice_text(option.text) for option in question.options)
        if any(len(option_set.intersection(previous)) >= 3 for previous in option_sets):
            raise ValueError("MCQ choices must be specific to their question.")
        option_sets.append(option_set)


def validate_single_answer_mcq(
    options: Sequence[OptionLike],
    correct_answer: str,
    label: str,
    *,
    allow_legacy_shape: bool = False,
) -> None:
    if allow_legacy_shape:
        if len(options) < 2:
            raise ValueError(f"{label} need at least two answer options.")
    elif len(options) != 4:
        raise ValueError(f"{label} must have exactly four answer options.")

    option_ids = [option.id for option in options]
    if len(set(option_ids)) != len(option_ids):
        raise ValueError(f"{label} answer option IDs must be unique.")

    if correct_answer not in option_ids:
        raise ValueError(f"{label} answer must match one of its option IDs.")
    if allow_legacy_shape:
        return

    option_texts = [normalized_choice_text(option.text) for option in options]
    if len(set(option_texts)) != len(option_texts):
        raise ValueError(f"{label} answer option text must be unique.")


def lesson_statements(lesson: dict) -> list[tuple[str, str]]:
    sections = (
        ("lesson introduction", "introduction"),
        ("lesson explanation", "explanation"),
        ("example explanation", "example_explanation"),
        ("real-world application", "real_world_applications"),
        ("common mistake", "common_mistakes"),
        ("key takeaway", "key_takeaways"),
        ("quick recap", "quick_recap"),
    )
    statements: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for label, field in sections:
        value = lesson.get(field)
        values = value if isinstance(value, list) else [value]
        for item in values:
            if not isinstance(item, str):
                continue
            for fragment in re.split(r"(?<=[.!?])\s+", item.strip()):
                text = fragment.strip()
                normalized = normalized_choice_text(text)
                key = (label, normalized)
                if len(text) >= 20 and len(text) <= 2400 and key not in seen:
                    seen.add(key)
                    statements.append((label, text))

    return statements


def build_lesson_grounded_mcqs(
    lesson: dict,
    title: str,
    *,
    count: int,
    max_option_length: int,
) -> list[dict]:
    prompt_templates = {
        "lesson introduction": "Which statement captures the foundation introduced for {title}?",
        "lesson explanation": "Which statement is directly taught about {title} in the explanation?",
        "example explanation": "Which statement describes what the lesson example demonstrates about {title}?",
        "real-world application": "Which statement is given as a practical application of {title}?",
        "common mistake": "Which statement identifies a mistake to avoid while learning {title}?",
        "key takeaway": "Which statement is listed as a key takeaway for {title}?",
        "quick recap": "Which statement appears in the lesson recap for {title}?",
    }
    statements_by_section: dict[str, list[str]] = {}
    for label, statement in lesson_statements(lesson):
        if len(statement) <= max_option_length:
            statements_by_section.setdefault(label, []).append(statement)

    candidates = [
        (label, statements[0])
        for label, statements in statements_by_section.items()
        if statements
    ]
    questions: list[dict] = []
    used_option_sets: list[frozenset[str]] = []
    for label, answer_text in candidates:
        target_section_texts = {
            normalized_choice_text(statement)
            for statement in statements_by_section[label]
        }
        other_sections = [section for section in statements_by_section if section != label]
        selected_option_texts: list[str] | None = None
        selected_overlap = 4
        for section_choices in combinations(other_sections, 3):
            distractors: list[str] = []
            for other_label in section_choices:
                distractor = next(
                    (
                        statement
                        for statement in statements_by_section[other_label]
                        if normalized_choice_text(statement) not in target_section_texts
                        and all(
                            normalized_choice_text(statement) != normalized_choice_text(existing)
                            for existing in distractors
                        )
                    ),
                    None,
                )
                if distractor is not None:
                    distractors.append(distractor)
            if len(distractors) != 3:
                continue

            candidate_set = frozenset(
                normalized_choice_text(text)
                for text in [answer_text, *distractors]
            )
            if len(candidate_set) != 4:
                continue
            overlap = max(
                (len(candidate_set.intersection(previous)) for previous in used_option_sets),
                default=0,
            )
            if overlap < selected_overlap:
                selected_option_texts = [answer_text, *distractors]
                selected_overlap = overlap
                if overlap == 0:
                    break

        if selected_option_texts is None or selected_overlap >= 3:
            continue

        option_texts = selected_option_texts.copy()
        correct_index = len(questions) % 4
        option_texts.remove(answer_text)
        option_texts.insert(correct_index, answer_text)
        normalized_set = frozenset(normalized_choice_text(text) for text in option_texts)
        if len(normalized_set) != 4:
            continue
        used_option_sets.append(normalized_set)

        options = [
            {"id": chr(ord("a") + index), "text": text}
            for index, text in enumerate(option_texts)
        ]
        prompt = prompt_templates.get(
            label,
            "Which statement is explicitly included in the lesson's {label} section for {title}?",
        )
        questions.append(
            {
                "prompt": prompt.format(label=label, title=title[:240]),
                "options": options,
                "correct_answer": options[correct_index]["id"],
                "answer_text": answer_text,
                "explanation": (
                    f"The correct statement is included in the lesson's {label} section: "
                    f"{answer_text} The other choices are lesson statements from different sections."
                ),
            }
        )
        if len(questions) == count:
            break

    return questions


def fallback_keywords(answer: str) -> list[str]:
    words = re.findall(r"[^\W_]+", answer.casefold(), flags=re.UNICODE)
    keywords = list(dict.fromkeys(word for word in words if len(word) >= 4 and word not in _STOP_WORDS))
    return keywords[:8]
