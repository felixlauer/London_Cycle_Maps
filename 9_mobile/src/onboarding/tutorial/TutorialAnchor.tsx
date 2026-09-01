import { useEffect, useRef, type ReactNode } from 'react';
import { View, type StyleProp, type ViewStyle } from 'react-native';
import {
  bumpTutorialAnchors,
  registerTutorialAnchor,
  type TutorialCutoutOpts,
} from './tutorialRegistry';

type Props = {
  id: string;
  children?: ReactNode;
  style?: StyleProp<ViewStyle>;
  opts?: TutorialCutoutOpts;
  pointerEvents?: 'auto' | 'none' | 'box-none' | 'box-only';
};

/** Registers a measurable spotlight target. */
export function TutorialAnchor({
  id,
  children = null,
  style,
  opts,
  pointerEvents,
}: Props) {
  const ref = useRef<View>(null);
  const optsKey = JSON.stringify(opts || {});

  useEffect(() => {
    const parsed = optsKey ? JSON.parse(optsKey) as TutorialCutoutOpts : {};
    return registerTutorialAnchor(id, ref, parsed);
  }, [id, optsKey]);

  return (
    <View
      ref={ref}
      collapsable={false}
      style={style}
      pointerEvents={pointerEvents}
      onLayout={() => bumpTutorialAnchors()}
    >
      {children}
    </View>
  );
}
