/**
 * Bug report overlay — web BugReportModal → POST /feedback/bug.
 */
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { X } from 'lucide-react-native';
import { apiFetch } from '../../api/flaskClient';
import { brand, chromeForTheme, space } from '../../theme/tokens';
import type { ThemeMode } from '../../theme/resolveAppearance';

export const BUG_REPORT_MAX_CHARS = 1500;
export const BUG_REPORT_MIN_CHARS = 10;

type Props = {
  open: boolean;
  onClose: () => void;
  themeMode?: ThemeMode;
};

export function BugReportModal({ open, onClose, themeMode = 'dark' }: Props) {
  const c = chromeForTheme(themeMode);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    if (!open) return;
    setMessage('');
    setError('');
    setSending(false);
    setSent(false);
  }, [open]);

  const remaining = BUG_REPORT_MAX_CHARS - message.length;
  const canSend = message.trim().length >= BUG_REPORT_MIN_CHARS
    && message.length <= BUG_REPORT_MAX_CHARS
    && !sending
    && !sent;

  const handleSubmit = async () => {
    if (!canSend) return;
    setSending(true);
    setError('');
    try {
      const res = await apiFetch('/feedback/bug', {
        method: 'POST',
        body: {
          message: message.trim(),
          page_url: 'tuned-mobile://plan',
          user_agent: `TunedMobile/${Platform.OS} ${String(Platform.Version)}`,
          theme: themeMode,
          viewport: 'native',
          app_version: 'mobile-1.0.0',
        },
      });
      const data = await res.json().catch(() => ({} as { error?: string }));
      if (!res.ok) {
        setError(data.error || 'Could not send report.');
        setSending(false);
        return;
      }
      setSent(true);
      setSending(false);
      setTimeout(() => onClose(), 900);
    } catch {
      setError('Could not reach the server.');
      setSending(false);
    }
  };

  return (
    <Modal
      visible={open}
      transparent
      animationType="fade"
      onRequestClose={onClose}
      statusBarTranslucent
    >
      <Pressable style={styles.overlay} onPress={onClose}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={styles.center}
        >
          <Pressable
            style={[
              styles.modal,
              {
                backgroundColor: c.shellBg,
                borderColor: c.shellBorder,
              },
            ]}
            onPress={(e) => e.stopPropagation()}
          >
            <View style={styles.header}>
              <Text style={[styles.title, { color: c.text }]}>Report a bug</Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Close"
                onPress={onClose}
                style={({ pressed }) => [
                  styles.closeBtn,
                  pressed && { opacity: 0.75 },
                ]}
                hitSlop={8}
              >
                <X size={18} strokeWidth={2.2} color={c.textSub} />
              </Pressable>
            </View>

            <Text style={[styles.hint, { color: c.textSub }]}>
              Tell us what went wrong and what you expected. We attach device
              and theme details automatically — no account required.
            </Text>

            <Text style={[styles.label, { color: c.textSub }]}>What happened?</Text>
            <TextInput
              style={[
                styles.textarea,
                {
                  color: c.text,
                  borderColor: c.line,
                  backgroundColor: c.inset,
                },
              ]}
              value={message}
              onChangeText={setMessage}
              maxLength={BUG_REPORT_MAX_CHARS}
              multiline
              textAlignVertical="top"
              placeholder="e.g. After tapping Get Route, the island stayed empty even though the route drew on the map."
              placeholderTextColor={c.textSub}
              editable={!sending && !sent}
              autoFocus
            />

            <View style={styles.meta}>
              <Text style={[styles.metaText, { color: c.textSub }, remaining < 80 && styles.metaWarn]}>
                {remaining} left
              </Text>
              <Text style={[styles.metaText, { color: c.textSub }]}>
                Min {BUG_REPORT_MIN_CHARS} characters
              </Text>
            </View>

            {error ? (
              <Text style={[styles.error, { color: c.danger }]} accessibilityRole="alert">{error}</Text>
            ) : null}
            {sent ? (
              <Text style={styles.success}>Thanks — report sent.</Text>
            ) : null}

            <View style={styles.actions}>
              <Pressable
                onPress={onClose}
                disabled={sending}
                style={({ pressed }) => [
                  styles.btn,
                  { borderColor: c.line, backgroundColor: c.surface },
                  pressed && { opacity: 0.85 },
                ]}
              >
                <Text style={[styles.btnText, { color: c.text }]}>Cancel</Text>
              </Pressable>
              <Pressable
                onPress={() => { void handleSubmit(); }}
                disabled={!canSend}
                style={({ pressed }) => [
                  styles.btn,
                  styles.btnPrimary,
                  !canSend && styles.btnDisabled,
                  pressed && canSend && { opacity: 0.9 },
                ]}
              >
                {sending ? (
                  <ActivityIndicator color="#fff" size="small" />
                ) : (
                  <Text style={styles.btnPrimaryText}>
                    {sent ? 'Sent' : 'Send report'}
                  </Text>
                )}
              </Pressable>
            </View>
          </Pressable>
        </KeyboardAvoidingView>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(16, 24, 40, 0.55)',
    justifyContent: 'center',
    padding: 16,
  },
  center: {
    width: '100%',
    maxWidth: 440,
    alignSelf: 'center',
  },
  modal: {
    borderRadius: 16,
    borderWidth: 1,
    padding: 18,
    gap: 8,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
    letterSpacing: -0.3,
  },
  closeBtn: {
    width: 36,
    height: 36,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  hint: {
    fontSize: 13,
    fontWeight: '500',
    lineHeight: 19,
    marginBottom: 6,
  },
  label: {
    fontSize: 12,
    fontWeight: '600',
  },
  textarea: {
    minHeight: 140,
    borderRadius: 12,
    borderWidth: 1,
    padding: 12,
    fontSize: 14,
    lineHeight: 20,
  },
  meta: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  metaText: {
    fontSize: 11,
    fontWeight: '600',
  },
  metaWarn: {
    color: brand.tiger,
  },
  error: {
    fontSize: 13,
    fontWeight: '600',
  },
  success: {
    fontSize: 13,
    fontWeight: '600',
    color: '#75E0B3',
  },
  actions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
    marginTop: 8,
  },
  btn: {
    minHeight: 40,
    paddingHorizontal: 14,
    borderRadius: space.radiusSm,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnText: {
    fontSize: 14,
    fontWeight: '600',
  },
  btnPrimary: {
    backgroundColor: brand.fuchsia,
    borderColor: brand.fuchsia,
    minWidth: 118,
  },
  btnPrimaryText: {
    fontSize: 14,
    fontWeight: '700',
    color: '#fff',
  },
  btnDisabled: {
    opacity: 0.45,
  },
});
