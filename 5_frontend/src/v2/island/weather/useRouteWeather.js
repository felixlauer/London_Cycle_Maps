import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../../../api/flaskClient';

const CACHE_MS = 12 * 60 * 1000;
const TEST_POLL_MS = 60 * 1000;

/**
 * Fetch island weather for start lat/lon at now or depart-at.
 * enabled=false skips the request; last good payload is kept until coords/time change.
 * When backend returns weather_test, polls every minute (bypasses client cache).
 */
export default function useRouteWeather({ lat, lon, atIso = null, enabled = false }) {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('idle'); // idle | loading | ok | error
  const abortRef = useRef(null);
  const cacheRef = useRef(new Map());
  const testModeRef = useRef(false);

  const fetchWeather = useCallback(async (bypassCache = false) => {
    if (lat == null || lon == null || !Number.isFinite(Number(lat)) || !Number.isFinite(Number(lon))) {
      return;
    }

    const latN = Number(lat);
    const lonN = Number(lon);
    const atKey = atIso || 'now';
    const cacheKey = `${latN.toFixed(3)}:${lonN.toFixed(3)}:${atKey}`;

    if (!bypassCache && !testModeRef.current) {
      const cached = cacheRef.current.get(cacheKey);
      if (cached && Date.now() - cached.ts < CACHE_MS) {
        setData(cached.data);
        setStatus('ok');
        return;
      }
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setStatus((s) => (s === 'ok' ? 'ok' : 'loading'));

    const params = new URLSearchParams({
      lat: String(latN),
      lon: String(lonN),
    });
    if (atIso) params.set('at', atIso);

    try {
      const res = await apiFetch(`/weather?${params}`, {
        testMode: false,
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(`weather ${res.status}`);
      const json = await res.json();
      if (controller.signal.aborted) return;
      if (json.error || json.temp_c == null) throw new Error(json.error || 'empty weather');

      testModeRef.current = Boolean(json.weather_test);
      if (!json.weather_test) {
        cacheRef.current.set(cacheKey, { ts: Date.now(), data: json });
      }
      setData(json);
      setStatus('ok');
    } catch (err) {
      if (controller.signal.aborted) return;
      setStatus('error');
      setData((prev) => prev);
    }
  }, [lat, lon, atIso]);

  useEffect(() => {
    if (!enabled) {
      setStatus('idle');
      testModeRef.current = false;
      return undefined;
    }

    testModeRef.current = false;
    fetchWeather(false);

    const intervalId = setInterval(() => {
      if (testModeRef.current) fetchWeather(true);
    }, TEST_POLL_MS);

    return () => {
      abortRef.current?.abort();
      clearInterval(intervalId);
    };
  }, [enabled, fetchWeather]);

  return { data, status, ready: status === 'ok' && data != null };
}
