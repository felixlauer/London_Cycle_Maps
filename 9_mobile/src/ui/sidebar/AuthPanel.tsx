/**
 * Inline auth form — web AuthPanel (login / signup / reset).
 * `signupOnly` + `variant="onboarding"` for first-run signup (no tabs / cancel).
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useAuth } from '../../auth/AuthProvider';
import { brand, chromeForTheme } from '../../theme/tokens';
import type { ThemeMode } from '../../theme/resolveAppearance';
import { useChrome } from '../../theme/useChrome';
import type { AuthTab } from './SidebarContext';

const TABS: { id: AuthTab; label: string }[] = [
  { id: 'login', label: 'Log in' },
  { id: 'signup', label: 'Sign up' },
  { id: 'reset', label: 'Forgot password' },
];

type Props = {
  initialTab?: AuthTab;
  visible?: boolean;
  onClose?: () => void;
  onSuccess?: (info: { tab: AuthTab; displayName?: string; needsConfirm?: boolean }) => void;
  /** Hide login/reset — signup form only (onboarding). */
  signupOnly?: boolean;
  /** Force theme tokens (onboarding forces light). */
  themeMode?: ThemeMode;
  /** `onboarding` hides heading/tabs/cancel and uses web signup placeholders. */
  variant?: 'inline' | 'onboarding';
};

