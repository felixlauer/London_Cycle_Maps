/**
 * Bottom-right hideable panel — which route overlays to draw (edge + point).
 * Routing weights are unchanged; this only controls map display after Get Route.
 */
import React, { useEffect, useState } from 'react';
import {
  ROUTE_OVERLAY_EDGE,
  ROUTE_OVERLAY_POINT,
  countActiveOverlays,
} from './routeOverlayCatalog';
import { API_BASE } from './api/flaskClient';

const sectionStyle = {
  fontSize: '10px',
  fontWeight: 700,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  marginBottom: '8px',
  marginTop: '4px',
};

const OverlayRow = ({ label, isOn, onToggle, swatchColor, theme, disabled }) => (
  <div
    style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: '10px',
      cursor: disabled ? 'default' : 'pointer',
      opacity: disabled ? 0.45 : 1,
    }}
    onClick={() => !disabled && onToggle(!isOn)}
  >
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
      <span style={{
        width: 10, height: 10, borderRadius: 2, flexShrink: 0,
        background: swatchColor, border: `1px solid ${theme.border}`,
      }} />
      <span style={{ fontSize: '12px', fontWeight: isOn ? 600 : 500, color: theme.textMain }}>{label}</span>
    </div>
    <div style={{ position: 'relative', width: 34, height: 18, flexShrink: 0 }}>
      <div style={{
        position: 'absolute', inset: 0, borderRadius: 18,
        background: isOn ? swatchColor : theme.toggleInactive, transition: 'background 0.25s',
      }} />
      <div style={{
        position: 'absolute', width: 14, height: 14, borderRadius: '50%', background: 'white',
        top: 2, left: isOn ? 18 : 2, transition: 'left 0.25s', boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
      }} />
    </div>
  </div>
);

export default function RouteOverlayPicker({
  theme,
  visibility,
  setVisibility,
  routeRevealed,
  lightingActive = false,
  onRefreshDisruptions,
  disruptionStatus,
  apiBase = API_BASE,
}) {
  const [open, setOpen] = useState(false);
  const [catalogVersion, setCatalogVersion] = useState(null);

  useEffect(() => {
    fetch(`${apiBase}/overlay_catalog`)
      .then((r) => r.json())
      .then((d) => { if (d?.version) setCatalogVersion(d.version); })
      .catch(() => {});
  }, [apiBase]);

  const activeCount = countActiveOverlays(visibility);
  const disabled = !routeRevealed;

  const setOne = (id, val) => setVisibility((prev) => ({ ...prev, [id]: val }));

  const clearAll = () => {
    const next = {};
    [...ROUTE_OVERLAY_EDGE, ...ROUTE_OVERLAY_POINT].forEach((o) => { next[o.id] = false; });
    setVisibility(next);
  };

  const renderGroup = (title, items) => (
    <>
      <div style={{ ...sectionStyle, color: theme.textSub }}>{title}</div>
      {items.map(({ id, label, themeColor, requiresLighting }) => {
        const unavailable = requiresLighting && !lightingActive;
        return (
        <OverlayRow
          key={id}
          label={unavailable ? `${label} (night routing off)` : label}
          isOn={!!visibility[id]}
          onToggle={(v) => setOne(id, v)}
          swatchColor={theme[themeColor] || theme.textMain}
          theme={theme}
          disabled={disabled || unavailable}
        />
        );
      })}
    </>
  );

  return (
    <div className="route-overlay-picker">
      {open && (
        <div className="route-overlay-panel" style={{
          width: 280,
          maxWidth: 'calc(100vw - 32px)',
          maxHeight: 'min(60vh, 520px)',
          background: theme.bg,
          borderRadius: 10,
          boxShadow: '0 8px 28px rgba(0,0,0,0.22)',
          marginBottom: 10,
          border: `1px solid ${theme.border}`,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}>
          <div style={{
            padding: '12px 14px',
            background: '#263238',
            color: '#fff',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
          }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 13 }}>Route overlays</div>
              <div style={{ fontSize: 10, opacity: 0.8, marginTop: 3 }}>
                {disabled ? 'Click Get Route to enable' : `${activeCount} on map · routes always shown`}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Hide overlay picker"
              style={{
                background: 'rgba(255,255,255,0.15)', border: 'none', color: '#fff',
                width: 26, height: 26, borderRadius: 6, cursor: 'pointer', fontSize: 16, lineHeight: 1,
              }}
            >×</button>
          </div>

          <div style={{ padding: '8px 14px', borderBottom: `1px solid ${theme.border}` }}>
            <button
              type="button"
              disabled={disabled}
              onClick={clearAll}
              style={{
                width: '100%', padding: '6px 10px', fontSize: 11, fontWeight: 600,
                background: theme.toggleInactive, border: `1px solid ${theme.border}`,
                borderRadius: 6, cursor: disabled ? 'default' : 'pointer', color: theme.textMain,
                opacity: disabled ? 0.5 : 1,
              }}
            >
              Hide all overlays
            </button>
          </div>

          <div style={{ padding: '10px 14px 14px', overflowY: 'auto', flex: 1 }}>
            {renderGroup('Edge overlays', ROUTE_OVERLAY_EDGE)}
            {visibility.disruptions && routeRevealed && onRefreshDisruptions && (
              <div style={{ marginLeft: 18, marginBottom: 10, display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  onClick={onRefreshDisruptions}
                  style={{
                    padding: '3px 8px', fontSize: 10, borderRadius: 4,
                    border: `1px solid ${theme.border}`, background: theme.toggleInactive,
                    cursor: 'pointer', color: theme.textMain,
                  }}
                >
                  Refresh disruptions
                </button>
                <span style={{ fontSize: 10, color: theme.textSub }}>{disruptionStatus || 'Live data'}</span>
              </div>
            )}
            <div style={{ marginTop: 8 }}>{renderGroup('Point overlays', ROUTE_OVERLAY_POINT)}</div>
            {catalogVersion && (
              <div style={{ marginTop: 10, fontSize: 10, color: theme.textSub }}>
                Overlay catalog v{catalogVersion}
              </div>
            )}
          </div>
        </div>
      )}

      <button
        type="button"
        className="route-overlay-fab"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '10px 14px',
          background: open ? '#263238' : theme.bg,
          color: open ? '#fff' : theme.textMain,
          border: open ? 'none' : `1px solid ${theme.border}`,
          borderRadius: 24,
          boxShadow: '0 4px 14px rgba(0,0,0,0.18)',
          cursor: 'pointer',
          fontSize: 13,
          fontWeight: 600,
          float: 'right',
        }}
      >
        <span style={{ fontSize: 15, lineHeight: 1 }}>◫</span>
        <span>Layers</span>
        {!open && activeCount > 0 && routeRevealed && (
          <span style={{
            background: theme.routeOptimized, color: '#fff', fontSize: 10, fontWeight: 700,
            minWidth: 18, height: 18, borderRadius: 9, display: 'inline-flex',
            alignItems: 'center', justifyContent: 'center', padding: '0 5px',
          }}>{activeCount}</span>
        )}
      </button>
    </div>
  );
}
