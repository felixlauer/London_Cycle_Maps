import React from 'react';
import '../../alerts/alertPill.css';

/**
 * Top-center communication pill — enters/exits with transform+opacity.
 * Optional inline actions (e.g. Cancel / Proceed) for confirm prompts.
 */
export default function AlertPillZone({ alert, onAction }) {
  const visible = Boolean(alert?.message);
  const hasActions = Boolean(alert?.actions?.length);

  return (
    <div
      className={
        `shell-zone shell-zone--alert alert-pill` +
        (visible ? ' is-visible' : '') +
        (hasActions ? ' has-actions' : '') +
        (alert ? ` alert-pill--${alert.type}` : '')
      }
      role={hasActions ? 'alertdialog' : 'status'}
      aria-live="polite"
      data-zone="alert-pill"
    >
      {visible && (
        <>
          <span className="alert-pill__text">{alert.message}</span>
          {hasActions && (
            <span className="alert-pill__actions" role="group">
              {alert.actions.map((action) => (
                <button
                  key={action.id}
                  type="button"
                  className={
                    `alert-pill__btn` +
                    (action.primary ? ' is-primary' : ' is-ghost')
                  }
                  onClick={() => onAction?.(action.id, alert)}
                >
                  {action.label}
                </button>
              ))}
            </span>
          )}
        </>
      )}
    </div>
  );
}
