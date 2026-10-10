const adaptivePriorityLabels = {
  demonstrated_weakness: {
    label: 'Assessment-supported weakness',
    className: 'border-rose-200 bg-rose-50 text-rose-900',
  },
  insufficient_evidence: {
    label: 'Insufficient assessment evidence',
    className: 'border-amber-200 bg-amber-50 text-amber-900',
  },
  upcoming_learning: {
    label: 'Upcoming learning · no demonstrated weakness',
    className: 'border-sky-200 bg-sky-50 text-sky-900',
  },
};

export function getAdaptivePriorityDisplay(category) {
  return adaptivePriorityLabels[category] || null;
}
