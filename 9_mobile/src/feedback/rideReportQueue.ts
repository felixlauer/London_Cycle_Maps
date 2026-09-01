/**
 * Offline-first queue for in-ride route reports.
 *
 * The rider taps mid-junction with a phone in a bracket and no signal. Nothing
 * about that moment can depend on the network, so a tap becomes a line on disk
 * first and a request later:
 *
 *   Flag press -> appendStub (category 'general', written immediately)
 *   category pick or 10 s timeout -> patchCategory (same line, same id)
 *   later, when online -> flush()
 *
 * Written on every mutation so a force-kill mid-picker still leaves the point.
 * `client_event_id` is the idempotency key, so replaying a batch is harmless.
 *
 * Storage is JSONL, one entry per line, because a partially-written last line
 * can be dropped without losing the rest — unlike a truncated JSON array.
 */
import { AppState, type AppStateStatus } from 'react-native';
import { Directory, File, Paths } from 'expo-file-system';
import * as Network from 'expo-network';

import { RideReportRejected, uploadRideReports } from '../api/rideReports';
import type { RideReportCategoryId } from './rideReportCategories';
import { withCategory, type RideReportEnvelope } from './rideReportPayload';

const FILE_NAME = 'ride_reports.jsonl';
const MAX_BATCH = 25;
/** Guards against an unbounded file if uploads stay broken for weeks. */
const MAX_ENTRIES = 500;
/** Keep sent rows briefly so a crash right after upload is still visible. */
const SENT_RETENTION_MS = 24 * 60 * 60 * 1000;
const REJECTED_RETENTION_MS = 7 * 24 * 60 * 60 * 1000;
/** Long enough to batch a burst of taps, short enough to land within the ride. */
export const POST_TAP_FLUSH_DELAY_MS = 15_000;

const BACKOFF_MS = [5_000, 20_000, 60_000, 5 * 60_000, 30 * 60_000];

export type QueueStatus = 'pending' | 'sent' | 'rejected';

export type QueueEntry = {
  status: QueueStatus;
  attempts: number;
  lastError: string | null;
  createdAtMs: number;
  updatedAtMs: number;
  payload: RideReportEnvelope;
};

export type FlushReason =
  | 'nav_end'
  | 'foreground'
  | 'auth'
  | 'connectivity'
  | 'post_tap'
  | 'manual';

let entries: QueueEntry[] = [];
const index = new Map<string, QueueEntry>();
let loaded = false;
let flushing: Promise<void> | null = null;
let nextAttemptAtMs = 0;
let backoffStep = 0;
let tapFlushTimer: ReturnType<typeof setTimeout> | null = null;

function queueFile(): File {
  return new File(Paths.document, FILE_NAME);
}

function serialise(list: QueueEntry[]): string {
  return list.map((e) => JSON.stringify(e)).join('\n') + (list.length ? '\n' : '');
}

/**
 * Synchronous whole-file rewrite. The queue holds a handful of rows per ride,
 * so rewriting is cheaper than tracking byte offsets — and it makes patching a
 * line trivial, which append-only would not.
 */
function persist(): void {
  try {
    const dir = new Directory(Paths.document);
    if (!dir.exists) dir.create({ intermediates: true });
    queueFile().write(serialise(entries));
  } catch (err) {
    // A failed write must not break the ride; the entry survives in memory.
    console.warn('[rideReportQueue] persist failed', err);
  }
}

function reindex(): void {
  index.clear();
  for (const entry of entries) {
    index.set(entry.payload.client_event_id, entry);
  }
}

function prune(nowMs: number): void {
  const before = entries.length;
  entries = entries.filter((e) => {
    if (e.status === 'sent') return nowMs - e.updatedAtMs < SENT_RETENTION_MS;
    if (e.status === 'rejected') return nowMs - e.updatedAtMs < REJECTED_RETENTION_MS;
    return true;
  });
  if (entries.length > MAX_ENTRIES) {
    entries = entries.slice(entries.length - MAX_ENTRIES);
  }
  if (entries.length !== before) reindex();
}

/**
 * Read the file into memory. Synchronous on purpose: a Flag press must be able
 * to write immediately, and an async load racing that write would silently
 * clobber whichever side lost. Merging keeps rows from both.
 */
function hydrate(): void {
  if (loaded) return;
  loaded = true;
  try {
    const file = queueFile();
    if (!file.exists) return;
    const parsed: QueueEntry[] = [];
    for (const line of file.textSync().split('\n')) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const entry = JSON.parse(trimmed) as QueueEntry;
        if (entry?.payload?.client_event_id) parsed.push(entry);
      } catch {
        // A torn final line from a kill mid-write. Drop it, keep the rest.
      }
    }
    const unsaved = entries;
    entries = parsed;
    reindex();
    for (const entry of unsaved) {
      if (!index.has(entry.payload.client_event_id)) {
        entries.push(entry);
        index.set(entry.payload.client_event_id, entry);
      }
    }
    prune(Date.now());
    if (unsaved.length) persist();
  } catch (err) {
    console.warn('[rideReportQueue] load failed', err);
  }
}

/** Warm the queue at startup so the first tap does not pay the read. */
export async function loadQueue(): Promise<void> {
  hydrate();
}

/**
 * Record a tap before the rider has said what it was. Category is 'general'
 * until patchCategory lands; if the app dies in between, that is the row we keep.
 */
export function appendStub(payload: RideReportEnvelope): QueueEntry {
  hydrate();
  const now = Date.now();
  const existing = index.get(payload.client_event_id);
  if (existing) return existing;

  const entry: QueueEntry = {
    status: 'pending',
    attempts: 0,
    lastError: null,
    createdAtMs: now,
    updatedAtMs: now,
    payload,
  };
  entries.push(entry);
  index.set(payload.client_event_id, entry);
  prune(now);
  persist();
  return entry;
}

