export function getActiveCoachForm(coachForm, lesson) {
  if (!lesson) return null;
  if (coachForm && coachForm.lessonId === lesson.lesson_id) return coachForm;
  return {
    lessonId: lesson.lesson_id,
    concept: lesson.title,
    question: '',
  };
}
