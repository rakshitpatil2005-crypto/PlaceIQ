export const STUDY_COACH_CONCEPT_LIMIT = 120;
export const STUDY_COACH_QUESTION_LIMIT = 500;

export function createStudyCoachRequest({ skillId, lessonId, concept, question }) {
  const normalizedConcept = typeof concept === 'string' ? concept.trim() : '';
  const normalizedQuestion = typeof question === 'string' ? question.trim() : '';

  if (!skillId || !lessonId) {
    throw new Error('Open a skill lesson before asking the Study Coach.');
  }
  if (!normalizedConcept) {
    throw new Error('Enter a concept to explain.');
  }
  if (normalizedConcept.length > STUDY_COACH_CONCEPT_LIMIT) {
    throw new Error(`Keep the concept under ${STUDY_COACH_CONCEPT_LIMIT + 1} characters.`);
  }
  if (normalizedQuestion.length > STUDY_COACH_QUESTION_LIMIT) {
    throw new Error(`Keep your question under ${STUDY_COACH_QUESTION_LIMIT + 1} characters.`);
  }

  return {
    skill_id: skillId,
    lesson_id: lessonId,
    concept: normalizedConcept,
    question: normalizedQuestion || null,
  };
}
