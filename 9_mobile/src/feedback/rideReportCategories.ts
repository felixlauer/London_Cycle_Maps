/**
 * The four circles the rider can hit, plus the timeout fallback.
 *
 * Derived from the overlay rail and the cost function, not invented: each
 * category maps onto a weight that already exists, so a tap has somewhere to go.
 * Attractions and hills are deliberately absent (not defects / LIDAR is better),
 * and traffic jams stay with TomTom.
 */
import { Car, Fence, Globe, LightbulbOff, TriangleAlert } from 'lucide-react-native';
import type { LucideIcon } from 'lucide-react-native';

export type RideReportCategoryId =
  | 'surface'
  | 'dangerous'
  | 'impassable'
  | 'speeding'
  | 'unlit'
  | 'general';

export type RideReportCategory = {
  id: RideReportCategoryId;
  /** Screen reader + alert pill. Longer than the caption under the circle. */
  label: string;
  /** Caption under the circle. Always shown. */
  shortLabel: string;
  hub: string;
  Icon: LucideIcon;
  /** Glyph on the filled circle. Banana is too light for white. */
  onHub: string;
};

const WHITE = '#FFFFFF';
const NEAR_BLACK = '#18181B';

export const RIDE_REPORT_CATEGORIES: Record<
  Exclude<RideReportCategoryId, 'general'>,
  RideReportCategory
> = {
  surface: {
    id: 'surface',
    label: 'Bad surface',
    shortLabel: 'Surface',
    hub: '#13C2A4',
    Icon: Globe,
    onHub: WHITE,
  },
  dangerous: {
    id: 'dangerous',
    label: 'Dangerous situation',
    shortLabel: 'Danger',
    hub: '#FF0061',
    Icon: TriangleAlert,
    onHub: WHITE,
  },
  impassable: {
    id: 'impassable',
    label: 'Impassable',
    shortLabel: 'Impassable',
    hub: '#4D9DE0',
    Icon: Fence,
    onHub: WHITE,
  },
  speeding: {
    id: 'speeding',
    label: 'Speeding',
    shortLabel: 'Speeding',
    hub: '#8717BF',
    Icon: Car,
    onHub: WHITE,
  },
  unlit: {
    id: 'unlit',
    label: 'Unlit',
    shortLabel: 'Unlit',
    hub: '#FDE74C',
    Icon: LightbulbOff,
    onHub: NEAR_BLACK,
  },
};

/** Slots 1-3 never change, day or night. */
export const FIXED_SLOTS: RideReportCategory[] = [
  RIDE_REPORT_CATEGORIES.surface,
  RIDE_REPORT_CATEGORIES.dangerous,
  RIDE_REPORT_CATEGORIES.impassable,
];

/**
 * Slot 4 follows the lighting gate (/night_status), not the UI theme — same
 * rule as the Light overlay. There is deliberately no fifth circle: after dark
 * lighting matters more than street character.
 */
export function slotFour(isDark: boolean): RideReportCategory {
  return isDark ? RIDE_REPORT_CATEGORIES.unlit : RIDE_REPORT_CATEGORIES.speeding;
}

export function reportSlots(isDark: boolean): RideReportCategory[] {
  return [...FIXED_SLOTS, slotFour(isDark)];
}

/** Trigger circle on the nav island. Tiger orange is the traffic/emergency family. */
export const REPORT_TRIGGER_HUB = '#F18805';
