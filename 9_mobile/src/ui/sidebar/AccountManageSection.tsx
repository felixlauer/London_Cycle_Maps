/**
 * Account accordion — web AccountManageSection (name / password / delete).
 */
import { useEffect, useState, type ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { ChevronDown, KeyRound, Trash2, UserRound } from 'lucide-react-native';
import { useAuth } from '../../auth/AuthProvider';
import { brand } from '../../theme/tokens';
import { useChrome } from '../../theme/useChrome';

export type AccountPanelId = 'name' | 'pwd' | 'del' | null;

type Props = {
  expandedPanel?: AccountPanelId;
  onExpandedPanelChange?: (next: AccountPanelId) => void;
};

export function AccountManageSection({
  expandedPanel = null,
  onExpandedPanelChange,
}: Props) {
  const { c } = useChrome();
  const { user, changePassword, updateDisplayName, deleteAccount } = useAuth();
  const [displayName, setDisplayName] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [deletePassword, setDeletePassword] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setDisplayName(user?.display_name || '');
  }, [user?.display_name]);

  if (!user) return null;

  const openName = expandedPanel === 'name';
  const openPwd = expandedPanel === 'pwd';
  const openDel = expandedPanel === 'del';

  const setPanel = (next: AccountPanelId) => {
    onExpandedPanelChange?.(next);
  };

  const handleUpdateName = async () => {
    setError('');
    setNotice('');
    setBusy(true);
    try {
      const { error: err } = await updateDisplayName(displayName);
      if (err) setError(err);
      else setNotice(displayName.trim() ? 'Name updated.' : 'Name cleared.');
    } finally {
      setBusy(false);
    }
  };

  const handleChangePassword = async () => {
    setError('');
    setNotice('');
    setBusy(true);
    try {
      const { error: err } = await changePassword(currentPassword, newPassword, confirmPassword);
      if (err) setError(err);
      else {
        setNotice('Password updated.');
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
      }
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteAccount = async () => {
    setError('');
    setNotice('');
    if (!deleteConfirm) {
      setError('Please confirm you want to permanently delete your account.');
      return;
    }
    setBusy(true);
    try {
      const { error: err } = await deleteAccount(deletePassword);
      if (err) setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.section} accessibilityLabel="Account">
      <Text style={[styles.title, { color: c.textSub }]}>Account</Text>
      <View style={[styles.card, { backgroundColor: c.inset, borderColor: c.line }]}>
        <AccordionRow
          label="Edit name"
          open={openName}
          icon={<UserRound size={16} strokeWidth={2.2} color={c.icon} />}
          onPress={() => setPanel(openName ? null : 'name')}
        />
        {openName ? (
          <View style={styles.panel}>
            <Text style={[styles.fieldLabel, { color: c.textSub }]}>Name</Text>
            <TextInput
              style={[styles.input, { borderColor: c.line, backgroundColor: c.shellBg, color: c.text }]}
              value={displayName}
              onChangeText={setDisplayName}
              placeholder="What should we call you?"
              placeholderTextColor={c.textSub}
              autoComplete="name"
              maxLength={80}
              editable={!busy}
            />
            <ActionButton label="Update name" busy={busy} onPress={handleUpdateName} surfaceColor={c.surface} textColor={c.text} />
          </View>
        ) : null}

        <View style={[styles.divider, { backgroundColor: c.line }]} />

        <AccordionRow
          label="Change password"
          open={openPwd}
          icon={<KeyRound size={16} strokeWidth={2.2} color={c.icon} />}
          onPress={() => setPanel(openPwd ? null : 'pwd')}
        />
        {openPwd ? (
          <View style={styles.panel}>
            <Text style={[styles.fieldLabel, { color: c.textSub }]}>Current password</Text>
            <TextInput
              style={[styles.input, { borderColor: c.line, backgroundColor: c.shellBg, color: c.text }]}
              value={currentPassword}
              onChangeText={setCurrentPassword}
              secureTextEntry
              autoComplete="password"
              editable={!busy}
            />
            <Text style={[styles.fieldLabel, { color: c.textSub }]}>New password</Text>
            <TextInput
              style={[styles.input, { borderColor: c.line, backgroundColor: c.shellBg, color: c.text }]}
              value={newPassword}
              onChangeText={setNewPassword}
              secureTextEntry
              autoComplete="password-new"
              editable={!busy}
            />
            <Text style={[styles.fieldLabel, { color: c.textSub }]}>Confirm new password</Text>
            <TextInput
              style={[styles.input, { borderColor: c.line, backgroundColor: c.shellBg, color: c.text }]}
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              secureTextEntry
              autoComplete="password-new"
              editable={!busy}
            />
            <ActionButton label="Update password" busy={busy} onPress={handleChangePassword} surfaceColor={c.surface} textColor={c.text} />
          </View>
        ) : null}

        <View style={[styles.divider, { backgroundColor: c.line }]} />

        <AccordionRow
          label="Delete account"
          open={openDel}
          icon={<Trash2 size={16} strokeWidth={2.2} color={c.icon} />}
          onPress={() => setPanel(openDel ? null : 'del')}
        />
        {openDel ? (
          <View style={styles.panel}>
            <Text style={[styles.hint, { color: c.textSub }]}>
              Permanently deletes your account and custom profiles. This cannot be undone.
            </Text>
            <Text style={[styles.fieldLabel, { color: c.textSub }]}>Confirm with your password</Text>
            <TextInput
              style={[styles.input, { borderColor: c.line, backgroundColor: c.shellBg, color: c.text }]}
              value={deletePassword}
              onChangeText={setDeletePassword}
              secureTextEntry
              autoComplete="password"
              editable={!busy}
            />
            <Pressable
              accessibilityRole="checkbox"
              accessibilityState={{ checked: deleteConfirm }}
              onPress={() => setDeleteConfirm((v) => !v)}
              style={styles.checkRow}
              hitSlop={6}
            >
              <View style={[styles.checkbox, { borderColor: c.line, backgroundColor: c.shellBg }, deleteConfirm && styles.checkboxOn]}>
                {deleteConfirm ? <Text style={styles.checkMark}>✓</Text> : null}
              </View>
              <Text style={[styles.checkLabel, { color: c.text }]}>
                I understand this permanently deletes my account.
              </Text>
            </Pressable>
            <ActionButton
              label="Delete my account"
              busy={busy}
              danger
              onPress={handleDeleteAccount}
              surfaceColor={c.surface}
              textColor={c.text}
            />
          </View>
        ) : null}
      </View>

      {!!error && <Text style={[styles.error, { color: c.danger }]}>{error}</Text>}
      {!!notice && <Text style={[styles.notice, { color: c.startDot }]}>{notice}</Text>}
    </View>
  );
}

function AccordionRow({
  label,
  open,
  icon,
  onPress,
}: {
  label: string;
  open: boolean;
  icon: ReactNode;
  onPress: () => void;
}) {
  const { c } = useChrome();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ expanded: open }}
      onPress={onPress}
      style={({ pressed }) => [styles.row, pressed && { backgroundColor: c.surface }]}
    >
      <View style={[styles.icon, { backgroundColor: c.surface }]}>{icon}</View>
      <Text style={[styles.rowLabel, { color: c.text }]}>{label}</Text>
      <View style={[styles.chevron, open && styles.chevronOpen]}>
        <ChevronDown size={14} strokeWidth={2} color={c.textSub} />
      </View>
    </Pressable>
  );
}

