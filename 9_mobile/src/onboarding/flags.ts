/**
 * Onboarding / tutorial completion flags — SecureStore (web localStorage parity).
 */
import * as SecureStore from 'expo-secure-store';

export const ONBOARDING_DONE_KEY = 'tuned_onboarding_done';
export const TUTORIAL_DONE_KEY = 'tuned_tutorial_done';

let memoryOnboarding: boolean | null = null;
let memoryTutorial: boolean | null = null;

export async function readOnboardingDone(): Promise<boolean> {
  if (memoryOnboarding != null) return memoryOnboarding;
  try {
    const v = await SecureStore.getItemAsync(ONBOARDING_DONE_KEY);
    memoryOnboarding = v === '1';
    return memoryOnboarding;
  } catch {
    return false;
  }
}

export async function writeOnboardingDone(done = true): Promise<void> {
  memoryOnboarding = done;
  try {
    if (done) await SecureStore.setItemAsync(ONBOARDING_DONE_KEY, '1');
    else await SecureStore.deleteItemAsync(ONBOARDING_DONE_KEY);
  } catch {
    /* ignore */
  }
}

export async function readTutorialDone(): Promise<boolean> {
  if (memoryTutorial != null) return memoryTutorial;
  try {
    const v = await SecureStore.getItemAsync(TUTORIAL_DONE_KEY);
    memoryTutorial = v === '1';
    return memoryTutorial;
  } catch {
    return false;
  }
}

export async function writeTutorialDone(done = true): Promise<void> {
  memoryTutorial = done;
  try {
    if (done) await SecureStore.setItemAsync(TUTORIAL_DONE_KEY, '1');
    else await SecureStore.deleteItemAsync(TUTORIAL_DONE_KEY);
  } catch {
    /* ignore */
  }
}

export async function resetOnboardingFlags(): Promise<void> {
  await writeOnboardingDone(false);
  await writeTutorialDone(false);
}
