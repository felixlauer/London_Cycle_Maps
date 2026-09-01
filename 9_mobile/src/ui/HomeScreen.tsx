import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { API_BASE, apiFetch } from '../api/flaskClient';
import { useAuth } from '../auth/AuthProvider';

type HealthState = 'loading' | 'ok' | 'fail';

type ProfileRow = {
  id?: string;
  name?: string;
  is_system?: boolean;
};

export function HomeScreen() {
  const { user, signOut } = useAuth();
  const [health, setHealth] = useState<HealthState>('loading');
  const [healthDetail, setHealthDetail] = useState('');
  const [profiles, setProfiles] = useState<ProfileRow[]>([]);
  const [profilesError, setProfilesError] = useState('');
  const [profilesLoading, setProfilesLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/health`);
        const text = await res.text();
        if (cancelled) return;
        if (!res.ok) {
          setHealth('fail');
          setHealthDetail(`HTTP ${res.status}`);
          return;
        }
        setHealth('ok');
        setHealthDetail(text.slice(0, 160));
      } catch (e) {
        if (!cancelled) {
          setHealth('fail');
          setHealthDetail(e instanceof Error ? e.message : String(e));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setProfilesLoading(true);
      setProfilesError('');
      try {
        const res = await apiFetch('/profiles');
        const data = await res.json().catch(() => ({}));
        if (cancelled) return;
        if (!res.ok) {
          setProfilesError(data.error || `Profiles failed (${res.status})`);
          setProfiles([]);
          return;
        }
        const list = Array.isArray(data) ? data : data.profiles || data.items || [];
        setProfiles(list);
      } catch (e) {
        if (!cancelled) {
          setProfilesError(e instanceof Error ? e.message : String(e));
          setProfiles([]);
        }
      } finally {
        if (!cancelled) setProfilesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const label =
    user?.display_name || user?.email || user?.id || 'Signed in';

  return (
    <ScrollView contentContainerStyle={styles.root}>
      <Text style={styles.brand}>Tuned</Text>
      <Text style={styles.sub}>Signed in as {label}</Text>
      <Text style={styles.meta}>API: {API_BASE || '(unset)'}</Text>

      {health === 'loading' && <ActivityIndicator style={styles.spinner} color="#FF0061" />}
      {health === 'ok' && <Text style={styles.ok}>Backend reachable</Text>}
      {health === 'fail' && <Text style={styles.fail}>Backend not reachable</Text>}
      {!!healthDetail && <Text style={styles.detail}>{healthDetail}</Text>}

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Profiles</Text>
        {profilesLoading && <ActivityIndicator color="#FF0061" />}
        {!!profilesError && <Text style={styles.fail}>{profilesError}</Text>}
        {!profilesLoading && !profilesError && profiles.length === 0 && (
          <Text style={styles.detail}>No profiles returned.</Text>
        )}
        {profiles.map((p, i) => (
          <Text key={p.id || String(i)} style={styles.profileRow}>
            {p.name || p.id || `Profile ${i + 1}`}
            {p.is_system ? ' · system' : ''}
          </Text>
        ))}
      </View>

      <Text style={styles.next}>Next: map + plan a Tuned route (P2c)</Text>

      <Pressable style={styles.signOut} onPress={() => signOut()}>
        <Text style={styles.signOutText}>Sign out</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: {
    flexGrow: 1,
    backgroundColor: '#0B1220',
    paddingHorizontal: 24,
    paddingTop: 72,
    paddingBottom: 40,
  },
  brand: {
    color: '#FF0061',
    fontSize: 36,
    fontWeight: '700',
    letterSpacing: 1,
  },
  sub: {
    color: '#C9D2E3',
    marginTop: 8,
    fontSize: 15,
  },
  meta: {
    color: '#8B97AB',
    marginTop: 16,
    fontSize: 12,
  },
  spinner: {
    marginTop: 20,
  },
  ok: {
    color: '#3DDC97',
    marginTop: 16,
    fontSize: 15,
    fontWeight: '600',
  },
  fail: {
    color: '#FF6B6B',
    marginTop: 12,
    fontSize: 14,
    fontWeight: '600',
  },
  detail: {
    color: '#8B97AB',
    marginTop: 8,
    fontSize: 12,
  },
  card: {
    marginTop: 28,
    backgroundColor: '#151E2E',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#243147',
    padding: 16,
  },
  cardTitle: {
    color: '#F2F5FA',
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 12,
  },
  profileRow: {
    color: '#C9D2E3',
    fontSize: 14,
    paddingVertical: 6,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#243147',
  },
  next: {
    color: '#8B97AB',
    marginTop: 24,
    fontSize: 13,
  },
  signOut: {
    marginTop: 28,
    alignSelf: 'flex-start',
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#243147',
  },
  signOutText: {
    color: '#C9D2E3',
    fontWeight: '600',
  },
});
