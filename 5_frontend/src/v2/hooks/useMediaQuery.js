import { useEffect, useState } from 'react';

/**
 * Subscribe to a CSS media query. Defaults to false on SSR / first paint.
 */
export default function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined;
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    onChange();
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, [query]);

  return matches;
}

/** True below Tailwind `md` (768px) — mobile chrome layout. */
export function useIsMobile() {
  return useMediaQuery('(max-width: 767px)');
}
