import { useRef } from 'react';
import { PanResponder, StyleSheet, View } from 'react-native';
import { brand, type ChromeTokens } from '../theme/tokens';

type Props = {
  value: number;
  min?: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  c: ChromeTokens;
  accessibilityLabel?: string;
};

/** Simple pan range control (no extra deps). */
export function RangeSlider({
  value,
  min = 0,
  max,
  step = 0.1,
  onChange,
  c,
  accessibilityLabel,
}: Props) {
  const trackRef = useRef<View>(null);
  const trackW = useRef(1);
  const trackPageX = useRef(0);
  const span = Math.max(0.0001, max - min);

  const measureTrack = () => {
    trackRef.current?.measureInWindow((x, _y, w) => {
      trackPageX.current = x;
      trackW.current = Math.max(1, w);
    });
  };

  const setFromPageX = (pageX: number) => {
    const x = pageX - trackPageX.current;
    const t = Math.max(0, Math.min(1, x / trackW.current));
    let next = min + t * span;
    if (step > 0) next = Math.round(next / step) * step;
    next = Math.max(min, Math.min(max, next));
    next = Math.round(next * 1000) / 1000;
    onChange(next);
  };

  const pan = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: (e) => {
        measureTrack();
        setFromPageX(e.nativeEvent.pageX);
      },
      onPanResponderMove: (e) => setFromPageX(e.nativeEvent.pageX),
    }),
  ).current;

  const pct = ((value - min) / span) * 100;

  return (
    <View
      ref={trackRef}
      accessibilityRole="adjustable"
      accessibilityLabel={accessibilityLabel}
      accessibilityValue={{ min, max, now: value }}
      onLayout={measureTrack}
      style={[styles.track, { backgroundColor: c.line }]}
      {...pan.panHandlers}
    >
      <View style={[styles.fill, { width: `${pct}%` as `${number}%`, backgroundColor: brand.fuchsia }]} />
      <View
        style={[
          styles.thumb,
          {
            left: `${pct}%` as `${number}%`,
            backgroundColor: '#fff',
            borderColor: brand.fuchsia,
          },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    height: 6,
    borderRadius: 999,
    justifyContent: 'center',
    marginVertical: 8,
  },
  fill: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    borderRadius: 999,
  },
  thumb: {
    position: 'absolute',
    width: 20,
    height: 20,
    borderRadius: 999,
    borderWidth: 2,
    marginLeft: -10,
    top: -7,
    shadowColor: '#000',
    shadowOpacity: 0.15,
    shadowRadius: 3,
    shadowOffset: { width: 0, height: 1 },
    elevation: 2,
  },
});