export function AuthPanel({
  initialTab = 'login',
  visible = true,
  onClose,
  onSuccess,
  signupOnly = false,
  themeMode: themeProp,
  variant = 'inline',
}: Props) {
  const chrome = useChrome();
  const c = themeProp ? chromeForTheme(themeProp) : chrome.c;
  const { signIn, signUp, resetPassword } = useAuth();
  const [tab, setTab] = useState<AuthTab>(signupOnly ? 'signup' : initialTab);
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const onboarding = variant === 'onboarding' || signupOnly;

  const resetForm = useCallback(() => {
    setTab(signupOnly ? 'signup' : initialTab);
    setDisplayName('');
    setEmail('');
    setPassword('');
    setError('');
    setNotice('');
    setBusy(false);
  }, [initialTab, signupOnly]);

  const handleDismiss = useCallback(() => {
    resetForm();
    onClose?.();
  }, [onClose, resetForm]);

  useEffect(() => {
    if (!visible) resetForm();
  }, [visible, resetForm]);

  useEffect(() => {
    setTab(signupOnly ? 'signup' : initialTab);
  }, [initialTab, signupOnly]);

  const switchTab = (id: AuthTab) => {
    setTab(id);
    setError('');
    setNotice('');
  };

  const handleSubmit = async () => {
    setError('');
    setNotice('');
    setBusy(true);
    try {
      if (tab === 'login') {
        const { error: err } = await signIn(email.trim(), password);
        if (err) setError(err);
        else {
          onSuccess?.({ tab: 'login' });
          if (!onboarding) handleDismiss();
        }
      } else if (tab === 'signup') {
        const name = displayName.trim();
        const { error: err, needsConfirm } = await signUp(email.trim(), password, name);
        if (err) setError(err);
        else if (needsConfirm && signupOnly) {
          // Web: still advance the tour when email confirmation is required.
          onSuccess?.({ tab: 'signup', displayName: name, needsConfirm: true });
        } else if (needsConfirm) {
          setNotice('Check your inbox to confirm your email, then log in.');
        } else {
          onSuccess?.({ tab: 'signup', displayName: name, needsConfirm: false });
          if (!onboarding) handleDismiss();
        }
      } else {
        const { error: err } = await resetPassword(email.trim());
        if (err) setError(err);
        else setNotice('Password reset email sent — check your inbox.');
      }
    } finally {
      setBusy(false);
    }
  };

  const submitLabel = tab === 'login'
    ? 'Log in'
    : tab === 'signup'
      ? (busy ? 'Please wait…' : 'Create account')
      : 'Send reset link';
  const heading = tab === 'login' ? 'Log in' : tab === 'signup' ? 'Sign up' : 'Reset password';
  const canSubmit = Boolean(email.trim()) && (tab === 'reset' || Boolean(password));

  const namePlaceholder = onboarding ? 'What should we call you?' : 'Display name (optional)';
  const emailPlaceholder = onboarding ? 'you@example.com' : 'Email';
  const passwordPlaceholder = onboarding ? 'At least 10 characters' : (tab === 'signup' ? 'Password (10+ characters)' : 'Password');

  return (
    <View style={styles.wrap}>
      {!onboarding ? (
        <Text style={[styles.heading, { color: c.text }]}>{heading}</Text>
      ) : null}

      {!onboarding ? (
        <View style={styles.tabs}>
          {TABS.map((t) => {
            const active = t.id === tab;
            return (
              <Pressable
                key={t.id}
                onPress={() => switchTab(t.id)}
                style={[styles.tab, { backgroundColor: c.inset }, active && { backgroundColor: c.surface }]}
                hitSlop={4}
              >
                <Text style={[styles.tabText, { color: c.textSub }, active && { color: c.text }]} numberOfLines={1}>
                  {t.label}
                </Text>
              </Pressable>
            );
          })}
        </View>
      ) : null}

      {tab === 'signup' ? (
        <View style={styles.field}>
          {onboarding ? (
            <Text style={[styles.label, { color: c.textSub }]}>Name</Text>
          ) : null}
          <TextInput
            style={[styles.input, { borderColor: c.line, backgroundColor: c.inset, color: c.text }]}
            value={displayName}
            onChangeText={setDisplayName}
            placeholder={namePlaceholder}
            placeholderTextColor={c.textSub}
            autoCapitalize="words"
            maxLength={80}
            editable={!busy}
          />
        </View>
      ) : null}

      <View style={styles.field}>
        {onboarding ? (
          <Text style={[styles.label, { color: c.textSub }]}>Email</Text>
        ) : null}
        <TextInput
          style={[styles.input, { borderColor: c.line, backgroundColor: c.inset, color: c.text }]}
          value={email}
          onChangeText={setEmail}
          placeholder={emailPlaceholder}
          placeholderTextColor={c.textSub}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="email-address"
          textContentType="emailAddress"
          editable={!busy}
        />
      </View>

      {tab !== 'reset' ? (
        <View style={styles.field}>
          {onboarding ? (
            <Text style={[styles.label, { color: c.textSub }]}>Password</Text>
          ) : null}
          <TextInput
            style={[styles.input, { borderColor: c.line, backgroundColor: c.inset, color: c.text }]}
            value={password}
            onChangeText={setPassword}
            placeholder={passwordPlaceholder}
            placeholderTextColor={c.textSub}
            secureTextEntry
            textContentType={tab === 'login' ? 'password' : 'newPassword'}
            editable={!busy}
          />
        </View>
      ) : null}

      {!!error && <Text style={[styles.error, { color: c.danger }]}>{error}</Text>}
      {!!notice && <Text style={[styles.notice, { color: c.startDot }]}>{notice}</Text>}

      <Pressable
        accessibilityRole="button"
        disabled={busy || !canSubmit}
        onPress={() => { void handleSubmit(); }}
        style={({ pressed }) => [
          styles.submit,
          onboarding && styles.submitOnb,
          (busy || !canSubmit) && styles.submitDisabled,
          pressed && !busy && canSubmit && { opacity: 0.9 },
        ]}
      >
        {busy ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.submitText}>{submitLabel}</Text>
        )}
      </Pressable>

      {!onboarding ? (
        <Pressable
          accessibilityRole="button"
          onPress={handleDismiss}
          style={styles.cancel}
          hitSlop={8}
        >
          <Text style={[styles.cancelText, { color: c.textSub }]}>Cancel</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 10,
  },
  heading: {
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 4,
  },
  tabs: {
    flexDirection: 'row',
    gap: 4,
    marginBottom: 4,
  },
  tab: {
    flex: 1,
    minHeight: 40,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  tabText: {
    fontSize: 11.5,
    fontWeight: '600',
  },
  field: { gap: 6 },
  label: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  input: {
    minHeight: 44,
    borderRadius: 9,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 13,
  },
  submit: {
    minHeight: 48,
    borderRadius: 12,
    backgroundColor: brand.fuchsia,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 4,
  },
  submitOnb: {
    borderRadius: 9,
    minHeight: 44,
  },
  submitDisabled: {
    opacity: 0.5,
  },
  submitText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '700',
  },
  cancel: {
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cancelText: {
    fontSize: 14,
    fontWeight: '600',
  },
  error: {
    fontSize: 13,
  },
  notice: {
    fontSize: 13,
  },
});
