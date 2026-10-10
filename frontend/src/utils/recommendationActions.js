export function recommendationLinkLabel(action) {
  if (action === 'practise') return 'Open lesson to practise';
  if (action === 'reassess') return 'Open lesson to reassess';
  if (action === 'revise') return 'Review lesson and practise';
  return 'Open learning lesson';
}
