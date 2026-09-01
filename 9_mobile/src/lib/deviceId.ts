/**
 * Anonymous installation id, generated once and kept in SecureStore.
 *
 * Ride feedback needs distinct-contributor counting to decide when several
 * riders agree about a stretch of road. Signed-in reports use the user id;
 * guests have none, so this stands in. It identifies an install, not a person,
 * and is never sent anywhere except with a report the rider chose to make.
 */
import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';

const DEVICE_ID_KEY = 'tuned_device_id';

let memoryId: string | null = null;
let inFlight: Promise<string> | null = null;

/** Cached id, or null before the first load. Safe to call during render. */
export function peekDeviceId(): string | null {
  return memoryId;
}

export async function loadDeviceId(): Promise<string> {
  if (memoryId) return memoryId;
  if (inFlight) return inFlight;

  inFlight = (async () => {
    try {
      const stored = await SecureStore.getItemAsync(DEVICE_ID_KEY);
      if (stored) {
        memoryId = stored;
        return stored;
      }
    } catch {
      /* fall through to a fresh id */
    }

    const next = Crypto.randomUUID();
    memoryId = next;
    try {
      await SecureStore.setItemAsync(DEVICE_ID_KEY, next);
    } catch {
      // Memory-only for this launch; a new id next time just looks like a new
      // contributor, which costs corroboration but never correctness.
    }
    return next;
  })().finally(() => {
    inFlight = null;
  });

  return inFlight;
}
