import React from 'react';
import { Sun, Moon, Monitor, Sunset } from 'lucide-react';
import { APPEARANCE_OPTIONS } from '../../theme/resolveAppearance';
import { useSidebar } from '../SidebarContext';

const APPEARANCE_ICONS = {
  light: Sun,
  dark: Moon,
  system: Monitor,
  auto: Sunset,
};

/**
 * System footer — Units first, then Appearance.
 */
export default function SystemFooter() {
  const { appearance, setAppearance, units, setUnits } = useSidebar();

  return (
    <footer className="sb-system">
      <h2 className="sb-system__title">System</h2>

      <div className="sb-system__block">
        <div className="sb-system__label">Units</div>
        <div className="sb-seg sb-seg--units" role="radiogroup" aria-label="Distance units">
          <button
            type="button"
            role="radio"
            aria-checked={units === 'metric'}
            className={`sb-seg__btn${units === 'metric' ? ' is-selected' : ''}`}
            onClick={() => setUnits('metric')}
          >
            Metric
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={units === 'imperial'}
            className={`sb-seg__btn${units === 'imperial' ? ' is-selected' : ''}`}
            onClick={() => setUnits('imperial')}
          >
            Imperial
          </button>
        </div>
      </div>

      <div className="sb-system__block">
        <div className="sb-system__label">Appearance</div>
        <div className="sb-seg" role="radiogroup" aria-label="Appearance">
          {APPEARANCE_OPTIONS.map((opt) => {
            const Icon = APPEARANCE_ICONS[opt.id] || Sun;
            const selected = appearance === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                role="radio"
                aria-checked={selected}
                className={`sb-seg__btn${selected ? ' is-selected' : ''}`}
                title={opt.label}
                onClick={() => setAppearance(opt.id)}
              >
                <Icon size={14} strokeWidth={2.25} aria-hidden />
                <span>{opt.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </footer>
  );
}
