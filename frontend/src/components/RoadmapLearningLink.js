import { createElement } from 'react';
import { BookOpen } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function RoadmapLearningLink({ skillId }) {
  return createElement(
    Link,
    {
      to: `/learn?skill=${encodeURIComponent(skillId)}`,
      onClick: (event) => event.stopPropagation(),
      className: 'inline-flex items-center gap-1.5 rounded-lg border border-brand-100 bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand-700 transition-colors hover:bg-brand-100',
    },
    createElement(BookOpen, { size: 14, 'aria-hidden': true }),
    'Open skill lesson',
  );
}
