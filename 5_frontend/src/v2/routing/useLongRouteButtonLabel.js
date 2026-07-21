import { useEffect, useRef, useState } from 'react';
import {
  isLongRoute,
  LONG_ROUTE_ARIA_MESSAGES,
  LONG_ROUTE_BUTTON_MESSAGES,
  LONG_ROUTE_MESSAGE_AT_MS,
  LONG_ROUTE_MESSAGE_FADE_MS,
} from './longRouteLoading';

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Rotating short copy for long-route commits on the Get Route button.
 * Resets each time calculating flips on; holds the last line until done.
 */
export function useLongRouteButtonLabel(isCalculating, start, end) {
  const longRoute = isLongRoute(start, end);
  const [messageIndex, setMessageIndex] = useState(0);
  const [textVisible, setTextVisible] = useState(true);
  const sessionRef = useRef(0);

  useEffect(() => {
    if (!isCalculating || !longRoute) {
      setMessageIndex(0);
      setTextVisible(true);
      return undefined;
    }

    const session = sessionRef.current + 1;
    sessionRef.current = session;
    setMessageIndex(0);
    setTextVisible(true);

    const crossfadeTo = async (nextIndex) => {
      if (sessionRef.current !== session) return;
      setTextVisible(false);
      await wait(LONG_ROUTE_MESSAGE_FADE_MS);
      if (sessionRef.current !== session) return;
      setMessageIndex(nextIndex);
      setTextVisible(true);
    };

    const timers = LONG_ROUTE_MESSAGE_AT_MS.slice(1).map((atMs, i) =>
      setTimeout(() => {
        void crossfadeTo(i + 1);
      }, atMs),
    );

    return () => {
      sessionRef.current += 1;
      timers.forEach(clearTimeout);
    };
  }, [isCalculating, longRoute]);

  if (!isCalculating) {
    return {
      longRoute: false,
      label: 'Get Route',
      ariaLabel: 'Get route',
      showDots: false,
      textVisible: true,
    };
  }

  if (!longRoute) {
    return {
      longRoute: false,
      label: 'Calculating',
      ariaLabel: 'Calculating route',
      showDots: true,
      textVisible: true,
    };
  }

  return {
    longRoute: true,
    label: LONG_ROUTE_BUTTON_MESSAGES[messageIndex],
    ariaLabel: LONG_ROUTE_ARIA_MESSAGES[messageIndex],
    showDots: true,
    textVisible,
  };
}
