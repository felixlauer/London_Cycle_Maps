/**
 * Full-map loading indicator while /route is in flight (long hops only).
 * Staged copy with crossfades; fixed-size card; min dwell before dismiss.
 */
import React, { useEffect, useRef, useState } from 'react';
import './routeLoadingBike.css';

/** Straight-line distance in km between [lat, lon] pairs (WGS84). */
export function straightLineKm(a, b) {
  if (!a || !b) return 0;
  const toRad = (d) => (d * Math.PI) / 180;
  const [lat1, lon1] = a;
  const [lat2, lon2] = b;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const sinDLat = Math.sin(dLat / 2);
  const sinDLon = Math.sin(dLon / 2);
  const h =
    sinDLat * sinDLat +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * sinDLon * sinDLon;
  return 2 * 6371 * Math.asin(Math.min(1, Math.sqrt(h)));
}

export const ROUTE_LOADING_MIN_KM = 10;

const LOADING_MESSAGES = [
  'Looks like a long ride! Mapping the best path...',
  'Analyzing cycle lanes and navigating junctions...',
  'Fine-tuning the details for a smoother journey...',
  'Almost ready, adjusting the final gears...',
];

/** When each message becomes active (ms from mount). Last stays until dismiss. */
const MESSAGE_AT_MS = [0, 3000, 6000, 9000];
const FADE_MS = 200;
const MIN_DWELL_MS = 1500;

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export default function RouteLoadingBike({
  busy = true,
  themeMode = 'light',
  onDismiss,
}) {
  const [messageIndex, setMessageIndex] = useState(0);
  const [textVisible, setTextVisible] = useState(true);
  const messageShownAtRef = useRef(Date.now());
  const completingRef = useRef(false);
  const onDismissRef = useRef(onDismiss);
  onDismissRef.current = onDismiss;

  // Advance through the sequence once; never loop past the last line.
  useEffect(() => {
    let cancelled = false;

    const crossfadeTo = async (nextIndex) => {
      if (cancelled || completingRef.current) return;
      setTextVisible(false);
      await wait(FADE_MS);
      if (cancelled || completingRef.current) return;
      setMessageIndex(nextIndex);
      messageShownAtRef.current = Date.now();
      setTextVisible(true);
      await wait(FADE_MS);
    };

    const timers = MESSAGE_AT_MS.slice(1).map((atMs, i) =>
      setTimeout(() => {
        void crossfadeTo(i + 1);
      }, atMs),
    );

    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
    };
  }, []);

  // When the route finishes: keep current line ≥1.5s, then dismiss (no further advances).
  useEffect(() => {
    if (busy) return undefined;
    completingRef.current = true;
    const elapsed = Date.now() - messageShownAtRef.current;
    const remain = Math.max(0, MIN_DWELL_MS - elapsed);
    const t = setTimeout(() => {
      onDismissRef.current?.();
    }, remain);
    return () => clearTimeout(t);
  }, [busy]);

  return (
    <div className="route-loading-overlay" role="status" aria-live="polite" aria-busy={busy}>
      <div className="route-loading-card" data-theme={themeMode}>
        <svg
          className="route-loading-bike"
          xmlns="http://www.w3.org/2000/svg"
          viewBox="80 200 330 140"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <line className="road" x1="91" y1="322" x2="394" y2="322" strokeWidth="5" />

          <g className="wheel-rear">
            <ellipse className="rim" cx="181.62" cy="287.416" rx="30" ry="30" strokeWidth="5" />
            <g className="arc-spin" style={{ transformOrigin: '181.62px 287.416px' }}>
              <path
                className="arc"
                d="M 181.75 312.104 C 191.942 312.104 201.027 305.675 204.417 296.062"
                strokeWidth="3"
              />
            </g>
          </g>

          <g className="wheel-front">
            <ellipse className="rim" cx="294.039" cy="287.693" rx="30" ry="30" strokeWidth="5" />
            <g className="arc-spin" style={{ transformOrigin: '294.039px 287.693px' }}>
              <path
                className="arc"
                d="M 294.04 312.38 C 304.23 312.38 313.32 305.95 316.71 296.34"
                strokeWidth="3"
              />
            </g>
          </g>

          <g className="frame">
            <ellipse
              cx="181.749"
              cy="288.042"
              rx="5"
              ry="5"
              fill="currentColor"
              stroke="currentColor"
            />
            <ellipse
              cx="228.827"
              cy="287.693"
              rx="5"
              ry="5"
              fill="currentColor"
              stroke="currentColor"
              strokeWidth="1"
            />
            <polygon
              points="181.75 287.693 197.442 231.897 272.418 232.246 228.827 287.693"
              strokeWidth="5"
            />
            <polyline points="294.388 289.785 265.792 214.81 280.09 214.81" strokeWidth="5" />
            <polyline
              points="228.827 286.995 188.375 215.507 177.216 215.507 198.14 215.507"
              strokeWidth="5"
            />
          </g>
        </svg>

        <div className="route-loading-text">
          <p className={textVisible ? 'is-visible' : 'is-hidden'}>
            {LOADING_MESSAGES[messageIndex]}
          </p>
        </div>
      </div>
    </div>
  );
}
