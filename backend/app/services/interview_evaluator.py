"""Evaluate free-text HR interview answers with a consistent rubric."""

from app.services.llm import ask_llm_json


def _clean_str(value) -> str:
    if isinstance(value, list):
        return "; ".join(str(item).strip() for item in value if item and str(item).strip())
    if isinstance(value, str):
        return value.strip()
    return ""


def _validate_evaluation_output(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Interview evaluation must be a JSON object.")
    try:
        score = int(round(float(raw.get("score_out_of_10"))))
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("Interview evaluation score is invalid.") from error
    if not 0 <= score <= 10:
        raise ValueError("Interview evaluation score is outside the supported range.")

    strengths = _clean_str(raw.get("strengths"))
    missing_points = _clean_str(raw.get("missing_points"))
    improvements = _clean_str(raw.get("improvement_suggestions"))
    feedback = _clean_str(raw.get("feedback"))
    if not all((strengths, missing_points, improvements, feedback)):
        raise ValueError("Interview evaluation is missing rubric feedback.")

    return {
        "score_out_of_10": score,
        "strengths": strengths,
        "missing_points": missing_points,
        "improvements": improvements,
        "improvement_suggestions": improvements,
        "feedback": feedback,
        "ideal_answer": _clean_str(raw.get("model_answer")) or None,
        "evaluation_source": "ai",
    }


def _deterministic_evaluation_fallback(answer: str) -> dict:
    normalized = " ".join((answer or "").casefold().split())
    if not normalized:
        score = 0
        strengths = "No response was provided."
        missing_points = "A response to the question is needed."
        improvements = "Provide a concise, honest answer to the question."
        feedback = "No response was provided, so it could not be evaluated."
    elif len(normalized.split()) < 3:
        score = 2
        strengths = "The response makes an initial attempt to address the question."
        missing_points = "More context and a specific supporting point are needed."
        improvements = "Add a relevant example or explain your reasoning without inventing experience."
        feedback = "The response is too brief to assess all rubric areas reliably."
    else:
        has_example = any(marker in normalized for marker in ("for example", "for instance", "in my", "during "))
        has_action = any(marker in normalized for marker in ("i ", "we ", "my role", "the team"))
        has_result = any(marker in normalized for marker in ("result", "outcome", "learned", "improved", "completed"))
        score = 4 + int(has_example) + int(has_action) + int(has_result)
        missing = []
        if not has_example:
            missing.append("a relevant specific example")
        if not has_action:
            missing.append("the candidate's own actions or contribution")
        if not has_result:
            missing.append("the outcome or learning")
        missing_points = ", ".join(missing) if missing else "No major rubric element is obviously missing."
        improvements = (
            "Clarify your contribution, supporting example, and outcome where relevant."
            if missing
            else "Keep the response focused and connect its outcome to the question."
        )
        strengths = "The response addresses the question and provides content that can be developed."
        feedback = "Automated fallback feedback is limited because AI evaluation was unavailable."

    return {
        "score_out_of_10": score,
        "strengths": strengths,
        "missing_points": missing_points,
        "improvements": improvements,
        "improvement_suggestions": improvements,
        "feedback": feedback,
        "ideal_answer": None,
        "evaluation_source": "fallback",
    }


def evaluate_candidate_answer(question: str, answer: str, target_role: str) -> dict:
    if not answer or not answer.strip():
        return _deterministic_evaluation_fallback("")

    prompt = f"""
    Act as a fair HR interviewer evaluating a candidate for a "{target_role}" position.
    Question asked: "{question}"
    Candidate's answer: "{answer}"

    Score from 0 to 10 using these equally important criteria: relevance to the question; clarity and
    structure; specificity and supporting example; professionalism and completeness. Judge the evidence,
    not response length. A concise meaningful response can score well. Do not assume experience the
    candidate did not claim. Give specific strengths, missing points, and actionable improvement suggestions.
    A model answer may show a general structure but must not invent personal experiences. Set model_answer
    to null when a safe general exemplar is not appropriate.

    Return EXACTLY this JSON structure with NO markdown formatting:
    {{
      "score_out_of_10": 8,
      "strengths": "The response is relevant and explains the candidate's contribution.",
      "missing_points": "The outcome could be more specific.",
      "improvement_suggestions": "Briefly state the result and what you learned.",
      "feedback": "The answer is clear and relevant.",
      "model_answer": null
    }}
    """

    ai_response = ask_llm_json(prompt, retries=2)
    if isinstance(ai_response, dict) and "error" not in ai_response:
        try:
            return _validate_evaluation_output(ai_response)
        except ValueError:
            pass
    return _deterministic_evaluation_fallback(answer)
