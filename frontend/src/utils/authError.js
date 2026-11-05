export function getAuthenticationErrorMessage(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (typeof item?.msg === 'string' ? item.msg.trim() : ''))
      .filter(Boolean);
    if (messages.length) return messages.join(' ');
  }
  return 'Authentication failed';
}
