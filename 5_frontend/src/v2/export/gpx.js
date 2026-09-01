import { detectExportPlatform, exportSuccessMessage } from './exportPlatform';

const GPX_NS = 'http://www.topografix.com/GPX/1/1';
const MAX_SLUG = 32;

export function escapeXml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function slugPart(label) {
  const s = String(label || '')
    .toLowerCase()
    .replace(/['’]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, MAX_SLUG);
  return s || 'route';
}

export function gpxFilename(startLabel, endLabel) {
  return `tuned-${slugPart(startLabel)}-to-${slugPart(endLabel)}.gpx`;
}

export function gpxTrackName(startLabel, endLabel) {
  const a = String(startLabel || '').trim() || 'Start';
  const b = String(endLabel || '').trim() || 'End';
  return `${a} to ${b}`;
}

function validPoints(path) {
  const out = [];
  for (const p of path || []) {
    if (!Array.isArray(p) || p.length < 2) continue;
    const lat = Number(p[0]);
    const lon = Number(p[1]);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
    out.push([lat, lon]);
  }
  return out;
}

/**
 * GPX 1.1 track (breadcrumb). Path is Tuned [[lat, lon], ...].
 */
export function buildGpxTrack({ path, name } = {}) {
  const pts = validPoints(path);
  if (pts.length < 2) {
    throw new Error('Route is too short to export');
  }
  const title = escapeXml(name || 'Tuned route');
  const trkpts = pts.map(([lat, lon]) => (
    `      <trkpt lat="${lat}" lon="${lon}"></trkpt>`
  )).join('\n');
  return (
    `<?xml version="1.0" encoding="UTF-8"?>\n`
    + `<gpx version="1.1" creator="Tuned Cycling" xmlns="${GPX_NS}">\n`
    + `  <trk>\n`
    + `    <name>${title}</name>\n`
    + `    <trkseg>\n`
    + `${trkpts}\n`
    + `    </trkseg>\n`
    + `  </trk>\n`
    + `</gpx>\n`
  );
}

export function downloadGpxFile(xml, filename) {
  const blob = new Blob([xml], { type: 'application/gpx+xml' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.rel = 'noopener';
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2500);
}

function canShareGpxFile(file) {
  try {
    return Boolean(navigator.canShare?.({ files: [file] }));
  } catch {
    return false;
  }
}

/**
 * Desktop + Android: download. iOS: share sheet when the File is allowed, else download.
 * Abort (user dismissed share) is not treated as success.
 */
export async function exportGpxTrack({
  path,
  startLabel,
  endLabel,
  platform,
} = {}) {
  const os = platform || detectExportPlatform();
  const name = gpxTrackName(startLabel, endLabel);
  const xml = buildGpxTrack({ path, name });
  const filename = gpxFilename(startLabel, endLabel);

  if (os === 'ios') {
    const file = new File([xml], filename, { type: 'application/gpx+xml' });
    if (canShareGpxFile(file) && typeof navigator.share === 'function') {
      try {
        await navigator.share({ files: [file], title: name });
        return { ok: true, method: 'share', platform: os, message: exportSuccessMessage(os, 'share') };
      } catch (err) {
        if (err?.name === 'AbortError') {
          return { ok: false, aborted: true, method: 'share', platform: os };
        }
        // Fall through to download if share rejects the payload.
      }
    }
  }

  downloadGpxFile(xml, filename);
  return {
    ok: true,
    method: 'download',
    platform: os,
    message: exportSuccessMessage(os, 'download'),
  };
}
