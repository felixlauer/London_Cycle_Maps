import { useCallback, useEffect, useRef, useState } from 'react';
import { ALERT_PRIORITY, ALERT_TTL_MS } from '../routing/constants';

/**
 * Single visible alert, priority-gated.
 * Transient alerts auto-dismiss; sticky confirms (actions) stay until the user
 * acts or `dismiss` is called.
 */
export function useAlertPill() {
  const [alert, setAlert] = useState(null);
  const alertRef = useRef(null);
  const timerRef = useRef(null);
  const seqRef = useRef(0);

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const dismiss = useCallback((types) => {
    const cur = alertRef.current;
    if (!cur) return;
    if (types) {
      const list = Array.isArray(types) ? types : [types];
      if (!list.includes(cur.type)) return;
    }
    clearTimer();
    alertRef.current = null;
    setAlert(null);
  }, []);

  const push = useCallback((next) => {
    if (!next?.message) return;
    const type = next.type || 'info';
    const priority = ALERT_PRIORITY[type] ?? 0;
    const cur = alertRef.current;
    // A strictly-higher-priority alert keeps the stage (and keeps its own timer).
    if (cur && (ALERT_PRIORITY[cur.type] ?? 0) > priority) return;

    clearTimer();
    const sticky = Boolean(next.sticky || (next.actions && next.actions.length) || type === 'confirm');
    const entry = {
      id: `a-${++seqRef.current}`,
      type,
      message: next.message,
      sticky,
      actions: next.actions || null,
      meta: next.meta || null,
    };
    alertRef.current = entry;
    setAlert(entry);

    const ttl = ALERT_TTL_MS[type];
    if (!sticky && ttl != null) {
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        alertRef.current = null;
        setAlert(null);
      }, ttl);
    }
  }, []);

  useEffect(() => () => clearTimer(), []);

  return { alert, push, dismiss };
}
