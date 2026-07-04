import React, { useEffect, useRef, useState } from 'react';

/** Small "?" icon with a click-to-open popover (copy comes from preset_config.json). */
export default function HelpTip({ text }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  if (!text) return null;
  return (
    <span className="wiz-helptip" ref={ref}>
      <button
        type="button"
        className={`wiz-helptip-btn${open ? ' open' : ''}`}
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
        aria-label="Help"
      >
        ?
      </button>
      {open && <span className="wiz-helptip-pop">{text}</span>}
    </span>
  );
}
