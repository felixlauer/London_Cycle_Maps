import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { createSessionToken, retrieve, suggest, type SuggestItem } from '../api/geocode';
import { TutorialAnchor } from '../onboarding/tutorial/TutorialAnchor';
import { useChrome } from '../theme/useChrome';
import { useSuggestPortal } from './SuggestPortal';

const DEBOUNCE_MS = 300;
const MIN_QUERY_LEN = 3;

/** Map-picked labels look like "51.5074, -0.1278" — never send those to suggest. */
export function looksLikeCoordinates(text: string) {
  return /^-?\d{1,3}(?:\.\d+)?\s*,\s*-?\d{1,3}(?:\.\d+)?$/.test(String(text || '').trim());
}

type Props = {
  value: string;
  placeholder?: string;
  onSelect: (opts: { lat: number; lon: number; label: string }) => void;
  onClear?: () => void;
  /** Called when this field becomes the active map-pick target (focus only). */
  onFocusChange?: (focused: boolean) => void;
  disabled?: boolean;
  /** Compact row height when vias are hidden (web 36px). */
  compact?: boolean;
};

/**
 * Place search — Flask /geocode/suggest + retrieve (web LocationSearchInput).
 * Suggestions render in a window portal (not Modal) so the keyboard stays open
 * and the list scrolls.
 */