export function patchCategory(
  clientEventId: string,
  category: RideReportCategoryId,
  elapsedMsIntoPicker: number,
): void {
  hydrate();
  const entry = index.get(clientEventId);
  // Only a still-pending row may change: an uploaded one is the server's now.
  if (!entry || entry.status !== 'pending') return;
  entry.payload = withCategory(entry.payload, category, elapsedMsIntoPicker);
  entry.updatedAtMs = Date.now();
  persist();
}

export function pendingCount(): number {
  return entries.reduce((n, e) => n + (e.status === 'pending' ? 1 : 0), 0);
}

export function queueSnapshot(): QueueEntry[] {
  return entries.map((e) => ({ ...e }));
}

async function isOnline(): Promise<boolean> {
  try {
    const state = await Network.getNetworkStateAsync();
    return Boolean(state.isConnected);
  } catch {
    // Unknown beats blocked: let the request itself decide.
    return true;
  }
}

function markBatchSent(batch: QueueEntry[], ids: Set<string>): void {
  const now = Date.now();
  for (const entry of batch) {
    if (!ids.has(entry.payload.client_event_id)) continue;
    entry.status = 'sent';
    entry.lastError = null;
    entry.updatedAtMs = now;
  }
}

function markBatchRejected(batch: QueueEntry[], message: string): void {
  const now = Date.now();
  for (const entry of batch) {
    entry.status = 'rejected';
    entry.lastError = message;
    entry.attempts += 1;
    entry.updatedAtMs = now;
  }
}

function backOff(batch: QueueEntry[], message: string): void {
  const now = Date.now();
  for (const entry of batch) {
    entry.attempts += 1;
    entry.lastError = message;
    entry.updatedAtMs = now;
  }
  const wait = BACKOFF_MS[Math.min(backoffStep, BACKOFF_MS.length - 1)];
  backoffStep = Math.min(backoffStep + 1, BACKOFF_MS.length - 1);
  nextAttemptAtMs = now + wait;
}

/**
 * Upload pending rows, oldest first, in batches of 25.
 *
 * Never throws: a failed flush leaves the rows on disk for the next trigger.
 * `force` skips the backoff window (used by explicit triggers like login).
 */
export async function flushRideReports(
  reason: FlushReason = 'manual',
  { force = false }: { force?: boolean } = {},
): Promise<void> {
  if (flushing) return flushing;

  flushing = (async () => {
    try {
      await loadQueue();
      if (!pendingCount()) return;
      if (!force && Date.now() < nextAttemptAtMs) return;
      if (!(await isOnline())) return;

      // Bounded: each pass either sends a batch or stops on the first failure.
      for (;;) {
        const batch = entries.filter((e) => e.status === 'pending').slice(0, MAX_BATCH);
        if (!batch.length) break;

        try {
          const result = await uploadRideReports(batch.map((e) => e.payload));
          const settled = new Set([...result.accepted, ...result.duplicates]);
          markBatchSent(batch, settled);

          // Rows the server refused individually would loop forever otherwise.
          const now = Date.now();
          for (const err of result.errors) {
            const entry = batch[err.index];
            if (!entry || entry.status !== 'pending') continue;
            entry.status = 'rejected';
            entry.lastError = err.error;
            entry.updatedAtMs = now;
          }
          // Anything neither settled nor refused: leave pending, stop the loop.
          const stalled = batch.some((e) => e.status === 'pending');
          backoffStep = 0;
          nextAttemptAtMs = 0;
          prune(Date.now());
          persist();
          if (stalled) break;
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          if (err instanceof RideReportRejected) {
            markBatchRejected(batch, message);
          } else {
            backOff(batch, message);
          }
          persist();
          break;
        }
      }
    } catch (err) {
      console.warn(`[rideReportQueue] flush (${reason}) failed`, err);
    } finally {
      flushing = null;
    }
  })();

  return flushing;
}

/** Debounced flush after a tap, so a burst of reports leaves as one request. */
export function scheduleFlushAfterTap(): void {
  if (tapFlushTimer) clearTimeout(tapFlushTimer);
  tapFlushTimer = setTimeout(() => {
    tapFlushTimer = null;
    void flushRideReports('post_tap');
  }, POST_TAP_FLUSH_DELAY_MS);
}

/**
 * Ambient flush triggers: app foregrounding and connectivity returning.
 * Nav-end and auth are explicit call sites. Returns an unsubscribe.
 */
export function installFlushTriggers(): () => void {
  let lastAppState: AppStateStatus = AppState.currentState;
  let lastConnected: boolean | null = null;

  const appSub = AppState.addEventListener('change', (next) => {
    const cameForward = lastAppState.match(/inactive|background/) && next === 'active';
    lastAppState = next;
    if (cameForward) void flushRideReports('foreground', { force: true });
  });

  const netSub = Network.addNetworkStateListener(({ isConnected }) => {
    const connected = Boolean(isConnected);
    const regained = lastConnected === false && connected;
    lastConnected = connected;
    if (regained) void flushRideReports('connectivity', { force: true });
  });

  return () => {
    appSub.remove();
    netSub.remove();
    if (tapFlushTimer) {
      clearTimeout(tapFlushTimer);
      tapFlushTimer = null;
    }
  };
}

/** Unit tests only — drops in-memory state without touching disk. */
export function resetQueueForTests(): void {
  entries = [];
  index.clear();
  loaded = false;
  flushing = null;
  nextAttemptAtMs = 0;
  backoffStep = 0;
  if (tapFlushTimer) {
    clearTimeout(tapFlushTimer);
    tapFlushTimer = null;
  }
}
