/**
 * Favourite order + active profile id prefs (web localStorage keys).
 */
import * as SecureStore from 'expo-secure-store';

const FAV_ORDER_KEY = 'tuned_favourite_order';
const ACTIVE_PROFILE_KEY = 'activeProfileId';

let memoryFav: string[] | null = null;
let memoryActive: string | null = null;

export async function loadFavouriteOrder(): Promise<string[]> {
  if (memoryFav) return memoryFav;
  try {
    const raw = await SecureStore.getItemAsync(FAV_ORDER_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    memoryFav = Array.isArray(parsed)
      ? parsed.filter((id): id is string => typeof id === 'string')
      : [];
    return memoryFav;
  } catch {
    memoryFav = [];
    return [];
  }
}

export function peekFavouriteOrder(): string[] {
  return memoryFav || [];
}

export async function writeFavouriteOrder(ids: string[]): Promise<void> {
  memoryFav = ids;
  try {
    await SecureStore.setItemAsync(FAV_ORDER_KEY, JSON.stringify(ids));
  } catch {
    /* ignore */
  }
}

export async function loadActiveProfileId(): Promise<string | null> {
  if (memoryActive != null) return memoryActive;
  try {
    const v = await SecureStore.getItemAsync(ACTIVE_PROFILE_KEY);
    memoryActive = v || null;
    return memoryActive;
  } catch {
    return null;
  }
}

export async function writeActiveProfileId(id: string): Promise<void> {
  memoryActive = id;
  try {
    await SecureStore.setItemAsync(ACTIVE_PROFILE_KEY, id);
  } catch {
    /* ignore */
  }
}
