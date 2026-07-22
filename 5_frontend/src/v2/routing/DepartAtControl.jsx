import React, { useEffect, useMemo, useState } from 'react';
import { Clock, ChevronLeft, ChevronRight, ChevronDown } from 'lucide-react';
import { BLOCKED } from './constants';

const STEP_MIN = 15;
const DAY_COUNT = 7;

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
    out.push({ index: i, label, year: p.year, month: p.month, day: p.day });
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

export function isFutureDepartAt(iso) {
  if (!iso) return false;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return false;
  return t - Date.now() > 30 * 60_000;
}

export function formatDepartStatusHint(mode, iso) {
  if (mode !== 'depart_at' || !iso) return '';
  try {
    const p = londonParts(new Date(iso));
    return `Depart ${p.weekday} ${formatHm(p.hour, p.minute)}`;
  } catch {
    return '';
  }
}

export function useDepartAtControl({
  mode,
  departAtIso,
  onChange,
  disabled,
  onBlocked,
}) {
  const [open, setOpen] = useState(false);
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
    if (disabled) setOpen(false);
  }, [disabled]);

  const emitDepartAt = (nextDay, nextHour, nextMinute) => {
    const clamped = clampToNotBeforeNow(nextDay, nextHour, nextMinute);
    const day = days[nextDay] || days[0];
    const iso = toLondonIso(day.year, day.month, day.day, clamped.hour, clamped.minute);
    setDayIndex(nextDay);
    setHour(clamped.hour);
    setMinute(clamped.minute);
    onChange({ mode: 'depart_at', departAtIso: iso });
  };

  const linkLabel = useMemo(() => {
    if (mode !== 'depart_at' || !departAtIso) return 'Leave now';
    const day = days[dayIndex] || days[0];
    const dayLab = dayIndex === 0 ? 'Today' : day.label;
    return `Depart ${dayLab} ${formatHm(hour, minute)}`;
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

  const toggleOpen = () => {
    if (disabled) {
      onBlocked?.(BLOCKED.departNeedsNoSantander);
      return;
    }
    setOpen((v) => !v);
  };

  const collapse = () => setOpen(false);

  return {
    open,
    disabled,
    linkLabel,
    mode,
    days,
    dayIndex,
    hour,
    minute,
    toggleOpen,
    collapse,
    onChange,
    emitDepartAt,
    nudgeDay,
    nudgeTime,
  };
}

export function DepartAtTrigger({
  linkLabel,
  open,
  disabled,
  onToggle,
}) {
  return (
    <button
      type="button"
      className="rc-textlink rc-depart__trigger"
      aria-expanded={open}
      aria-disabled={disabled}
      onClick={onToggle}
    >
      <Clock size={14} strokeWidth={2.2} aria-hidden />
      <span>{linkLabel}</span>
      <ChevronDown
        size={13}
        strokeWidth={2.2}
        className={`rc-depart__chevron${open ? ' is-open' : ''}`}
        aria-hidden
      />
    </button>
  );
}

export function DepartAtPanel({
  mode,
  days,
  dayIndex,
  hour,
  minute,
  onChange,
  emitDepartAt,
  nudgeDay,
  nudgeTime,
}) {
  return (
    <div className="rc-depart__inline">
      <div className="rc-depart__seg" role="tablist">
        <button
          type="button"
          className={mode === 'now' ? 'is-active' : ''}
          onClick={() => onChange({ mode: 'now', departAtIso: null })}
        >
          Leave now
        </button>
        <button
          type="button"
          className={mode === 'depart_at' ? 'is-active' : ''}
          onClick={() => {
            const slot = defaultDepartSlot();
            emitDepartAt(slot.dayIndex, slot.hour, slot.minute);
          }}
        >
          Depart at
        </button>
      </div>
      {mode === 'depart_at' && (
        <div className="rc-depart__pickers">
          <div className="rc-depart__row">
            <button type="button" onClick={() => nudgeDay(-1)} aria-label="Previous day">
              <ChevronLeft size={15} strokeWidth={2} />
            </button>
            <span>{days[dayIndex]?.label || 'Today'}</span>
            <button type="button" onClick={() => nudgeDay(1)} aria-label="Next day">
              <ChevronRight size={15} strokeWidth={2} />
            </button>
          </div>
          <div className="rc-depart__row">
            <button type="button" onClick={() => nudgeTime(-1)} aria-label="Earlier">
              <ChevronLeft size={15} strokeWidth={2} />
            </button>
            <span className="rc-depart__time">{formatHm(hour, minute)}</span>
            <button type="button" onClick={() => nudgeTime(1)} aria-label="Later">
              <ChevronRight size={15} strokeWidth={2} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Stacked layout — trigger above inline panel (legacy wrapper).
 */
export default function DepartAtControl(props) {
  const depart = useDepartAtControl(props);

  return (
    <div className={`rc-depart${depart.disabled ? ' is-disabled' : ''}`}>
      <DepartAtTrigger
        linkLabel={depart.linkLabel}
        open={depart.open}
        disabled={depart.disabled}
        onToggle={depart.toggleOpen}
      />
      {depart.open && !depart.disabled && (
        <DepartAtPanel {...depart} />
      )}
    </div>
  );
}