function ActionButton({
  label,
  busy,
  onPress,
  danger = false,
  surfaceColor,
  textColor,
}: {
  label: string;
  busy: boolean;
  onPress: () => void;
  danger?: boolean;
  surfaceColor: string;
  textColor: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={busy}
      onPress={onPress}
      style={({ pressed }) => [
        styles.btn,
        danger ? styles.btnDanger : { backgroundColor: surfaceColor },
        busy && { opacity: 0.55 },
        pressed && !busy && { opacity: 0.88 },
      ]}
    >
      {busy ? (
        <ActivityIndicator color="#fff" />
      ) : (
        <Text style={[styles.btnText, { color: textColor }]}>{label}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  section: {
    gap: 8,
  },
  title: {
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: 0.2,
    textTransform: 'uppercase',
  },
  card: {
    borderRadius: 11,
    borderWidth: 1,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    minHeight: 48,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  icon: {
    width: 28,
    height: 28,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowLabel: {
    flex: 1,
    fontSize: 14.5,
    fontWeight: '600',
  },
  chevron: {
    transform: [{ rotate: '0deg' }],
  },
  chevronOpen: {
    transform: [{ rotate: '180deg' }],
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    marginLeft: 50,
  },
  panel: {
    paddingHorizontal: 12,
    paddingBottom: 12,
    gap: 8,
  },
  fieldLabel: {
    fontSize: 12,
    fontWeight: '600',
    marginTop: 2,
  },
  input: {
    minHeight: 44,
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
  },
  hint: {
    fontSize: 12.5,
    lineHeight: 17,
    marginBottom: 2,
  },
  checkRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    minHeight: 44,
    paddingVertical: 4,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 1,
  },
  checkboxOn: {
    borderColor: brand.fuchsia,
    backgroundColor: brand.fuchsia,
  },
  checkMark: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 14,
  },
  checkLabel: {
    flex: 1,
    fontSize: 13,
    lineHeight: 18,
  },
  btn: {
    minHeight: 44,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 4,
  },
  btnDanger: {
    backgroundColor: '#7F1D1D',
  },
  btnText: {
    fontSize: 14,
    fontWeight: '700',
  },
  error: {
    fontSize: 13,
  },
  notice: {
    fontSize: 13,
  },
});
