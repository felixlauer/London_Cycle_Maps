import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  motion,
  useMotionValue,
  useTransform,
  animate,
  useReducedMotion,
} from 'motion/react';
import { availableOverlayModes } from '../../map/overlayModes';
import {
  buildOverlayPillPath,
  overlayPillMetrics,
  armCenterY,
  armExtentForLabel,
  edgeModeForIndex,
} from './overlayPillPath';
import './overlayRail.css';

const EXPAND_SPRING = { type: 'spring', stiffness: 300, damping: 24 };
/** Collapse a bit softer than expand, but not sluggish. */
const COLLAPSE_SPRING = { type: 'spring', stiffness: 240, damping: 26 };
/** How long the T + label stays open before collapsing to the capsule. */
const PEEK_MS = 2400;

/**
 * Overlay mode rail — SVG path morph; brief label peek; mode hub accent.
 * Expand and collapse use the same spring on armExtent (true reverse).
 * Clicking the active icon clears the mode (no peek).
 */
export default function OverlayModeRail({
  activeMode,
  isDark = false,
  inactive = true,
  onSelectMode,
}) {
  const modes = availableOverlayModes(isDark);
  const m = useMemo(() => overlayPillMetrics(modes.length), [modes.length]);
  const reduceMotion = useReducedMotion();
  const instant = { duration: 0.01 };

  /** Opens the T; after PEEK_MS it closes — same spring, extent → 0. */
  const [peek, setPeek] = useState(false);

  const selectedIndex = modes.findIndex((x) => x.id === activeMode);
  const hasSelection = !inactive && selectedIndex >= 0;
  const morphIndex = hasSelection ? selectedIndex : Math.max(0, Math.floor((modes.length - 1) / 2));

  // Edge geometry for the selected row while the arm is open; path builder
  // falls back to a perfect capsule when extent → 0.
  const edgeMode = hasSelection
    ? edgeModeForIndex(selectedIndex, modes.length)
    : 'middle';
  const edgeModeRef = useRef(edgeMode);
  edgeModeRef.current = edgeMode;

  useEffect(() => {
    if (inactive) setPeek(false);
  }, [inactive]);

  const armExtentMv = useMotionValue(0);
  const armCyMv = useMotionValue(armCenterY(morphIndex, m));

  useEffect(() => {
    if (!hasSelection) {
      setPeek(false);
      // Toggle-off: snap capsule shut — no expand/collapse theatre
      armExtentMv.set(0);
    }
  }, [hasSelection, armExtentMv]);

  useEffect(() => {
    if (!peek || inactive || !hasSelection) return undefined;
    const t = window.setTimeout(() => setPeek(false), PEEK_MS);
    return () => window.clearTimeout(t);
  }, [peek, activeMode, inactive, hasSelection]);

  const targetExtent = (peek && hasSelection)
    ? armExtentForLabel(modes[selectedIndex].label, edgeMode)
    : 0;
  const targetCy = armCenterY(morphIndex, m);
  const extentSpring = reduceMotion
    ? instant
    : (targetExtent > 0 ? EXPAND_SPRING : COLLAPSE_SPRING);

  useEffect(() => {
    if (!hasSelection && targetExtent === 0) return undefined;
    const c1 = animate(armExtentMv, targetExtent, extentSpring);
    const c2 = animate(armCyMv, targetCy, extentSpring);
    return () => {
      c1.stop();
      c2.stop();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetExtent, targetCy, reduceMotion, hasSelection]);

  const pathD = useTransform([armExtentMv, armCyMv], ([ext, cy]) =>
    buildOverlayPillPath({
      spineW: m.spineW,
      spineH: m.spineH,
      armExtent: ext,
      armCy: cy,
      armH: m.armH,
      filletR: m.filletR,
      endR: m.cornerR,
      edgeMode: edgeModeRef.current,
    }),
  );

  const labelExtent = hasSelection
    ? armExtentForLabel(modes[selectedIndex].label, edgeMode)
    : 80;
  // Label arrives earlier so it isn’t waiting on the last spring settle
  const fadeStart = Math.max(28, labelExtent * 0.9);
  const fadeEnd = Math.max(fadeStart + 1, labelExtent * 1);
  const labelOpacity = useTransform(
    armExtentMv,
    [0, fadeStart, fadeEnd],
    [0, 0, 1],
  );

  const svgW = m.maxArmExtent + m.spineW;
  const activeLabel = hasSelection ? modes[selectedIndex].label : '';

  const labelStyle = hasSelection
    ? {
      opacity: labelOpacity,
      top: armCenterY(selectedIndex, m) - m.armH / 2,
      height: m.armH,
      width: labelExtent,
      left: -labelExtent,
    }
    : undefined;

  const handleClick = (id) => {
    if (inactive) {
      onSelectMode?.(id);
      return;
    }
    // Toggle off — icon colour only, no expand/collapse
    if (id === activeMode) {
      setPeek(false);
      onSelectMode?.(null);
      return;
    }
    onSelectMode?.(id);
    setPeek(true);
  };

  return (
    <div
      className={`overlay-pill${inactive ? ' is-inactive' : ''}`}
      role="toolbar"
      aria-label="Route overlay modes"
      aria-disabled={inactive || undefined}
      style={{
        width: m.spineW,
        height: m.spineH,
        '--op-arm-max': `${m.maxArmExtent}px`,
      }}
    >
      <svg
        className="overlay-pill__svg"
        width={svgW}
        height={m.spineH}
        viewBox={`${-m.maxArmExtent} 0 ${svgW} ${m.spineH}`}
        aria-hidden
      >
        <motion.path
          className="overlay-pill__path"
          d={pathD}
          fill="var(--shell-bg)"
          stroke="var(--shell-border)"
          strokeWidth={1}
          strokeLinejoin="round"
        />
      </svg>

      {hasSelection && (
        <motion.div
          className="overlay-pill__label"
          style={labelStyle}
          aria-hidden
        >
          <span className="overlay-pill__label-text">{activeLabel}</span>
        </motion.div>
      )}

      <div
        className="overlay-pill__icons"
        style={{ padding: m.pad, gap: m.gap }}
      >
        {modes.map((mode) => {
          const Icon = mode.Icon;
          const selected = hasSelection && mode.id === activeMode;
          return (
            <button
              key={mode.id}
              type="button"
              className={`overlay-pill__btn${selected ? ' is-active' : ''}`}
              style={{
                height: m.btnH,
                ...(selected ? { color: mode.hub } : null),
              }}
              aria-label={mode.label}
              aria-pressed={selected}
              aria-disabled={inactive || undefined}
              onClick={() => handleClick(mode.id)}
            >
              <Icon size={18} strokeWidth={2.25} aria-hidden />
            </button>
          );
        })}
      </div>
    </div>
  );
}
