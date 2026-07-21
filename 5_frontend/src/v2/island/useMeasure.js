import { useEffect, useRef, useState } from 'react';

/** Track a container's content-box size via ResizeObserver. */
export default function useMeasure() {
  const ref = useRef(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const ro = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      if (box) setSize({ width: box.width, height: box.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return [ref, size];
}
