import React, { useEffect, useId } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { detectExportPlatform } from './exportPlatform';
import './gpxHelp.css';

const STEPS = {
  desktop: [
    'Open connect.garmin.com and sign in.',
    'Go to Training → Courses → Import. Choose the GPX file you just downloaded.',
    'Save it as a Course, not an Activity.',
    'On your phone, open the Garmin Connect app and Send to Device.',
    'On the Edge: Navigation → Courses → that route → Ride.',
  ],
  android: [
    'Tap the download notification, or open Files → Downloads.',
    'Open the GPX with Garmin Connect (not as an activity).',
    'Pick cycling, name the course, and save.',
    'Tap Send to Device with your Edge nearby.',
    'On the Edge: Navigation → Courses → that route → Ride.',
  ],
  ios: [
    'If the share sheet opened, choose Copy to Connect (under More if needed).',
    'Otherwise open Files → Downloads, share the GPX, then Copy to Connect.',
    'Save it as a Course in Garmin Connect.',
    'Send to Device with your Edge nearby.',
    'On the Edge: Navigation → Courses → that route → Ride.',
  ],
};

function stepsFor(platform) {
  return STEPS[platform] || STEPS.desktop;
}

/**
 * Garmin-on-the-bars walkthrough. Copy follows desktop / Android / iOS.
 * Watch and phone-app classes are the same GPX — help later.
 */
export default function GpxHelpOverlay({ open, onClose, themeMode = 'light', platform }) {
  const titleId = useId();
  const os = platform || detectExportPlatform();
  const steps = stepsFor(os);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div className="gpx-help-overlay" role="presentation" onClick={onClose}>
      <div
        className="gpx-help-modal"
        data-theme={themeMode}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="gpx-help-modal__header">
          <h2 id={titleId} className="gpx-help-modal__title">
            Follow this route on a Garmin
          </h2>
          <button
            type="button"
            className="gpx-help-modal__close"
            aria-label="Close"
            onClick={onClose}
          >
            <X size={18} strokeWidth={2.2} aria-hidden />
          </button>
        </header>

        <p className="gpx-help-modal__lede">
          The file is a GPX track of the Tuned line. Import it as a Course so
          your Edge can follow it — not as an Activity on your feed.
        </p>

        <ol className="gpx-help-modal__steps">
          {steps.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ol>

        <p className="gpx-help-modal__aside">
          Wahoo ELEMNT and Hammerhead Karoo take the same file: open it in
          the Wahoo or Hammerhead app, then send it to the computer.
        </p>
      </div>
    </div>,
    document.body,
  );
}
