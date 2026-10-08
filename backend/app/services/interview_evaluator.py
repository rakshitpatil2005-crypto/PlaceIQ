"""
Interview Answer Evaluator for PlaceIQ (Phase 4.2)

Evaluates candidate interview answers strictly with:
- Score from 0 to 10 (clamped integer)
- Strengths (what the candidate did well)
- Improvements (constructive areas for growth)
- Overall feedback summary
- Ideal answer hint / reference response
- Structured validation rules & safe deterministic fallback
"""
import re
from app.services.llm import ask_llm_json
from app.services.skill_extractor import _alias_to_canonical


def _clean_str(val) -> str:
    if isinstance(val, list):
        return "; ".join(str(item).strip() for item in val if item and str(item).strip())
    if isinstance(val, str):
        return val.strip()
    return ""


def _validate_evaluation_output(raw: dict, question: str, target_role: str) -> dict:
    """
    Sanitize and validate LLM answer evaluation output.
    Guarantees integer score (0-10), strengths, improvements, feedback, and ideal_answer.
    """
    if not isinstance(raw, dict):
        raw = {}

    # Score: clamp to 0..10 integer
    raw_score = raw.get("score_out_of_10") or raw.get("score") or raw.get("rating") or 5
    try:
        score = int(round(float(raw_score)))
        score = max(0, min(10, score))
    except (TypeError, ValueError):
        score = 5

    strengths = _clean_str(raw.get("strengths") or raw.get("strengths_summary") or raw.get("positive_points"))
    if not strengths:
        strengths = "Displayed relevant technical intent and structured communication."

    improvements = _clean_str(raw.get("improvements") or raw.get("areas_for_improvement") or raw.get("constructive_feedback"))
    if not improvements:
        improvements = "Consider providing more specific technical examples and architectural details."

    feedback = _clean_str(raw.get("feedback") or raw.get("overall_feedback"))
    if not feedback:
        feedback = f"Strengths: {strengths} Improvements: {improvements}"

    ideal = _clean_str(raw.get("ideal_answer") or raw.get("sample_answer") or raw.get("reference_answer"))
    if not ideal:
        ideal = f"A complete answer for {target_role} should clearly explain key concepts, practical trade-offs, and real-world implementations related to {question}."

    return {
        "score_out_of_10": score,
        "strengths": strengths,
        "improvements": improvements,
        "feedback": feedback,
        "ideal_answer": ideal,
    }


def _deterministic_evaluation_fallback(question: str, answer: str, target_role: str) -> dict:
    """
    Generate a deterministic answer evaluation fallback if the LLM is unavailable.
    Evaluates word length and technical keyword density.
    """
    answer_text = (answer or "").strip()
    words = answer_text.split()
    word_count = len(words)

    # Simple heuristic scoring based on length and technical terms
    lower_ans = answer_text.lower()
    tech_matches = sum(1 for alias in _alias_to_canonical if alias in lower_ans)

    if word_count < 10:
        score = 3
        strengths = "Provided a direct initial response."
        improvements = "Answer is too brief. Elaborate with technical terminology, code details, or step-by-step logic."
        feedback = "Answer is very short. Expand your response with concrete examples and technical depth."
    elif word_count < 30:
        score = 6 + (1 if tech_matches >= 2 else 0)
        strengths = "Good concise explanation with relevant core terminology."
        improvements = "Could be enhanced by adding practical project examples or performance considerations."
        feedback = "Solid effort. Add practical application details to score higher in placement interviews."
    else:
        score = min(10, 7 + min(3, tech_matches // 2))
        strengths = "Comprehensive answer demonstrating clear technical depth and structured communication."
        improvements = "Ensure concise delivery without losing focus on the core question requirements."
        feedback = "Very thorough response demonstrating good domain knowledge for the role."

    ideal = (
        f"An ideal answer for '{question}' in a {target_role} interview should clearly state core principles, "
        f"explain technical implementation details step-by-step, discuss potential trade-offs, and reference real-world project experiences."
    )

    return {
        "score_out_of_10": score,
        "strengths": strengths,
        "improvements": improvements,
        "feedback": feedback,
        "ideal_answer": ideal,
    }


def evaluate_candidate_answer(question: str, answer: str, target_role: str) -> dict:
    """
    Evaluate a candidate's answer for an interview question.
    Returns dict with keys: score_out_of_10, strengths, improvements, feedback, ideal_answer.
    """
    prompt = f"""
    Act as a senior technical interviewer for a "{target_role}" position.
    Question asked: "{question}"
    Candidate's answer: "{answer}"

    Provide a rigorous, constructive evaluation of the candidate's answer.

    Return EXACTLY this JSON structure with NO markdown formatting:
    {{
      "score_out_of_10": 8,
      "strengths": "Clear explanation of core concepts and good technical terminology.",
      "improvements": "Include specific architectural trade-offs or practical project implementation details.",
      "feedback": "Strong technical response. Adding a concrete code/system example would make it exceptional.",
      "ideal_answer": "An ideal answer should state the definition, explain key mechanisms, discuss performance trade-offs, and provide a practical code/system snippet."
    }}
    """

    ai_response = ask_llm_json(prompt, retries=2)

    if isinstance(ai_response, dict) and "error" not in ai_response:
        validated = _validate_evaluation_output(ai_response, question, target_role)
        return validated

    return _deterministic_evaluation_fallback(question, answer, target_role)
