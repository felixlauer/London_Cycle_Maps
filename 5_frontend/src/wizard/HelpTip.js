import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';

/** Small "?" icon with a click-to-open popover (copy comes from preset_config.json). */
export default function HelpTip({ text }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(null);
  const ref = useRef(null);
  const popRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('touchstart', onDocClick);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('touchstart', onDocClick);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!open || !ref.current) {
      setPos(null);
      return undefined;
    }
    const place = () => {
      const btn = ref.current?.getBoundingClientRect();
      if (!btn) return;
      const margin = 12;
      const maxW = Math.min(260, window.innerWidth - margin * 2);
      let left = btn.left + btn.width / 2 - maxW / 2;
      left = Math.max(margin, Math.min(left, window.innerWidth - maxW - margin));
      let top = btn.top - 8;
      const popH = popRef.current?.offsetHeight || 120;
      if (top - popH < margin) {
        top = btn.bottom + 8;
        setPos({ left, top, width: maxW, place: 'below' });
      } else {
        setPos({ left, top: top - popH, width: maxW, place: 'above' });
      }
    };
    place();
    const ro = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(place)
      : null;
    if (popRef.current) ro?.observe(popRef.current);
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      ro?.disconnect();
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [open, text]);

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
      {open && pos && (
        <span
          ref={popRef}
          className={`wiz-helptip-pop is-fixed is-${pos.place}`}
          style={{ left: pos.left, top: pos.top, width: pos.width }}
        >
          {text}
        </span>
      )}
    </span>
  );
}
