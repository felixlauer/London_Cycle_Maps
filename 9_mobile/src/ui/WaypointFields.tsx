import { Fragment, useMemo, useRef, useState } from 'react';
import {
  PanResponder,
  Pressable,
  StyleSheet,
  Text,
  View,
  type GestureResponderEvent,
  type PanResponderGestureState,
} from 'react-native';
import { Circle, Equal, MapPin, X } from 'lucide-react-native';
import type { LatLon } from '../lib/coords';
import type { ViaPoint } from '../routing/constants';
import { useChrome } from '../theme/useChrome';
import { LocationSearchInput } from './LocationSearchInput';

export type PickTarget = 'start' | 'end' | `via:${number}` | null;

export type WaypointChange = {
  start: LatLon | null;
  startLabel: string;
  end: LatLon | null;
  endLabel: string;
  vias: ViaPoint[];
};

type ListItem = {
  id: string;
  role: 'start' | 'via' | 'end';
  coord: LatLon | null;
  label: string;
};

const ROW_H = 45;
const ROW_H_COMPACT = 36;
const DIVIDER_H = StyleSheet.hairlineWidth;

export function toWaypointList(
  start: LatLon | null,
  startLabel: string,
  vias: ViaPoint[],
  end: LatLon | null,
  endLabel: string,
): ListItem[] {
  return [
    { id: 'start', role: 'start', coord: start, label: startLabel || '' },
    ...vias.map((v, i) => ({
      id: v.id || `via-${i}`,
      role: 'via' as const,
      coord: v.coord,
      label: v.label || '',
    })),
    { id: 'end', role: 'end', coord: end, label: endLabel || '' },
  ];
}

export function fromWaypointList(list: ListItem[]): WaypointChange {
  const first = list[0];
  const last = list[list.length - 1];
  const middle = list.slice(1, -1);
  return {
    start: first.coord,
    startLabel: first.label,
    end: last.coord,
    endLabel: last.label,
    vias: middle.map((w, i) => ({
      id: w.id.startsWith('via') ? w.id : `via-${i}-${Date.now()}`,
      coord: w.coord,
      label: w.label,
    })),
  };
}

function letterAt(index: number) {
  return String.fromCharCode(65 + index);
}

function SlotIcon({ role, letter }: { role: string; letter: string }) {
  const { c } = useChrome();
  if (role === 'start') {
    return <Circle size={15} strokeWidth={2.2} color={c.icon} />;
  }
  if (role === 'end') {
    return <MapPin size={16} strokeWidth={2.2} color={c.icon} />;
  }
  return (
    <View style={styles.viaLetter}>
      <Text style={styles.viaLetterText}>{letter}</Text>
    </View>
  );
}

function strideFor(compact: boolean) {
  return (compact ? ROW_H_COMPACT : ROW_H) + DIVIDER_H;
}

function clampDy(from: number, dy: number, count: number, stride: number) {
  const maxUp = -from * stride;
  const maxDown = (count - 1 - from) * stride;
  return Math.max(maxUp, Math.min(maxDown, dy));
}

function overIndexFor(from: number, dy: number, count: number, stride: number) {
  const clamped = clampDy(from, dy, count, stride);
  return Math.max(0, Math.min(count - 1, Math.round(from + clamped / stride)));
}

type Props = {
  start: LatLon | null;
  end: LatLon | null;
  startLabel: string;
  endLabel: string;
  vias: ViaPoint[];
  onChangeWaypoints: (next: WaypointChange) => void;
  onRemoveVia: (viaIndex: number) => void;
  onFlyTo?: (coord: LatLon) => void;
  onMapPickTargetChange?: (t: PickTarget) => void;
  viasCollapsed?: boolean;
  onExpandVias?: () => void;
  startPlaceholder?: string;
  endPlaceholder?: string;
};

type DragState = {
  from: number;
  dy: number;
  over: number;
};

