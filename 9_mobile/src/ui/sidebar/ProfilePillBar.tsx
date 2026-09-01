/**
 * Mobile open profile chrome — web ProfileZone ≤767px:
 * X | stretched pill (avatar + identity/auth link + logo).
 */
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { X } from 'lucide-react-native';
import { useAuth } from '../../auth/AuthProvider';
import {
  avatarPaletteForEmail,
  initialsFromUser,
} from '../../lib/avatar';
import { useChrome } from '../../theme/useChrome';
import { BrandLogo } from '../BrandLogo';
import { useSidebar } from './SidebarContext';

type Props = {
  /** Extra top padding (status bar / notch). */
  topInset?: number;
};

export function ProfilePillBar({ topInset = 0 }: Props) {
  const { user, isLoading, signOut } = useAuth();
  const {
    view,
    toggleSidebar,
    openAuthPanel,
    closeSidebar,
    closeWizard,
    closeAuthPanel,
  } = useSidebar();
  const { themeMode, c } = useChrome();

  const initials = initialsFromUser(user);
  const palette = avatarPaletteForEmail(user?.email);

  const closeLabel = view === 'wizard'
    ? 'Return to profiles'
    : view === 'auth'
      ? 'Close sign in'
      : 'Close sidebar';

  const handleCloseX = () => {
    if (view === 'wizard') closeWizard();
    else if (view === 'auth') closeAuthPanel();
    else closeSidebar();
  };

  const handleAuthLink = () => {
    if (user) void signOut();
    else openAuthPanel('login');
  };

  const identityLabel = isLoading
    ? '…'
    : user
      ? (user.display_name || user.email || 'Signed in')
      : 'Not signed in';

  return (
    <View style={[styles.zone, { paddingTop: topInset }]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={closeLabel}
        onPress={handleCloseX}
        style={({ pressed }) => [styles.closeX, pressed && { opacity: 0.7 }]}
        hitSlop={6}
      >
        <X size={18} strokeWidth={2.2} color={c.textSub} />
      </Pressable>

      <View style={[
        styles.chrome,
        {
          backgroundColor: c.shellBg,
          borderColor: c.shellBorder,
          shadowOpacity: themeMode === 'dark' ? 0.45 : 0.08,
        },
      ]}
      >
        <View style={styles.main}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Close profile sidebar"
            accessibilityState={{ expanded: true }}
            onPress={toggleSidebar}
            style={({ pressed }) => [
              styles.avatar,
              user ? { backgroundColor: palette.from } : styles.avatarGuest,
              isLoading && { backgroundColor: c.surface },
              pressed && { opacity: 0.9 },
            ]}
          >
            {!isLoading ? (
              <Text
                style={[
                  styles.initials,
                  !user && styles.guestLabel,
                  user ? { color: palette.color } : null,
                ]}
                numberOfLines={1}
              >
                {user ? initials : 'Guest'}
              </Text>
            ) : null}
          </Pressable>

          <View style={styles.identity}>
            <Text style={[styles.email, { color: c.text }]} numberOfLines={1}>
              {identityLabel}
            </Text>
            {!isLoading ? (
              <Pressable
                accessibilityRole="button"
                onPress={handleAuthLink}
                hitSlop={6}
                style={({ pressed }) => pressed && { opacity: 0.75 }}
              >
                <Text style={[styles.authLink, { color: c.textSub }]}>
                  {user ? 'Log out' : 'Sign in'}
                </Text>
              </Pressable>
            ) : null}
          </View>
        </View>

        <View style={styles.logoSlot} pointerEvents="none">
          <View style={styles.logoNudge}>
            <BrandLogo size={28} />
          </View>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  zone: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 0,
    paddingHorizontal: 12,
    /* Web: shell-inset + 56px pill + 20px air under floating chrome */
    paddingBottom: 20,
    backgroundColor: 'transparent',
  },
  closeX: {
    width: 44,
    height: 44,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  chrome: {
    flex: 1,
    minWidth: 0,
    height: 56,
    padding: 5,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
    borderRadius: 999,
    shadowColor: '#000',
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  main: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    height: '100%',
  },
  avatar: {
    width: 46,
    height: 46,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  avatarGuest: {
    backgroundColor: '#7768AE',
  },
  initials: {
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: 0.3,
    color: '#fff',
  },
  guestLabel: {
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
    color: '#fff',
  },
  identity: {
    flex: 1,
    minWidth: 0,
    justifyContent: 'center',
    gap: 2,
  },
  email: {
    fontSize: 12.5,
    fontWeight: '600',
  },
  authLink: {
    fontSize: 11,
    fontWeight: '600',
    textDecorationLine: 'underline',
  },
  logoSlot: {
    width: 46,
    height: 46,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    marginLeft: 'auto',
  },
  logoNudge: {
    transform: [{ translateX: -5 }],
  },
});
