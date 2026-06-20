/** Route overlay layer ids — mirrored by GET /overlay_catalog on app.py */

export const ROUTE_OVERLAY_EDGE = [
  { id: 'lit', label: 'Lit segments', themeColor: 'litColor' },
  { id: 'steep', label: 'Steep / uphill', themeColor: 'steepColor' },
  { id: 'tflCycleway', label: 'TfL cycleways', themeColor: 'tflCyclewayColor' },
  { id: 'tflQuietway', label: 'TfL quietways', themeColor: 'tflQuietwayColor' },
  { id: 'green', label: 'Green / scenic', themeColor: 'greenColor' },
  { id: 'narrow', label: 'Narrow facility', themeColor: 'narrowColor' },
  { id: 'disruptions', label: 'Live disruptions', themeColor: 'disruptionColor' },
];

export const ROUTE_OVERLAY_POINT = [
  { id: 'barriers', label: 'Barriers', themeColor: 'nodeBarrier' },
  { id: 'signals', label: 'Traffic signals', themeColor: 'nodeSignal' },
  { id: 'junctionDanger', label: 'Junctions & crossings', themeColor: 'nodeJunction' },
  { id: 'calming', label: 'Traffic calming', themeColor: 'nodeCalming' },
];

export const ALL_OVERLAY_IDS = [
  ...ROUTE_OVERLAY_EDGE.map((o) => o.id),
  ...ROUTE_OVERLAY_POINT.map((o) => o.id),
];

export const emptyOverlayVisibility = () =>
  Object.fromEntries(ALL_OVERLAY_IDS.map((id) => [id, false]));

/** Visibility when a route is revealed — display-only; not tied to routing weights. */
export const defaultOverlayVisibility = () => ({
  ...emptyOverlayVisibility(),
  tflCycleway: true,
});

export const countActiveOverlays = (vis) =>
  ALL_OVERLAY_IDS.filter((id) => vis[id]).length;
