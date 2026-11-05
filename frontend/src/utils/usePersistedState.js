import { useState, useEffect } from 'react';

export default function usePersistedState(key, initial = null) {
  const [value, setValue] = useState(() => {
    try {
      const saved = localStorage.getItem(key);
      return saved ? JSON.parse(saved) : initial;
    } catch {
      return initial;
    }
  });

  useEffect(() => {
    try {
      if (value === null || value === undefined) localStorage.removeItem(key);
      else localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* ignore storage errors */
    }
  }, [key, value]);

  return [value, setValue];
}