const mockDisk: Record<string, string> = {};

jest.mock('expo-file-system', () => ({
  Paths: { document: 'doc://' },
  Directory: class {
    exists = true;
    create() {}
  },
  File: class {
    path: string;
    constructor(dir: string, name: string) {
      this.path = `${dir}${name}`;
    }
    get exists() {
      return this.path in mockDisk;
    }
    write(content: string) {
      mockDisk[this.path] = content;
    }
    async text() {
      return mockDisk[this.path] ?? '';
    }
    textSync() {
      return mockDisk[this.path] ?? '';
    }
  },
}));

jest.mock('expo-network', () => ({
  getNetworkStateAsync: jest.fn().mockResolvedValue({ isConnected: true }),
  addNetworkStateListener: jest.fn().mockReturnValue({ remove: jest.fn() }),
}));

const mockUpload = jest.fn();

jest.mock('../api/rideReports', () => ({
  uploadRideReports: (...args: unknown[]) => mockUpload(...args),
  RideReportRejected: class RideReportRejected extends Error {},
}));

import { RideReportRejected } from '../api/rideReports';
import { buildRideReport, type RideReportEnvelope } from './rideReportPayload';
import {
  appendStub,
  flushRideReports,
  loadQueue,
  patchCategory,
  pendingCount,
  queueSnapshot,
  resetQueueForTests,
} from './rideReportQueue';

const FILE = 'doc://ride_reports.jsonl';

function envelope(id: string): RideReportEnvelope {
  return buildRideReport({
    clientEventId: id,
    category: 'general',
    deviceId: 'dev-1',
    personalOnly: false,
    simulate: false,
    progress: null,
    fallbackLocation: [51.5, -0.1],
    nav: {
      rerouting: false,
      tracking: true,
      overviewActive: false,
      muted: false,
      cyclewaysVisible: true,
    },
    route: {},
    profile: {},
    device: { platform: 'android' },
    night: { isDark: false },
    timing: { tappedAtMs: Date.now(), elapsedMsIntoPicker: 0 },
  })!;
}

function lines(): Record<string, unknown>[] {
  return (mockDisk[FILE] || '')
    .split('\n')
    .filter(Boolean)
    .map((l) => JSON.parse(l));
}

beforeEach(() => {
  for (const key of Object.keys(mockDisk)) delete mockDisk[key];
  mockUpload.mockReset();
  resetQueueForTests();
});

describe('stub then patch', () => {
  it('writes one line on the tap and rewrites the same line on the pick', () => {
    const stub = envelope('aaaaaaaa-0000-0000-0000-000000000001');
    appendStub(stub);
    expect(lines()).toHaveLength(1);
    expect(lines()[0]).toMatchObject({ status: 'pending', attempts: 0 });

    patchCategory(stub.client_event_id, 'impassable', 1200);
    const after = lines();
    expect(after).toHaveLength(1);
    expect((after[0] as any).payload.category).toBe('impassable');
  });

  it('ignores a repeated stub for the same event id', () => {
    const stub = envelope('aaaaaaaa-0000-0000-0000-000000000002');
    appendStub(stub);
    appendStub(stub);
    expect(lines()).toHaveLength(1);
  });

  it('keeps a tap that landed before the first disk read', async () => {
    mockDisk[FILE] = `${JSON.stringify({
      status: 'pending',
      attempts: 0,
      lastError: null,
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: envelope('bbbbbbbb-0000-0000-0000-000000000001'),
    })}\n`;

    appendStub(envelope('bbbbbbbb-0000-0000-0000-000000000002'));
    await loadQueue();

    expect(pendingCount()).toBe(2);
    expect(lines()).toHaveLength(2);
  });
});

describe('flush', () => {
  it('marks accepted and duplicate ids as sent, then posts nothing again', async () => {
    const a = envelope('cccccccc-0000-0000-0000-000000000001');
    const b = envelope('cccccccc-0000-0000-0000-000000000002');
    appendStub(a);
    appendStub(b);

    mockUpload.mockResolvedValueOnce({
      accepted: [a.client_event_id],
      // Replayed from an earlier partial flush — settled, not stuck.
      duplicates: [b.client_event_id],
      errors: [],
    });

    await flushRideReports('manual');
    expect(mockUpload).toHaveBeenCalledTimes(1);
    expect(pendingCount()).toBe(0);
    expect(queueSnapshot().every((e) => e.status === 'sent')).toBe(true);

    await flushRideReports('manual');
    expect(mockUpload).toHaveBeenCalledTimes(1);
  });

  it('does not retry a batch the server refused', async () => {
    appendStub(envelope('dddddddd-0000-0000-0000-000000000001'));
    mockUpload.mockRejectedValueOnce(new (RideReportRejected as any)('bad category'));

    await flushRideReports('manual');
    expect(pendingCount()).toBe(0);
    expect(queueSnapshot()[0].status).toBe('rejected');

    await flushRideReports('manual', { force: true });
    expect(mockUpload).toHaveBeenCalledTimes(1);
  });

  it('rejects only the row the server named, leaving the batch alone', async () => {
    const a = envelope('eeeeeeee-0000-0000-0000-000000000001');
    const b = envelope('eeeeeeee-0000-0000-0000-000000000002');
    appendStub(a);
    appendStub(b);

    mockUpload.mockResolvedValueOnce({
      accepted: [a.client_event_id],
      duplicates: [],
      errors: [{ index: 1, error: 'lat/lon outside the supported area' }],
    });

    await flushRideReports('manual');
    const byId = Object.fromEntries(
      queueSnapshot().map((e) => [e.payload.client_event_id, e.status]),
    );
    expect(byId[a.client_event_id]).toBe('sent');
    expect(byId[b.client_event_id]).toBe('rejected');
  });

  it('keeps rows pending and backs off after a server error', async () => {
    appendStub(envelope('ffffffff-0000-0000-0000-000000000001'));
    mockUpload.mockRejectedValueOnce(new Error('503'));

    await flushRideReports('manual');
    expect(pendingCount()).toBe(1);
    expect(queueSnapshot()[0].attempts).toBe(1);

    // Inside the backoff window an unforced flush must not hit the network.
    await flushRideReports('manual');
    expect(mockUpload).toHaveBeenCalledTimes(1);

    mockUpload.mockResolvedValueOnce({ accepted: [], duplicates: [], errors: [] });
    await flushRideReports('manual', { force: true });
    expect(mockUpload).toHaveBeenCalledTimes(2);
  });

  it('does nothing when there is nothing to send', async () => {
    await flushRideReports('nav_end');
    expect(mockUpload).not.toHaveBeenCalled();
  });
});
