import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Clock, ChevronLeft, ChevronRight, ChevronDown } from 'lucide-react';
import { BLOCKED } from './constants';
import { formatDepartHm, maskTimeDigits, parseDepartTime } from './departTime';

const STEP_MIN = 15;
const DAY_COUNT = 7;
const TIME_COMMIT_MS = 280;

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

function clampToNotBeforeNow(dayIndex, hour, minute, step = 1) {
  if (dayIndex !== 0) return { hour, minute };
  const now = londonParts();
  const nowTotal = now.hour * 60 + now.minute;
  let total = hour * 60 + minute;
  if (total < nowTotal) {
    total = roundUpToStep(nowTotal, step);
    if (total >= 24 * 60) return { hour: 23, minute: 59 };
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
  return formatDepartHm(hour, minute);
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
      const clamped = clampToNotBeforeNow(dayIndex, p.hour, p.minute);
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
  const [timeText, setTimeText] = useState(() => formatHm(slotFromIso.hour, slotFromIso.minute));
  const [timeFocused, setTimeFocused] = useState(false);
  const timeFocusedRef = useRef(false);
  const timeCommitRef = useRef(null);
  const timeEnterCommittedRef = useRef(false);
  const dayIndexRef = useRef(slotFromIso.dayIndex);
  const hourRef = useRef(slotFromIso.hour);
  const minuteRef = useRef(slotFromIso.minute);

  useEffect(() => {
    setDayIndex(slotFromIso.dayIndex);
    setHour(slotFromIso.hour);
    setMinute(slotFromIso.minute);
    dayIndexRef.current = slotFromIso.dayIndex;
    hourRef.current = slotFromIso.hour;
    minuteRef.current = slotFromIso.minute;
    if (!timeFocusedRef.current) {
      setTimeText(formatHm(slotFromIso.hour, slotFromIso.minute));
    }
  }, [slotFromIso.dayIndex, slotFromIso.hour, slotFromIso.minute]);

  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  useEffect(() => () => {
    if (timeCommitRef.current) clearTimeout(timeCommitRef.current);
  }, []);

  const emitDepartAt = (nextDay, nextHour, nextMinute, step = 1) => {
    const clamped = clampToNotBeforeNow(nextDay, nextHour, nextMinute, step);
    const day = days[nextDay] || days[0];
    const iso = toLondonIso(day.year, day.month, day.day, clamped.hour, clamped.minute);
    setDayIndex(nextDay);
    setHour(clamped.hour);
    setMinute(clamped.minute);
    dayIndexRef.current = nextDay;
    hourRef.current = clamped.hour;
    minuteRef.current = clamped.minute;
    if (!timeFocusedRef.current) setTimeText(formatHm(clamped.hour, clamped.minute));
    onChange({ mode: 'depart_at', departAtIso: iso });
    return clamped;
  };

  const applyParsedTime = (raw, { revert = false } = {}) => {
    const parsed = parseDepartTime(raw);
    if (!parsed) {
      if (revert) setTimeText(formatHm(hour, minute));
      return false;
    }
    // When the typed time is before London now, clamp forward to the next 15-min slot.
    // For future times, the step does not affect the minute.
    const clamped = emitDepartAt(dayIndex, parsed.hour, parsed.minute, STEP_MIN);
    setTimeText(formatHm(clamped.hour, clamped.minute));
    return true;
  };

  const handleTimeText = (next) => {
    const masked = maskTimeDigits(next);
    setTimeText(masked);
    if (timeCommitRef.current) clearTimeout(timeCommitRef.current);
    const digits = masked.replace(/\D/g, '');
    if (digits.length !== 4) return;
    const parsed = parseDepartTime(masked, { hourOnlyOnShort: false });
    if (!parsed) return;
    timeCommitRef.current = setTimeout(() => {
      timeCommitRef.current = null;
      emitDepartAt(dayIndex, parsed.hour, parsed.minute, STEP_MIN);
    }, TIME_COMMIT_MS);
  };

  const onTimeFocus = (e) => {
    timeFocusedRef.current = true;
    setTimeFocused(true);
    e.target.select();
  };

  const onTimeBlur = () => {
    const revert = !timeEnterCommittedRef.current;
    timeEnterCommittedRef.current = false;
    timeFocusedRef.current = false;
    setTimeFocused(false);
    if (timeCommitRef.current) {
      clearTimeout(timeCommitRef.current);
      timeCommitRef.current = null;
    }
    applyParsedTime(timeText, { revert });
  };

  const onTimeKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      timeEnterCommittedRef.current = true;
      // If the draft is incomplete/invalid, keep it as-is instead of snapping back.
      applyParsedTime(timeText, { revert: false });
      e.currentTarget.blur();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setTimeText(formatHm(hour, minute));
      e.currentTarget.blur();
    }
  };

  const commitDraft = () => {
    if (!timeFocusedRef.current) return;
    if (timeCommitRef.current) {
      clearTimeout(timeCommitRef.current);
      timeCommitRef.current = null;
    }
    timeFocusedRef.current = false;
    setTimeFocused(false);
    applyParsedTime(timeText, { revert: true });
  };

  const linkLabel = useMemo(() => {
    if (mode !== 'depart_at' || !departAtIso) return 'Leave now';
    const day = days[dayIndex] || days[0];
    const dayLab = dayIndex === 0 ? 'Today' : day.label;
    return `Depart ${dayLab} ${formatHm(hour, minute)}`;
  }, [mode, departAtIso, days, dayIndex, hour, minute]);

  const nudgeTime = (dir) => {
    commitDraft();
    const baseTotal = hourRef.current * 60 + minuteRef.current;
    const rem = baseTotal % STEP_MIN;
    // Chevron rules:
    // - If already on a 15-min slot, +/- moves to the next/previous slot.
    // - If not on a slot, +/- moves to the nearest upcoming/past slot.
    let total;
    if (dir > 0) {
      total = rem === 0 ? baseTotal + STEP_MIN : Math.ceil(baseTotal / STEP_MIN) * STEP_MIN;
    } else {
      total = rem === 0 ? baseTotal - STEP_MIN : Math.floor(baseTotal / STEP_MIN) * STEP_MIN;
    }
    let nextDay = dayIndexRef.current;
    if (total < 0) {
      if (nextDay === 0) {
        emitDepartAt(0, 0, 0, STEP_MIN);
        return;
      }
      nextDay -= 1;
      total += 24 * 60;
    } else if (total >= 24 * 60) {
      if (nextDay >= DAY_COUNT - 1) {
        emitDepartAt(nextDay, 23, 45, STEP_MIN);
        return;
      }
      nextDay += 1;
      total -= 24 * 60;
    }
    emitDepartAt(nextDay, Math.floor(total / 60), total % 60, STEP_MIN);
  };

  const nudgeDay = (dir) => {
    commitDraft();
    const next = Math.max(0, Math.min(DAY_COUNT - 1, dayIndexRef.current + dir));
    emitDepartAt(next, hourRef.current, minuteRef.current, STEP_MIN);
  };

  const toggleOpen = () => {
    if (disabled) {
      onBlocked?.(BLOCKED.departNeedsNoSantander);
      return;
    }
    if (open) commitDraft();
    setOpen((v) => !v);
  };

  const collapse = () => {
    commitDraft();
    setOpen(false);
  };

  return {
    open,
    disabled,
    linkLabel,
    mode,
    days,
    dayIndex,
    hour,
    minute,
    timeText,
    timeFocused,
    toggleOpen,
    collapse,
    commitDraft,
    onChange,
    emitDepartAt,
    nudgeDay,
    nudgeTime,
    handleTimeText,
    onTimeFocus,
    onTimeBlur,
    onTimeKeyDown,
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
  timeText,
  onChange,
  emitDepartAt,
  nudgeDay,
  nudgeTime,
  handleTimeText,
  onTimeFocus,
  onTimeBlur,
  onTimeKeyDown,
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
            emitDepartAt(slot.dayIndex, slot.hour, slot.minute, STEP_MIN);
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
            <input
              className="rc-depart__time rc-depart__time-input"
              type="text"
              inputMode="numeric"
              autoComplete="off"
              spellCheck="false"
              maxLength={5}
              aria-label="Departure time, 24-hour"
              placeholder="HH:MM"
              value={timeText}
              onChange={(e) => handleTimeText(e.target.value)}
              onFocus={onTimeFocus}
              onBlur={onTimeBlur}
              onKeyDown={onTimeKeyDown}
            />
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
