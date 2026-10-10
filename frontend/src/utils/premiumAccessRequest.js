export async function submitPremiumAccessRequest({
  postRequest,
  currentPlan,
  requestLock,
  setRequesting,
  setError,
  setRequestMessage,
  setPlan,
  setRequestFailed,
}) {
  if (requestLock.current || currentPlan?.access_request_pending) return;

  requestLock.current = true;
  setRequesting(true);
  setError('');
  setRequestMessage('');
  setRequestFailed(false);

  try {
    const { data } = await postRequest();
    if (data?.status === 'already_active') {
      setPlan(data);
      setRequestMessage(data.message || 'Premium access is already active for this account.');
      return;
    }
    if (data?.status !== 'request_recorded' || data.access_request_pending !== true) {
      throw new Error('The server did not confirm that your request is pending. Please retry.');
    }

    setPlan(data);
    setRequestMessage(
      'Your Premium access request was received and is pending review. Premium has not been activated.',
    );
  } catch (error) {
    setRequestFailed(true);
    setError(
      error.response?.data?.detail
      || error.message
      || 'Unable to submit your Premium access request. Please try again.',
    );
  } finally {
    requestLock.current = false;
    setRequesting(false);
  }
}
