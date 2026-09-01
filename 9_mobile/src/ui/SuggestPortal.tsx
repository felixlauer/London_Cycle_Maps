/**
 * Window-level search suggest host — avoids RN Modal (dismisses keyboard on Android).
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { StyleSheet, View } from 'react-native';

type SuggestPortalContextValue = {
  setSuggestNode: (node: ReactNode | null) => void;
};

const SuggestPortalContext = createContext<SuggestPortalContextValue | null>(null);

export function SuggestPortalProvider({ children }: { children: ReactNode }) {
  const [suggestNode, setSuggestNode] = useState<ReactNode | null>(null);
  const value = useMemo(() => ({ setSuggestNode }), []);

  return (
    <SuggestPortalContext.Provider value={value}>
      {children}
      {suggestNode ? (
        <View style={styles.host} pointerEvents="box-none">
          {suggestNode}
        </View>
      ) : null}
    </SuggestPortalContext.Provider>
  );
}

export function useSuggestPortal() {
  const ctx = useContext(SuggestPortalContext);
  if (!ctx) {
    return {
      setSuggestNode: (_node: ReactNode | null) => {},
    };
  }
  return ctx;
}

/** Optional — no-op outside provider (tests). */
export function useSuggestPortalOptional() {
  return useContext(SuggestPortalContext);
}

const styles = StyleSheet.create({
  host: {
    ...StyleSheet.absoluteFill,
    zIndex: 4000,
    elevation: 4000,
  },
});
