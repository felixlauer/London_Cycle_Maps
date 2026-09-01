import { useEffect, useRef, useState } from 'react';
import {
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { brand, type ChromeTokens } from '../theme/tokens';

/** "?" help popover — web wizard/HelpTip.js */
export function HelpTip({
  text,
  c,
}: {
  text?: string;
  c: ChromeTokens;
}) {
  const [open, setOpen] = useState(false);
  const { width: winW } = useWindowDimensions();
  const btnRef = useRef<View>(null);
  const [anchor, setAnchor] = useState<{ x: number; y: number; w: number; h: number } | null>(null);

  useEffect(() => {
    if (!open) setAnchor(null);
  }, [open]);

  if (!text) return null;

  const maxW = Math.min(260, winW - 24);

  return (
    <>
      <Pressable
        ref={btnRef}
        accessibilityRole="button"
        accessibilityLabel="Help"
        hitSlop={8}
        onPress={() => {
          btnRef.current?.measureInWindow((x, y, w, h) => {
            setAnchor({ x, y, w, h });
            setOpen(true);
          });
        }}
        style={[
          styles.btn,
          { borderColor: c.line, backgroundColor: c.inset },
          open && { borderColor: brand.fuchsia, backgroundColor: `${brand.fuchsia}22` },
        ]}
      >
        <Text style={[styles.btnText, { color: open ? brand.fuchsia : c.textSub }]}>?</Text>
      </Pressable>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.backdrop} onPress={() => setOpen(false)}>
          {anchor ? (
            <View
              pointerEvents="box-none"
              style={[
                styles.pop,
                {
                  width: maxW,
                  left: Math.max(12, Math.min(anchor.x + anchor.w / 2 - maxW / 2, winW - maxW - 12)),
                  top: anchor.y + anchor.h + 8,
                  backgroundColor: c.shellBg,
                  borderColor: c.line,
                },
              ]}
            >
              <Text style={[styles.popText, { color: c.text }]}>{text}</Text>
            </View>
          ) : null}
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  btn: {
    width: 18,
    height: 18,
    borderRadius: 999,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 6,
  },
  btnText: { fontSize: 11, fontWeight: '700', lineHeight: 13 },
  backdrop: { flex: 1 },
  pop: {
    position: 'absolute',
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 10,
    shadowColor: '#000',
    shadowOpacity: 0.18,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  popText: { fontSize: 12.5, lineHeight: 17, fontWeight: '500' },
});
