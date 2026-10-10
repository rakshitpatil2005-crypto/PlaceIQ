export function validatePracticeAnswer(question, answer) {
  if (typeof answer !== 'string' || !answer.trim()) {
    return question?.type === 'mcq' ? 'Select an answer before continuing.' : 'Enter an answer before continuing.';
  }
  if (answer.length > 6000) return 'Answer must be 6,000 characters or fewer.';
  if (question?.type === 'mcq' && !question.options?.some((option) => option.id === answer)) {
    return 'Choose one of the available answer options.';
  }
  return '';
}
