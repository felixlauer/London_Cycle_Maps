import { useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { ChevronDown, ChevronLeft, ChevronRight, Clock } from 'lucide-react-native';
import { BLOCKED } from '../routing/constants';
import { useChrome } from '../theme/useChrome';
import { formatDepartHm, maskTimeDigits, parseDepartTime } from './departTime';

const STEP_MIN = 15;
const DAY_COUNT = 7;
const TIME_COMMIT_MS = 280;

export type DepartMode = 'now' | 'depart_at';

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

function londonOffsetMinutes(approxDate: Date) {
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

function dateFromLondonLocal(year: number, month: number, day: number, hour: number, minute: number) {
  const utcGuess = Date.UTC(year, month - 1, day, hour, minute, 0);
  const off = londonOffsetMinutes(new Date(utcGuess));
  return new Date(utcGuess - off * 60_000);
}

function roundUpToStep(minute: number, step = STEP_MIN) {
  return Math.ceil(minute / step) * step;
}

function clampToNotBeforeNow(dayIndex: number, hour: number, minute: number, step = 1) {
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
  const out: { index: number; label: string; year: number; month: number; day: number }[] = [];
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

function formatHm(hour: number, minute: number) {
  return formatDepartHm(hour, minute);
}

function toLondonIso(year: number, month: number, day: number, hour: number, minute: number) {
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

export function useDepartAtControl({
  mode,
  departAtIso,
  onChange,
  disabled,
  onBlocked,
}: {
  mode: DepartMode;
  departAtIso: string | null;
  onChange: (next: { mode: DepartMode; departAtIso: string | null }) => void;
  disabled?: boolean;
  onBlocked?: (msg: string) => void;
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
  const timeFocusedRef = useRef(false);
  const timeCommitRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const timeSubmitCommittedRef = useRef(false);
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

  const emitDepartAt = (nextDay: number, nextHour: number, nextMinute: number, step = 1) => {
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

  const applyParsedTime = (raw: string, { revert = false } = {}) => {
    const parsed = parseDepartTime(raw);
    if (!parsed) {
      if (revert) setTimeText(formatHm(hour, minute));
      return false;
    }
    // When typed time is before London now, clamp forward to the next 15-min slot.
    const clamped = emitDepartAt(dayIndex, parsed.hour, parsed.minute, STEP_MIN);
    setTimeText(formatHm(clamped.hour, clamped.minute));
    return true;
  };

  const handleTimeText = (next: string) => {
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

  const onTimeFocus = () => {
    timeFocusedRef.current = true;
  };

  const onTimeBlur = () => {
    const revert = !timeSubmitCommittedRef.current;
    timeSubmitCommittedRef.current = false;
    timeFocusedRef.current = false;
    if (timeCommitRef.current) {
      clearTimeout(timeCommitRef.current);
      timeCommitRef.current = null;
    }
    applyParsedTime(timeText, { revert });
  };

  const commitDraft = () => {
    if (!timeFocusedRef.current) return;
    if (timeCommitRef.current) {
      clearTimeout(timeCommitRef.current);
      timeCommitRef.current = null;
    }
    timeFocusedRef.current = false;
    applyParsedTime(timeText, { revert: true });
  };

  const linkLabel = useMemo(() => {
    if (mode !== 'depart_at' || !departAtIso) return 'Leave now';
    const day = days[dayIndex] || days[0];
    const dayLab = dayIndex === 0 ? 'Today' : day.label;
    return `Depart ${dayLab} ${formatHm(hour, minute)}`;
  }, [mode, departAtIso, days, dayIndex, hour, minute]);

  const nudgeTime = (dir: number) => {
    commitDraft();
    const baseTotal = hourRef.current * 60 + minuteRef.current;
    const rem = baseTotal % STEP_MIN;
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

  const nudgeDay = (dir: number) => {
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

  return {
    open,
    disabled: !!disabled,
    linkLabel,
    mode,
    days,
    dayIndex,
    hour,
    minute,
    timeText,
    toggleOpen,
    collapse: () => {
      commitDraft();
      setOpen(false);
    },
    commitDraft,
    onChange,
    emitDepartAt,
    nudgeDay,
    nudgeTime,
    handleTimeText,
    onTimeFocus,
    onTimeBlur,
  };
}

export function DepartAtTrigger({
  linkLabel,
  open,
  disabled,
  onToggle,
}: {
  linkLabel: string;
  open: boolean;
  disabled?: boolean;
  onToggle: () => void;
}) {
  const { c } = useChrome();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ expanded: open, disabled: !!disabled }}
      onPress={onToggle}
      style={({ pressed }) => [
        styles.trigger,
        disabled && styles.disabled,
        pressed && !disabled && { opacity: 0.75 },
      ]}
    >
      <Clock size={14} strokeWidth={2.2} color={c.textSub} />
      <Text style={[styles.triggerText, { color: c.textSub }]}>{linkLabel}</Text>
      <ChevronDown
        size={13}
        strokeWidth={2.2}
        color={c.textSub}
        style={open ? styles.chevOpen : undefined}
      />
    </Pressable>
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
}: ReturnType<typeof useDepartAtControl>) {
  const { c } = useChrome();
  return (
    <View style={styles.panel}>
      <View style={[styles.seg, { backgroundColor: c.inset, borderColor: c.line }]}>
        <Pressable
          onPress={() => onChange({ mode: 'now', departAtIso: null })}
          style={[styles.segBtn, mode === 'now' && { backgroundColor: c.surface }]}
        >
          <Text style={[styles.segText, { color: c.textSub }, mode === 'now' && { color: c.text }]}>Leave now</Text>
        </Pressable>
        <Pressable
          onPress={() => {
            const slot = defaultDepartSlot();
            emitDepartAt(slot.dayIndex, slot.hour, slot.minute, STEP_MIN);
          }}
          style={[styles.segBtn, mode === 'depart_at' && { backgroundColor: c.surface }]}
        >
          <Text style={[styles.segText, { color: c.textSub }, mode === 'depart_at' && { color: c.text }]}>Depart at</Text>
        </Pressable>
      </View>
      {mode === 'depart_at' && (
        <View style={styles.pickers}>
          <View style={[styles.row, { backgroundColor: c.inset, borderColor: c.line }]}>
            <Pressable onPress={() => nudgeDay(-1)} hitSlop={8} style={styles.nudge}>
              <ChevronLeft size={15} strokeWidth={2} color={c.text} />
            </Pressable>
            <Text style={[styles.rowLabel, { color: c.text }]} numberOfLines={1}>{days[dayIndex]?.label || 'Today'}</Text>
            <Pressable onPress={() => nudgeDay(1)} hitSlop={8} style={styles.nudge}>
              <ChevronRight size={15} strokeWidth={2} color={c.text} />
            </Pressable>
          </View>
          <View style={[styles.row, { backgroundColor: c.inset, borderColor: c.line }]}>
            <Pressable onPress={() => nudgeTime(-1)} hitSlop={8} style={styles.nudge}>
              <ChevronLeft size={15} strokeWidth={2} color={c.text} />
            </Pressable>
            <TextInput
              value={timeText}
              onChangeText={handleTimeText}
              onFocus={onTimeFocus}
              onBlur={onTimeBlur}
              onSubmitEditing={() => {
                timeSubmitCommittedRef.current = true;
                onTimeBlur();
              }}
              keyboardType="number-pad"
              inputMode="numeric"
              returnKeyType="done"
              maxLength={5}
              selectTextOnFocus
              placeholder="HH:MM"
              placeholderTextColor={c.textSub}
              accessibilityLabel="Departure time, 24-hour"
              allowFontScaling={false}
              style={[styles.timeInput, { color: c.text }]}
            />
            <Pressable onPress={() => nudgeTime(1)} hitSlop={8} style={styles.nudge}>
              <ChevronRight size={15} strokeWidth={2} color={c.text} />
            </Pressable>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  trigger: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 4,
    paddingHorizontal: 5,
    borderRadius: 6,
  },
  triggerText: {
    fontSize: 12.5,
    fontWeight: '600',
  },
  chevOpen: { transform: [{ rotate: '180deg' }] },
  disabled: { opacity: 0.45 },
  panel: {
    gap: 10,
    paddingTop: 2,
  },
  seg: {
    flexDirection: 'row',
    gap: 6,
    borderRadius: 10,
    padding: 3,
    borderWidth: 1,
  },
  segBtn: {
    flex: 1,
    paddingVertical: 8,
    borderRadius: 8,
    alignItems: 'center',
  },
  segText: {
    fontSize: 12.5,
    fontWeight: '600',
  },
  pickers: { gap: 5 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderRadius: 10,
    borderWidth: 1,
    paddingVertical: 6,
    paddingHorizontal: 8,
    minWidth: 0,
  },
  rowLabel: {
    flex: 1,
    fontSize: 13,
    fontWeight: '600',
    textAlign: 'center',
  },
  timeInput: {
    flex: 1,
    minWidth: 56,
    height: 32,
    paddingVertical: 0,
    paddingHorizontal: 4,
    fontSize: 13,
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
    textAlign: 'center',
  },
  nudge: {
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
