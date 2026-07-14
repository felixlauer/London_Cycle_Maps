/**
 * Google Maps–style Leave now / Depart at under Get Route.
 * Stores Europe/London local time; emits ISO or null (leave now).
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import timeIcon from '../assets/time-2624.svg';
import calendarIcon from '../assets/calendar-11015.svg';

const STEP_MIN = 15;
const DAY_COUNT = 7;

/** Wall-clock parts in Europe/London for a Date. */
function londonParts(d = new Date()) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Europe/London',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      weekday: 'short',
      hour12: false,
    })
      .formatToParts(d)
      .filter((p) => p.type !== 'literal')
      .map((p) => [p.type, p.value]),
  );
  return {
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day),
    hour: Number(parts.hour === '24' ? 0 : parts.hour),
    minute: Number(parts.minute),
    weekday: parts.weekday,
  };
}

/** London offset minutes east of UTC at an approximate Instant. */
function londonOffsetMinutes(approxDate) {
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Europe/London',
    timeZoneName: 'shortOffset',
  });
  const tz = fmt.formatToParts(approxDate).find((p) => p.type === 'timeZoneName')?.value || 'GMT';
  const m = tz.match(/GMT([+-])(\d{1,2})(?::?(\d{2}))?/i);
  if (!m) return 0;
  const sign = m[1] === '-' ? -1 : 1;
  return sign * (Number(m[2]) * 60 + Number(m[3] || 0));
}

/** Build Date for London Y-M-D HH:MM (local wall clock). */
function dateFromLondonLocal(year, month, day, hour, minute) {
  const utcGuess = Date.UTC(year, month - 1, day, hour, minute, 0);
  const off = londonOffsetMinutes(new Date(utcGuess));
  return new Date(utcGuess - off * 60_000);
}

function roundUpToStep(minute, step = STEP_MIN) {
  return Math.ceil(minute / step) * step;
}

function clampToNotBeforeNow(dayIndex, hour, minute) {
  if (dayIndex !== 0) return { hour, minute };
  const now = londonParts();
  const nowTotal = now.hour * 60 + now.minute;
  let total = hour * 60 + minute;
  if (total < nowTotal) {
    total = roundUpToStep(nowTotal, STEP_MIN);
    if (total >= 24 * 60) return { hour: 23, minute: 45 };
  }
  return { hour: Math.floor(total / 60), minute: total % 60 };
}

function buildDayOptions() {
  const out = [];
  const now = new Date();
  for (let i = 0; i < DAY_COUNT; i += 1) {
    const d = new Date(now.getTime() + i * 86_400_000);
    const p = londonParts(d);
    const label = i === 0
      ? 'Today'
      : new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London', weekday: 'short' }).format(d);
    out.push({
      index: i,
      label,
      year: p.year,
      month: p.month,
      day: p.day,
    });
  }
  return out;
}

