import React, { useEffect, useRef, useState } from 'react';
import {
  Shield, Zap, Trees, Bike, Package, Road, ChevronDown,
} from 'lucide-react';
import {
  PRESET_META,
  PRESET_ORDER,
  BIKE_OPTIONS,
  SANTANDER_BIKE_OPTIONS,
  buildFavouriteSlots,
  BLOCKED,
} from './constants';

const ICONS = { Shield, Zap, Trees, Bike, Package, Road };

function OptIcon({ name, size = 15 }) {
  const Comp = ICONS[name] || Bike;
  return <Comp size={size} strokeWidth={2} aria-hidden />;
}

/**
 * Mode | Bike | Santander quick-select strip.
 * Neutral surfaces and icons; accent reserved for the Santander status dot.
 * Blocked controls stay clickable so the alert pill can explain why.
 */
export default function ModeBikeSantanderRow({
  profiles,
  favouriteOrder = null,
  activeProfileId,
  onSelectProfile,
  sessionBikeType,
  onSelectBike,
  santanderMode,
  onSantanderChange,
  santanderDisabled,
  bikePulse,
  onBlocked,
  onEditFavourites,
}) {
  const [modeOpen, setModeOpen] = useState(false);
  const [bikeOpen, setBikeOpen] = useState(false);
  const modeRef = useRef(null);
  const bikeRef = useRef(null);

  const favourites = buildFavouriteSlots(profiles, favouriteOrder);
  const activeProfile = (profiles || []).find((p) => p.id === activeProfileId);
  const presetMeta = PRESET_META[activeProfileId];
  const favSlot = favourites.find((f) => f.id === activeProfileId);
  const modeLabel = presetMeta?.label || activeProfile?.name || 'Mode';

  const bikeOpts = santanderMode ? SANTANDER_BIKE_OPTIONS : BIKE_OPTIONS;
  const activeBikeOpt = bikeOpts.find((o) => o.id === sessionBikeType) || bikeOpts[0];

  useEffect(() => {
    const onDoc = (e) => {
      if (modeRef.current && !modeRef.current.contains(e.target)) setModeOpen(false);
      if (bikeRef.current && !bikeRef.current.contains(e.target)) setBikeOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  return (
    <div className="rc-quick">
      <div className="rc-quick__slot" ref={modeRef}>
        <button
          type="button"
          className={`rc-pill${modeOpen ? ' is-open' : ''}`}
          aria-expanded={modeOpen}
          aria-label="Riding mode"
          onClick={() => { setModeOpen((v) => !v); setBikeOpen(false); }}
        >
          <span className="rc-pill__lead">
            {presetMeta ? (
              <OptIcon name={presetMeta.Icon} />
            ) : favSlot ? (
              <span className="rc-badge">{favSlot.slot}</span>
            ) : (
              <Shield size={15} strokeWidth={2} aria-hidden />
            )}
          </span>
          <span className="rc-pill__label">{modeLabel}</span>
          <ChevronDown size={13} strokeWidth={2} className="rc-pill__chevron" aria-hidden />
        </button>
        {modeOpen && (
          <div className="rc-menu" role="listbox">
            {favourites.length > 0 && (
              <div className="rc-menu__section">
                <div className="rc-menu__heading">Favourites</div>
                {favourites.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    className={`rc-menu__item${f.id === activeProfileId ? ' is-active' : ''}`}
                    onClick={() => { onSelectProfile(f.id); setModeOpen(false); }}
                  >
                    <span className="rc-badge">{f.slot}</span>
                    <span className="rc-menu__text">{f.name}</span>
                    {f.id === activeProfileId && <span className="rc-menu__dot" aria-hidden />}
                  </button>
                ))}
              </div>
            )}
            <div className="rc-menu__section">
              <div className="rc-menu__heading">Presets</div>
              {PRESET_ORDER.map((id) => {
                const meta = PRESET_META[id];
                return (
                  <button
                    key={id}
                    type="button"
                    className={`rc-menu__item${id === activeProfileId ? ' is-active' : ''}`}
                    onClick={() => { onSelectProfile(id); setModeOpen(false); }}
                  >
                    <OptIcon name={meta.Icon} />
                    <span className="rc-menu__text">{meta.label}</span>
                    {id === activeProfileId && <span className="rc-menu__dot" aria-hidden />}
                  </button>
                );
              })}
            </div>
            <button
              type="button"
              className="rc-menu__footer"
              onClick={() => {
                if (onEditFavourites) onEditFavourites();
                else onBlocked?.(BLOCKED.editFavouritesSoon);
                setModeOpen(false);
              }}
            >
              Edit favourites…
            </button>
          </div>
        )}
      </div>

      <div className="rc-quick__slot" ref={bikeRef}>
        <button
          type="button"
          className={`rc-pill${bikeOpen ? ' is-open' : ''}${bikePulse ? ' is-pulse' : ''}`}
          aria-expanded={bikeOpen}
          aria-label="Bike type"
          onClick={() => { setBikeOpen((v) => !v); setModeOpen(false); }}
        >
          <span className="rc-pill__lead">
            <OptIcon name={activeBikeOpt.Icon} />
          </span>
          <span className="rc-pill__label">{activeBikeOpt.label}</span>
          <ChevronDown size={13} strokeWidth={2} className="rc-pill__chevron" aria-hidden />
        </button>
        {bikeOpen && (
          <div className="rc-menu" role="listbox">
            {bikeOpts.map((opt) => (
              <button
                key={opt.id}
                type="button"
                className={`rc-menu__item${opt.id === sessionBikeType ? ' is-active' : ''}`}
                onClick={() => { onSelectBike(opt.id); setBikeOpen(false); }}
              >
                <OptIcon name={opt.Icon} />
                <span className="rc-menu__text">{opt.label}</span>
                {opt.id === sessionBikeType && <span className="rc-menu__dot" aria-hidden />}
              </button>
            ))}
          </div>
        )}
      </div>

      <button
        type="button"
        className={
          `rc-pill rc-pill--santander${santanderMode ? ' is-on' : ''}` +
          (santanderDisabled ? ' is-disabled' : '')
        }
        aria-pressed={santanderMode}
        aria-disabled={santanderDisabled}
        title={santanderDisabled ? BLOCKED.santanderNeedsNoStops : 'Santander Cycles hire'}
        onClick={() => {
          if (santanderDisabled) {
            onBlocked?.(BLOCKED.santanderNeedsNoStops);
            return;
          }
          onSantanderChange(!santanderMode);
        }}
      >
        <span className="rc-santander-dot" aria-hidden />
        <span className="rc-pill__label">Santander</span>
      </button>
    </div>
  );
}