export function LocationSearchInput({
  value,
  placeholder,
  onSelect,
  onClear,
  onFocusChange,
  disabled = false,
  compact = false,
}: Props) {
  const { c, themeMode } = useChrome();
  const { setSuggestNode } = useSuggestPortal();
  const dropdownShadowOpacity = themeMode === 'light' ? 0.08 : 0.25;
  const [query, setQuery] = useState(value || '');
  const [suggestions, setSuggestions] = useState<SuggestItem[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [anchor, setAnchor] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const sessionTokenRef = useRef<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestIdRef = useRef(0);
  const wrapRef = useRef<View>(null);
  const inputRef = useRef<TextInput>(null);
  const pickingRef = useRef(false);
  const interactingSuggestRef = useRef(false);

  useEffect(() => {
    setQuery(value || '');
  }, [value]);

  useEffect(() => () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setSuggestNode(null);
  }, [setSuggestNode]);

  const measureAnchor = useCallback(() => {
    wrapRef.current?.measureInWindow((x, y, w, h) => {
      setAnchor({ x, y, w, h });
    });
  }, []);

  const runSuggest = useCallback(async (text: string, sessionToken: string) => {
    if (!sessionToken || text.length < MIN_QUERY_LEN || looksLikeCoordinates(text)) {
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
        measureAnchor();
        setOpen(true);
      }
    } catch (err) {
      if (reqId === requestIdRef.current) {
        setSuggestions([]);
        setError(err instanceof Error ? err.message : 'Search failed');
        measureAnchor();
        setOpen(true);
      }
    } finally {
      if (reqId === requestIdRef.current) setLoading(false);
    }
  }, [measureAnchor]);

  const clearField = useCallback(() => {
    setQuery('');
    setSuggestions([]);
    setOpen(false);
    setError('');
    setLoading(false);
    onClear?.();
  }, [onClear]);

  const handleFocus = () => {
    sessionTokenRef.current = createSessionToken();
    onFocusChange?.(true);
    measureAnchor();
    if (looksLikeCoordinates(query)) return;
    if (query.length >= MIN_QUERY_LEN) {
      runSuggest(query, sessionTokenRef.current);
    }
  };

  const handleBlur = () => {
    setTimeout(() => {
      if (pickingRef.current || interactingSuggestRef.current) return;
      setOpen(false);
    }, 220);
  };

  const dismissSuggestions = () => {
    setOpen(false);
    interactingSuggestRef.current = false;
  };

  const handleChange = (text: string) => {
    setQuery(text);
    setError('');
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!text.trim()) {
      setSuggestions([]);
      setOpen(false);
      onClear?.();
      return;
    }

    if (looksLikeCoordinates(text)) {
      setSuggestions([]);
      setOpen(false);
      return;
    }

    if (!sessionTokenRef.current) {
      sessionTokenRef.current = createSessionToken();
    }
    if (text.length < MIN_QUERY_LEN) {
      setSuggestions([]);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(() => {
      if (sessionTokenRef.current) runSuggest(text, sessionTokenRef.current);
    }, DEBOUNCE_MS);
  };

  const pickSuggestion = async (item: SuggestItem) => {
    const token = sessionTokenRef.current;
    if (!token || !item?.mapbox_id) return;
    pickingRef.current = true;
    setLoading(true);
    setError('');
    setOpen(false);
    try {
      const result = await retrieve(item.mapbox_id, token);
      const displayLabel = item.name || item.full_address || result.label;
      setQuery(displayLabel);
      onSelect({ lat: result.lat, lon: result.lon, label: displayLabel });
      sessionTokenRef.current = null;
      inputRef.current?.blur();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load place');
      setOpen(true);
    } finally {
      setLoading(false);
      pickingRef.current = false;
      interactingSuggestRef.current = false;
    }
  };

  const showSheet = open && !!anchor && (suggestions.length > 0 || (!!error && !loading)
    || (!loading && query.length >= MIN_QUERY_LEN && suggestions.length === 0 && !looksLikeCoordinates(query)));

  useEffect(() => {
    if (!showSheet || !anchor) {
      setSuggestNode(null);
      return undefined;
    }

    setSuggestNode(
      <View style={styles.portalRoot} pointerEvents="box-none">
        <Pressable style={StyleSheet.absoluteFill} onPress={dismissSuggestions} />
        <TutorialAnchor
          id="tut-suggest-dropdown"
          opts={{ ring: true, radius: 8 }}
          style={[
            styles.dropdown,
            {
              top: anchor.y + anchor.h + 2,
              left: anchor.x,
              width: Math.max(anchor.w, 200),
              backgroundColor: c.shellBg,
              borderColor: c.line,
              shadowOpacity: dropdownShadowOpacity,
            },
          ]}
        >
          <ScrollView
            keyboardShouldPersistTaps="handled"
            nestedScrollEnabled
            style={styles.dropdownScroll}
            onTouchStart={() => { interactingSuggestRef.current = true; }}
            onScrollBeginDrag={() => { interactingSuggestRef.current = true; }}
          >
            {!!error && <Text style={[styles.error, { color: c.danger }]}>{error}</Text>}
            {suggestions.map((item, idx) => (
              <Pressable
                key={item.mapbox_id || String(idx)}
                onPress={() => pickSuggestion(item)}
                style={({ pressed }) => [
                  styles.suggestion,
                  idx < suggestions.length - 1 && [styles.suggestionBorder, { borderBottomColor: c.line }],
                  pressed && { backgroundColor: c.surface },
                ]}
              >
                <Text style={[styles.suggestionTitle, { color: c.text }]} numberOfLines={1}>
                  {item.name || item.full_address}
                </Text>
                {!!item.place_formatted && !!item.name && (
                  <Text style={[styles.suggestionSub, { color: c.textSub }]} numberOfLines={1}>
                    {item.place_formatted}
                  </Text>
                )}
              </Pressable>
            ))}
            {!loading && !error && suggestions.length === 0 && query.length >= MIN_QUERY_LEN
              && !looksLikeCoordinates(query) && (
              <Text style={[styles.emptyText, { color: c.textSub }]}>No results</Text>
            )}
          </ScrollView>
        </TutorialAnchor>
      </View>,
    );

    return () => setSuggestNode(null);
  }, [
    showSheet, anchor, suggestions, error, loading, query, c, dropdownShadowOpacity, setSuggestNode,
  ]);

  return (
    <View style={styles.wrap} ref={wrapRef} collapsable={false}>
      <TextInput
        ref={inputRef}
        value={query}
        onChangeText={handleChange}
        onFocus={handleFocus}
        onBlur={handleBlur}
        editable={!disabled}
        placeholder={placeholder}
        placeholderTextColor={c.textSub}
        autoCorrect={false}
        autoCapitalize="none"
        returnKeyType="search"
        blurOnSubmit={false}
        allowFontScaling={false}
        numberOfLines={1}
        style={[styles.input, { color: c.text }, compact && styles.inputCompact]}
      />
      {loading ? (
        <ActivityIndicator size="small" color={c.textSub} style={styles.spinner} />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    minWidth: 0,
    position: 'relative',
  },
  input: {
    height: 45,
    padding: 0,
    margin: 0,
    borderWidth: 0,
    backgroundColor: 'transparent',
    fontSize: 13.5,
    fontWeight: '500',
  },
  inputCompact: {
    height: 36,
  },
  spinner: {
    position: 'absolute',
    right: 0,
    top: 12,
  },
  portalRoot: {
    ...StyleSheet.absoluteFill,
  },
  dropdown: {
    position: 'absolute',
    borderWidth: 1,
    borderRadius: 8,
    maxHeight: 220,
    zIndex: 100,
    elevation: 20,
    shadowColor: '#000',
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    overflow: 'hidden',
  },
  dropdownScroll: {
    maxHeight: 220,
  },
  suggestion: {
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  suggestionBorder: {
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  suggestionTitle: {
    fontSize: 14,
    fontWeight: '600',
  },
  suggestionSub: {
    fontSize: 12,
    marginTop: 2,
  },
  error: {
    padding: 12,
    fontSize: 13,
  },
  emptyText: {
    padding: 12,
    fontSize: 13,
  },
});
