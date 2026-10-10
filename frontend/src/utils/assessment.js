export function validateAssessmentAnswers(questions, answers) {
  if (!Array.isArray(questions) || questions.length < 3) {
    return 'This assessment does not contain enough questions.';
  }
  for (const question of questions) {
    const answer = answers?.[question.question_id];
    if (typeof answer !== 'string' || !answer.trim()) {
      return `Answer question ${questions.indexOf(question) + 1} before submitting.`;
    }
    if (answer.length > 6000) return 'Each answer must be 6,000 characters or fewer.';
    if (question.type === 'mcq' && !question.options?.some((option) => option.id === answer)) {
      return `Choose an available option for question ${questions.indexOf(question) + 1}.`;
    }
  }
  return '';
}