function formatHm(hour, minute) {
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

function toLondonIso(year, month, day, hour, minute) {
  const dt = dateFromLondonLocal(year, month, day, hour, minute);
  const offMin = londonOffsetMinutes(dt);
  const sign = offMin >= 0 ? '+' : '-';
  const abs = Math.abs(offMin);
  const oh = String(Math.floor(abs / 60)).padStart(2, '0');
  const om = String(abs % 60).padStart(2, '0');
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}T${formatHm(hour, minute)}:00${sign}${oh}:${om}`;
}

function defaultDepartSlot() {
  const days = buildDayOptions();
  const now = londonParts();
  let total = roundUpToStep(now.hour * 60 + now.minute + STEP_MIN, STEP_MIN);
  let dayIndex = 0;
  if (total >= 24 * 60) {
    dayIndex = 1;
    total = 0;
  }
  const hour = Math.floor(total / 60);
  const minute = total % 60;
  const day = days[Math.min(dayIndex, days.length - 1)];
  return {
    dayIndex: day.index,
    hour,
    minute,
    iso: toLondonIso(day.year, day.month, day.day, hour, minute),
  };
}

/**
 * @param {{
 *   mode: 'now' | 'depart_at',
 *   departAtIso: string | null,
 *   onChange: (next: { mode: 'now' | 'depart_at', departAtIso: string | null }) => void,
 * }} props
 */
export default function DepartAtControl({ mode, departAtIso, onChange }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const days = useMemo(() => buildDayOptions(), []);

  const slotFromIso = useMemo(() => {
    if (!departAtIso) return defaultDepartSlot();
    try {
      const d = new Date(departAtIso);
      if (Number.isNaN(d.getTime())) return defaultDepartSlot();
      const p = londonParts(d);
      let dayIndex = days.findIndex(
        (x) => x.year === p.year && x.month === p.month && x.day === p.day,
      );
      if (dayIndex < 0) dayIndex = 0;
      const clamped = clampToNotBeforeNow(dayIndex, p.hour, p.minute - (p.minute % STEP_MIN));
      const day = days[dayIndex];
      return {
        dayIndex,
        hour: clamped.hour,
        minute: clamped.minute,
        iso: toLondonIso(day.year, day.month, day.day, clamped.hour, clamped.minute),
      };
    } catch {
      return defaultDepartSlot();
    }
  }, [departAtIso, days]);

  const [dayIndex, setDayIndex] = useState(slotFromIso.dayIndex);
  const [hour, setHour] = useState(slotFromIso.hour);
  const [minute, setMinute] = useState(slotFromIso.minute);

  useEffect(() => {
    setDayIndex(slotFromIso.dayIndex);
    setHour(slotFromIso.hour);
    setMinute(slotFromIso.minute);
  }, [slotFromIso.dayIndex, slotFromIso.hour, slotFromIso.minute]);

  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const emitDepartAt = (nextDay, nextHour, nextMinute) => {
    const clamped = clampToNotBeforeNow(nextDay, nextHour, nextMinute);
    const day = days[nextDay] || days[0];
    const iso = toLondonIso(day.year, day.month, day.day, clamped.hour, clamped.minute);
    setDayIndex(nextDay);
    setHour(clamped.hour);
    setMinute(clamped.minute);
    onChange({ mode: 'depart_at', departAtIso: iso });
  };

  const pillLabel = useMemo(() => {
    if (mode !== 'depart_at' || !departAtIso) return 'Leave now';
    const day = days[dayIndex] || days[0];
    const dayLab = dayIndex === 0 ? 'Today' : day.label;
    return `${dayLab} ${formatHm(hour, minute)}`;
  }, [mode, departAtIso, days, dayIndex, hour, minute]);

  const nudgeTime = (dir) => {
    let total = hour * 60 + minute + dir * STEP_MIN;
    let nextDay = dayIndex;
    if (total < 0) {
      if (dayIndex === 0) {
        emitDepartAt(0, 0, 0);
        return;
      }
      nextDay = dayIndex - 1;
      total = 24 * 60 - STEP_MIN;
    } else if (total >= 24 * 60) {
      if (dayIndex >= DAY_COUNT - 1) {
        emitDepartAt(dayIndex, 23, 45);
        return;
      }
      nextDay = dayIndex + 1;
      total = 0;
    }
    emitDepartAt(nextDay, Math.floor(total / 60), total % 60);
  };

  const nudgeDay = (dir) => {
    const next = Math.max(0, Math.min(DAY_COUNT - 1, dayIndex + dir));
    emitDepartAt(next, hour, minute);
  };

  return (
    <div className="depart-at" ref={rootRef}>
      <button
        type="button"
        className="depart-at__pill"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <img src={timeIcon} alt="" className="depart-at__icon" width={16} height={16} />
        <span className="depart-at__pill-label">{pillLabel}</span>
        <span className="depart-at__caret" aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>

      {open && (
        <div className="depart-at__menu" role="listbox">
          <button
            type="button"
            className={`depart-at__option${mode === 'now' ? ' is-active' : ''}`}
            onClick={() => {
              onChange({ mode: 'now', departAtIso: null });
              setOpen(false);
            }}
          >
            Leave now
          </button>
          <button
            type="button"
            className={`depart-at__option${mode === 'depart_at' ? ' is-active' : ''}`}
            onClick={() => {
              const slot = defaultDepartSlot();
              setDayIndex(slot.dayIndex);
              setHour(slot.hour);
              setMinute(slot.minute);
              onChange({ mode: 'depart_at', departAtIso: slot.iso });
            }}
          >
            Depart at
          </button>

          {mode === 'depart_at' && (
            <div className="depart-at__row">
              <div className="depart-at__field">
                <img src={timeIcon} alt="" className="depart-at__icon" width={14} height={14} />
                <button type="button" className="depart-at__step" onClick={() => nudgeTime(-1)} aria-label="Earlier">
                  ◀
                </button>
                <span className="depart-at__value">{formatHm(hour, minute)}</span>
                <button type="button" className="depart-at__step" onClick={() => nudgeTime(1)} aria-label="Later">
                  ▶
                </button>
              </div>
              <div className="depart-at__field">
                <img src={calendarIcon} alt="" className="depart-at__icon" width={14} height={14} />
                <button type="button" className="depart-at__step" onClick={() => nudgeDay(-1)} aria-label="Previous day">
                  ◀
                </button>
                <span className="depart-at__value">
                  {(days[dayIndex] || days[0]).label}
                </span>
                <button type="button" className="depart-at__step" onClick={() => nudgeDay(1)} aria-label="Next day">
                  ▶
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** True when depart_at is more than 30 minutes ahead of London now (matches backend). */
export function isFutureDepartAt(departAtIso) {
  if (!departAtIso) return false;
  const t = new Date(departAtIso).getTime();
  if (Number.isNaN(t)) return false;
  return t - Date.now() > 30 * 60_000;
}

export function formatDepartStatusHint(mode, departAtIso) {
  if (mode !== 'depart_at' || !departAtIso) return '';
  const p = londonParts(new Date(departAtIso));
  const days = buildDayOptions();
  const idx = days.findIndex((x) => x.year === p.year && x.month === p.month && x.day === p.day);
  const dayLab = idx === 0 ? 'Today' : (days[idx]?.label || p.weekday);
  return `Depart ${dayLab} ${formatHm(p.hour, p.minute)} · parks at that time`;
}
