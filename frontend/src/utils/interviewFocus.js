export const INTERVIEW_FOCUS_OPTIONS = [
  {
    value: 'recommended',
    label: 'Recommended for me',
    description: 'Uses your saved role, resume skills, skill gaps, and past weak areas.',
  },
  {
    value: 'programming_languages',
    label: 'Programming Languages',
    description: 'Practice language concepts, syntax, and practical code behavior.',
  },
  {
    value: 'web_development',
    label: 'Web Development',
    description: 'Focus on browser, frontend, backend, and web platform concepts.',
  },
  {
    value: 'data_structures_algorithms',
    label: 'Data Structures & Algorithms',
    description: 'Practice choosing data structures and reasoning about algorithms.',
  },
  {
    value: 'database_sql',
    label: 'Database & SQL',
    description: 'Focus on queries, data modeling, transactions, and database design.',
  },
  {
    value: 'core_computer_science',
    label: 'Core Computer Science',
    description: 'Review operating systems, networking, and core CS foundations.',
  },
  {
    value: 'ai_machine_learning',
    label: 'AI & Machine Learning',
    description: 'Practice model concepts, data, evaluation, and ML applications.',
  },
  {
    value: 'cloud_computing',
    label: 'Cloud Computing',
    description: 'Focus on cloud architecture, deployment, and reliability concepts.',
  },
  {
    value: 'full_stack_development',
    label: 'Full Stack Development',
    description: 'Connect frontend, backend, APIs, and data in end-to-end scenarios.',
  },
  {
    value: 'custom',
    label: 'My own focus',
    description: 'Enter a specific skill or technology you want to practice.',
  },
];

export function interviewFocusDescription(value) {
  return INTERVIEW_FOCUS_OPTIONS.find((option) => option.value === value)?.description ?? '';
}

export function interviewFocusRequestValue(value, customFocus) {
  return value === 'custom' ? `custom:${customFocus.trim()}` : value;
}

export function interviewGenerationReducer(state, action) {
  switch (action.type) {
    case 'start':
      return { loading: true, error: '', notice: '' };
    case 'success':
      return {
        loading: false,
        error: '',
        notice: action.contentSource === 'fallback'
          ? 'AI question generation was unavailable. This session uses the built-in technical question fallback.'
          : '',
      };
    case 'failure':
      return { loading: false, error: action.message, notice: '' };
    default:
      return state;
  }
}

export function interviewGenerationError(status, detail, hasExistingSession, retryAfter) {
  const sessionNote = hasExistingSession
    ? 'Your current interview session and saved results are unchanged. '
    : '';
  if (status === 429) {
    const delay = Number(retryAfter);
    const waitMessage = Number.isFinite(delay) && delay > 0
      ? ` Please wait about ${Math.ceil(delay)} seconds before retrying.`
      : ' Please wait briefly before retrying.';
    const providerMessage = detail?.toLowerCase().includes('quota')
      ? detail
      : 'The question provider is rate-limited.';
    return `${sessionNote}${providerMessage}${detail?.toLowerCase().includes('quota') ? '' : waitMessage}`;
  }
  if (status === 503 && detail?.toLowerCase().includes('validation')) {
    return `${sessionNote}${detail}`;
  }
  return `${sessionNote}${detail || 'Interview questions are temporarily unavailable. Please try again.'}`;
}