/**
 * Apple Maps-style waypoint card — web WaypointFields (search + vias + grip).
 * Grip: vertical-only drag reorder, clamped inside the card.
 */
export function WaypointFields({
  start,
  end,
  startLabel,
  endLabel,
  vias,
  onChangeWaypoints,
  onRemoveVia,
  onFlyTo,
  onMapPickTargetChange,
  viasCollapsed = false,
  onExpandVias,
  startPlaceholder,
  endPlaceholder,
}: Props) {
  const { c } = useChrome();
  const list = toWaypointList(start, startLabel, vias, end, endLabel);
  const viaCount = (vias || []).length;
  const hideVias = viasCollapsed && viaCount > 0;
  const [drag, setDrag] = useState<DragState | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const listRef = useRef(list);
  const hideViasRef = useRef(hideVias);
  const onChangeRef = useRef(onChangeWaypoints);
  listRef.current = list;
  hideViasRef.current = hideVias;
  onChangeRef.current = onChangeWaypoints;

  const visible = hideVias
    ? [
      { wp: list[0], index: 0 },
      { wp: list[list.length - 1], index: list.length - 1 },
    ]
    : list.map((wp, index) => ({ wp, index }));

  const reorderCount = hideVias ? 2 : list.length;
  const stride = strideFor(hideVias);
  const reorderCountRef = useRef(reorderCount);
  const strideRef = useRef(stride);
  reorderCountRef.current = reorderCount;
  strideRef.current = stride;

  const setPickTarget = (role: PickTarget) => {
    onMapPickTargetChange?.(role);
  };

  /**
   * Keep the map-pick target after blur. On Android the first tap outside a
   * focused TextInput only dismisses the keyboard — if we cleared pickTarget
   * on blur, that tap never places a pin (needs two tries).
   * Target clears when another field focuses or a pin is placed.
   */
  const handleFieldFocusChange = (roleDisplay: string, index: number, focused: boolean) => {
    if (focused) setPickTarget(pickTargetFor(roleDisplay, index));
  };

  const applyReorder = (fromVisible: number, toVisible: number) => {
    if (fromVisible == null || toVisible == null || fromVisible === toVisible) return;
    const current = listRef.current;
    const collapsed = hideViasRef.current;
    if (collapsed) {
      // Only start ↔ end while vias are collapsed.
      if (
        (fromVisible === 0 && toVisible === 1)
        || (fromVisible === 1 && toVisible === 0)
      ) {
        const next = [...current];
        const tmp = next[0];
        next[0] = next[next.length - 1];
        next[next.length - 1] = tmp;
        onChangeRef.current(fromWaypointList(next));
      }
      return;
    }
    const next = [...current];
    const [item] = next.splice(fromVisible, 1);
    next.splice(toVisible, 0, item);
    onChangeRef.current(fromWaypointList(next));
  };

  const applyReorderRef = useRef(applyReorder);
  applyReorderRef.current = applyReorder;

  const updateAt = (index: number, { lat, lon, label }: { lat: number; lon: number; label: string }) => {
    const next = list.map((w, i) =>
      i === index
        ? { ...w, coord: [lat, lon] as LatLon, label: label || `${lat.toFixed(4)}, ${lon.toFixed(4)}` }
        : w,
    );
    onChangeWaypoints(fromWaypointList(next));
    onFlyTo?.([lat, lon]);
  };

  const clearAt = (index: number) => {
    const next = list.map((w, i) =>
      i === index ? { ...w, coord: null, label: '' } : w,
    );
    onChangeWaypoints(fromWaypointList(next));
  };

  const pickTargetFor = (roleDisplay: string, index: number): PickTarget => {
    if (roleDisplay === 'start') return 'start';
    if (roleDisplay === 'end') return 'end';
    return `via:${index - 1}`;
  };

  const gripHandlers = useMemo(() => {
    const make = (visibleIndex: number) => PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: (_e: GestureResponderEvent, g: PanResponderGestureState) => (
        Math.abs(g.dy) > 4 && Math.abs(g.dy) > Math.abs(g.dx) * 1.1
      ),
      onPanResponderTerminationRequest: () => false,
      onShouldBlockNativeResponder: () => true,
      onPanResponderGrant: () => {
        const next = { from: visibleIndex, dy: 0, over: visibleIndex };
        dragRef.current = next;
        setDrag(next);
      },
      onPanResponderMove: (_e, g) => {
        // Vertical only — ignore dx entirely.
        const count = reorderCountRef.current;
        const step = strideRef.current;
        const dy = clampDy(visibleIndex, g.dy, count, step);
        const over = overIndexFor(visibleIndex, dy, count, step);
        const next = { from: visibleIndex, dy, over };
        dragRef.current = next;
        setDrag(next);
      },
      onPanResponderRelease: (_e, g) => {
        const count = reorderCountRef.current;
        const step = strideRef.current;
        const dy = clampDy(visibleIndex, g.dy, count, step);
        const over = overIndexFor(visibleIndex, dy, count, step);
        applyReorderRef.current(visibleIndex, over);
        dragRef.current = null;
        setDrag(null);
      },
      onPanResponderTerminate: () => {
        dragRef.current = null;
        setDrag(null);
      },
    }).panHandlers;
    return Array.from({ length: Math.max(reorderCount, 2) }, (_, i) => make(i));
  }, [reorderCount, stride]);

  const renderRow = (
    wp: ListItem,
    listIndex: number,
    visibleIndex: number,
    compact = false,
  ) => {
    const isVia = listIndex > 0 && listIndex < list.length - 1;
    const roleDisplay = listIndex === 0 ? 'start' : listIndex === list.length - 1 ? 'end' : 'via';
    const letter = letterAt(listIndex);
    const viaPlaceholder = `Stop ${letter} or tap the map`;
    const isFilled = Boolean(wp.coord) || Boolean(String(wp.label || '').trim());
    const isDragging = drag?.from === visibleIndex;
    const isDropTarget = Boolean(
      drag && drag.over === visibleIndex && drag.from !== visibleIndex,
    );

    return (
      <Fragment key={wp.id}>
        {visibleIndex > 0 && <View style={[styles.divider, { backgroundColor: c.line }]} />}
        <View
          style={[
            styles.row,
            { backgroundColor: c.inset },
            compact && styles.rowCompact,
            isDropTarget && { backgroundColor: c.surface },
            isDragging && styles.rowDragging,
            isDragging && { transform: [{ translateY: drag!.dy }] },
          ]}
        >
          <SlotIcon role={roleDisplay} letter={letter} />
          <View style={[styles.inputWrap, compact && styles.inputWrapCompact]}>
            <LocationSearchInput
              value={wp.label}
              compact={compact}
              placeholder={
                roleDisplay === 'start'
                  ? (startPlaceholder || 'Search start or tap the map')
                  : roleDisplay === 'end'
                    ? (endPlaceholder || 'Search destination or tap the map')
                    : viaPlaceholder
              }
              onSelect={({ lat, lon, label }) => updateAt(listIndex, { lat, lon, label })}
              onClear={() => clearAt(listIndex)}
              onFocusChange={(focused) => {
                handleFieldFocusChange(roleDisplay, listIndex, focused);
              }}
            />
          </View>
          {isVia && !isFilled && (
            <Pressable
              accessibilityLabel="Remove stop"
              onPress={() => onRemoveVia(listIndex - 1)}
              style={({ pressed }) => [styles.remove, pressed && { backgroundColor: c.surface }]}
              hitSlop={6}
            >
              <X size={14} strokeWidth={2.2} color={c.textSub} />
            </Pressable>
          )}
          {isFilled && (
            <Pressable
              accessibilityLabel="Clear location"
              onPress={() => clearAt(listIndex)}
              style={({ pressed }) => [styles.clear, pressed && { backgroundColor: c.surface }]}
              hitSlop={6}
            >
              <X size={14} strokeWidth={2.2} color={c.textSub} />
            </Pressable>
          )}
          <View
            style={[styles.grip, isDragging && styles.gripActive]}
            accessibilityLabel="Reorder stop"
            accessibilityRole="adjustable"
            {...(gripHandlers[visibleIndex] || {})}
          >
            <Equal size={16} strokeWidth={2} color={c.icon} />
          </View>
        </View>
      </Fragment>
    );
  };

  return (
    <View style={styles.waypoints}>
      {hideVias ? (
        <View style={[styles.cardHidden, { backgroundColor: c.inset, borderColor: c.line }, drag && styles.cardDragging]}>
          {visible.map(({ wp, index }, vi) => renderRow(wp, index, vi, true))}
          <View style={styles.hiddenOverlay} pointerEvents="box-none">
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Show ${viaCount} hidden stop${viaCount === 1 ? '' : 's'}`}
              onPress={() => onExpandVias?.()}
              style={({ pressed }) => [
                styles.hiddenPill,
                { borderColor: c.line, backgroundColor: c.surface },
                pressed && { opacity: 0.85 },
              ]}
              hitSlop={8}
            >
              <Text style={[styles.hiddenPillText, { color: c.text }]}>
                {viaCount} stop{viaCount === 1 ? '' : 's'} hidden
              </Text>
            </Pressable>
          </View>
        </View>
      ) : (
        <View style={[styles.card, { backgroundColor: c.inset, borderColor: c.line }, drag && styles.cardDragging]}>
          {visible.map(({ wp, index }, vi) => renderRow(wp, index, vi))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  waypoints: {
    flexDirection: 'column',
  },
  card: {
    borderRadius: 11,
    borderWidth: 1,
    overflow: 'hidden',
    zIndex: 2,
  },
  cardDragging: {
    // Keep the floating row inside the start/destination box.
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
    height: ROW_H,
    paddingLeft: 11,
    paddingRight: 9,
    zIndex: 1,
  },
  rowCompact: {
    height: ROW_H_COMPACT,
  },
  rowDragging: {
    zIndex: 8,
    elevation: 6,
    opacity: 0.96,
    shadowColor: '#000',
    shadowOpacity: 0.18,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
  },
  rowDropTarget: {},
  inputWrap: {
    flex: 1,
    minWidth: 0,
    zIndex: 20,
  },
  /** Collapsed vias — don’t outrank the hidden-stops pill. */
  inputWrapCompact: {
    zIndex: 1,
  },
  divider: {
    height: DIVIDER_H,
    marginLeft: 38,
  },
  viaLetter: {
    width: 18,
    height: 18,
    borderRadius: 999,
    backgroundColor: '#52525B',
    alignItems: 'center',
    justifyContent: 'center',
  },
  viaLetterText: {
    fontSize: 10,
    fontWeight: '700',
    color: '#fff',
    lineHeight: 11,
    textAlign: 'center',
    includeFontPadding: false,
    textAlignVertical: 'center',
    marginTop: 0.5,
  },
  remove: {
    width: 28,
    height: 28,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  clear: {
    width: 28,
    height: 28,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  grip: {
    width: 28,
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    opacity: 0.55,
  },
  gripActive: {
    opacity: 1,
  },
  cardHidden: {
    position: 'relative',
    borderRadius: 11,
    borderWidth: 1,
    overflow: 'hidden',
    zIndex: 2,
  },
  /** Covers the right ~⅔ (web left: 66.666%). High zIndex so taps beat inputWrap. */
  hiddenOverlay: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    left: '33%',
    right: 0,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 40,
    elevation: 8,
  },
  hiddenPill: {
    paddingVertical: 5,
    paddingHorizontal: 14,
    borderRadius: 999,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  hiddenPillText: {
    fontSize: 11.5,
    fontWeight: '600',
  },
});
