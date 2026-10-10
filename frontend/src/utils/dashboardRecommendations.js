export function getDashboardRecommendations(response) {
  if (!Array.isArray(response?.recommendations)) return [];
  return response.recommendations
    .filter((item) => (
      item
      && typeof item.skill_id === 'string'
      && typeof item.action === 'string'
      && typeof item.reason === 'string'
      && typeof item.next_step === 'string'
      && Array.isArray(item.evidence)
      && typeof item.href === 'string'
      && item.href.startsWith('/learn?skill=')
    ))
    .slice(0, 2);
}
