export const MASTERY_STATUS_LABELS = {
  insufficient_evidence: 'Insufficient evidence',
  developing: 'Developing',
  demonstrated_proficiency: 'Demonstrated proficiency',
  strength: 'Strength',
  review: 'Review',
};

export function formatMasteryScore(score) {
  return typeof score === 'number' && Number.isFinite(score) ? `${score}%` : '—';
}

export function masteryStatusLabel(status) {
  return MASTERY_STATUS_LABELS[status] || 'Insufficient evidence';
}
