export async function runSingleFlight(lock, action) {
  if (lock.current) return undefined;

  lock.current = true;
  try {
    return await action();
  } finally {
    lock.current = false;
  }
}
