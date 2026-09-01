/**
 * Upload queued in-ride reports. Auth is optional server-side: a guest batch is
 * accepted and counted by device_id, a signed-in batch is attributed to the user.
 */
import { apiFetch } from './flaskClient';
import type { RideReportEnvelope } from '../feedback/rideReportPayload';

export type RideReportUploadResult = {
  accepted: string[];
  duplicates: string[];
  /** Per-report validation failures. Index refers to the submitted batch. */
  errors: { index: number; error: string }[];
};

export class RideReportRejected extends Error {
  constructor(
    message: string,
    /** 4xx: the batch will never succeed, so the queue drops it. */
    readonly status: number,
  ) {
    super(message);
    this.name = 'RideReportRejected';
  }
}

export async function uploadRideReports(
  reports: RideReportEnvelope[],
): Promise<RideReportUploadResult> {
  const res = await apiFetch('/feedback/ride-reports', {
    method: 'POST',
    body: { reports },
  });

  if (!res.ok) {
    let message = `Ride report upload failed (${res.status})`;
    try {
      const data = await res.json();
      if (data?.error) message = String(data.error);
    } catch {
      /* keep the status-only message */
    }
    // 429 is transient (an hourly bucket), so it retries like a 5xx.
    if (res.status >= 400 && res.status < 500 && res.status !== 429) {
      throw new RideReportRejected(message, res.status);
    }
    throw new Error(message);
  }

  const data = await res.json();
  return {
    accepted: Array.isArray(data?.accepted) ? data.accepted.map(String) : [],
    duplicates: Array.isArray(data?.duplicates) ? data.duplicates.map(String) : [],
    errors: Array.isArray(data?.errors) ? data.errors : [],
  };
}
