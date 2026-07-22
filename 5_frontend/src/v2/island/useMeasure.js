import { useLayoutEffect, useRef, useState } from 'react';

/** Track a container's content-box size via ResizeObserver. */
export default function useMeasure() {
  const ref = useRef(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;

    const update = (width, height) => {
      setSize((prev) => (
        prev.width === width && prev.height === height
          ? prev
          : { width, height }
      ));
    };

    update(el.clientWidth, el.clientHeight);

    const ro = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      if (box) update(box.width, box.height);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return [ref, size];
}
