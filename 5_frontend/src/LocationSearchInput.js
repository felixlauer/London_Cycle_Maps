import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  createSessionToken,
  getMapboxToken,
  suggest,
  retrieve,
} from './mapboxGeocoding';

const DEBOUNCE_MS = 300;
const MIN_QUERY_LEN = 2;

export default function LocationSearchInput({
  label,
  value,
  placeholder,
  theme,
  onSelect,
  disabled = false,
}) {
  const [query, setQuery] = useState(value || '');
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [highlightIndex, setHighlightIndex] = useState(-1);
  const sessionTokenRef = useRef(null);
  const containerRef = useRef(null);
  const debounceRef = useRef(null);
  const requestIdRef = useRef(0);

  const mapboxEnabled = Boolean(getMapboxToken());

  useEffect(() => {
    setQuery(value || '');
  }, [value]);

  useEffect(() => {
    const onDocClick = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const runSuggest = useCallback(async (text, sessionToken) => {
    if (!sessionToken || text.length < MIN_QUERY_LEN) {
      setSuggestions([]);
      setLoading(false);
      return;
    }
    const reqId = ++requestIdRef.current;
    setLoading(true);
    setError('');
    try {
      const results = await suggest(text, sessionToken);
      if (reqId === requestIdRef.current) {
        setSuggestions(results);
        setOpen(true);
        setHighlightIndex(results.length ? 0 : -1);
      }
    } catch (err) {
      if (reqId === requestIdRef.current) {
        setSuggestions([]);
        setError(err.message || 'Search failed');
        setOpen(true);
      }
    } finally {
      if (reqId === requestIdRef.current) setLoading(false);
    }
  }, []);

  const handleFocus = () => {
    sessionTokenRef.current = createSessionToken();
    if (query.length >= MIN_QUERY_LEN) {
      runSuggest(query, sessionTokenRef.current);
    }
  };

  const handleBlur = () => {
    sessionTokenRef.current = null;
  };

  const handleChange = (e) => {
    const text = e.target.value;
    setQuery(text);
    setError('');
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!sessionTokenRef.current) return;
    if (text.length < MIN_QUERY_LEN) {
      setSuggestions([]);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(() => {
      runSuggest(text, sessionTokenRef.current);
    }, DEBOUNCE_MS);
  };

  const pickSuggestion = async (item) => {
    const token = sessionTokenRef.current;
    if (!token || !item?.mapbox_id) return;
    setLoading(true);
    setError('');
    setOpen(false);
    try {
      const result = await retrieve(item.mapbox_id, token);
      const displayLabel = item.name || item.full_address || result.label;
      setQuery(displayLabel);
      onSelect({ lat: result.lat, lon: result.lon, label: displayLabel });
      sessionTokenRef.current = null;
    } catch (err) {
      setError(err.message || 'Could not load place');
      setOpen(true);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (!open || !suggestions.length) {
      if (e.key === 'Escape') setOpen(false);
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightIndex((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const item = suggestions[highlightIndex >= 0 ? highlightIndex : 0];
      if (item) pickSuggestion(item);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  const inputDisabled = disabled || !mapboxEnabled;
  const inputPlaceholder = mapboxEnabled
    ? placeholder
    : 'Mapbox key not configured';

  return (
    <div ref={containerRef} style={{ marginBottom: '8px', position: 'relative' }}>
      {label ? (
      <label style={{ display: 'block', fontSize: '11px', fontWeight: 'bold', color: theme.textSub, marginBottom: '4px' }}>
        {label}
      </label>
      ) : null}
      <input
        type="text"
        value={query}
        onChange={handleChange}
        onFocus={handleFocus}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        disabled={inputDisabled}
        placeholder={inputPlaceholder}
        autoComplete="off"
        style={{
          width: '100%',
          padding: '8px',
          borderRadius: '4px',
          border: `1px solid ${theme.border}`,
          background: theme.bg,
          color: theme.textMain,
          fontSize: '12px',
          boxSizing: 'border-box',
        }}
      />
      {loading && (
        <div style={{ fontSize: '10px', color: theme.textSub, marginTop: '2px' }}>Searching…</div>
      )}
      {error && (
        <div style={{ fontSize: '10px', color: '#f44336', marginTop: '2px' }}>{error}</div>
      )}
      {open && suggestions.length > 0 && (
        <ul
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: '100%',
            margin: '2px 0 0',
            padding: 0,
            listStyle: 'none',
            background: theme.bg,
            border: `1px solid ${theme.border}`,
            borderRadius: '4px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            zIndex: 2000,
            maxHeight: '180px',
            overflowY: 'auto',
          }}
        >
          {suggestions.map((item, idx) => (
            <li
              key={item.mapbox_id || idx}
              onMouseDown={(e) => {
                e.preventDefault();
                pickSuggestion(item);
              }}
              onMouseEnter={() => setHighlightIndex(idx)}
              style={{
                padding: '8px 10px',
                fontSize: '12px',
                cursor: 'pointer',
                background: idx === highlightIndex ? theme.toggleInactive : theme.bg,
                color: theme.textMain,
                borderBottom: idx < suggestions.length - 1 ? `1px solid ${theme.border}` : 'none',
              }}
            >
              <div style={{ fontWeight: 600 }}>{item.name || item.full_address}</div>
              {item.place_formatted && item.name && (
                <div style={{ fontSize: '10px', color: theme.textSub, marginTop: '2px' }}>
                  {item.place_formatted}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {open && !loading && query.length >= MIN_QUERY_LEN && suggestions.length === 0 && !error && (
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: '100%',
            marginTop: '2px',
            padding: '8px 10px',
            fontSize: '11px',
            color: theme.textSub,
            background: theme.bg,
            border: `1px solid ${theme.border}`,
            borderRadius: '4px',
            zIndex: 2000,
          }}
        >
          No results
        </div>
      )}
    </div>
  );
}
