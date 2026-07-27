import React, { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { apiFetch } from '../../api/flaskClient';
import './bugReport.css';

export const BUG_REPORT_MAX_CHARS = 1500;
export const BUG_REPORT_MIN_CHARS = 10;

/**
 * Centered bug-report overlay — works on phone / tablet / desktop.
 * Persists via Flask → Supabase (or local JSON in bare-dev).
 */
export default function BugReportModal({ open, onClose, themeMode = 'light' }) {
  const titleId = useId();
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const textareaRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    setMessage('');
    setError('');
    setSending(false);
    setSent(false);
    const t = window.setTimeout(() => textareaRef.current?.focus(), 40);
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);

  if (!open || typeof document === 'undefined') return null;

  const remaining = BUG_REPORT_MAX_CHARS - message.length;
  const canSend = message.trim().length >= BUG_REPORT_MIN_CHARS
    && message.length <= BUG_REPORT_MAX_CHARS
    && !sending
    && !sent;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!canSend) return;
    setSending(true);
    setError('');
    try {
      const res = await apiFetch('/feedback/bug', {
        method: 'POST',
        body: {
          message: message.trim(),
          page_url: typeof window !== 'undefined' ? window.location.href : '',
          user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : '',
          theme: themeMode,
          viewport: typeof window !== 'undefined'
            ? `${window.innerWidth}x${window.innerHeight}`
            : '',
          app_version: process.env.REACT_APP_VERSION || 'v2',
        },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.error || 'Could not send report.');
        setSending(false);
        return;
      }
      setSent(true);
      setSending(false);
      window.setTimeout(() => onClose?.(), 900);
    } catch {
      setError('Could not reach the server.');
      setSending(false);
    }
  };

  return createPortal(
    <div className="bug-report-overlay" role="presentation" onClick={onClose}>
      <div
        className="bug-report-modal"
        data-theme={themeMode}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="bug-report-modal__header">
          <h2 id={titleId} className="bug-report-modal__title">Report a bug</h2>
          <button
            type="button"
            className="bug-report-modal__close"
            aria-label="Close"
            onClick={onClose}
          >
            <X size={18} strokeWidth={2.2} aria-hidden />
          </button>
        </header>

        <p className="bug-report-modal__hint">
          Tell us what went wrong and what you expected. We attach page, device,
          and theme details automatically — no account required.
        </p>

        <form className="bug-report-modal__form" onSubmit={handleSubmit}>
          <label className="bug-report-modal__label" htmlFor="bug-report-message">
            What happened?
          </label>
          <textarea
            id="bug-report-message"
            ref={textareaRef}
            className="bug-report-modal__textarea"
            value={message}
            maxLength={BUG_REPORT_MAX_CHARS}
            rows={7}
            placeholder="e.g. After tapping Get Route, the island stayed empty even though the route drew on the map."
            disabled={sending || sent}
            onChange={(e) => setMessage(e.target.value)}
          />
          <div className="bug-report-modal__meta">
            <span className={remaining < 80 ? 'is-warn' : ''}>
              {remaining} left
            </span>
            <span>Min {BUG_REPORT_MIN_CHARS} characters</span>
          </div>

          {error && <p className="bug-report-modal__error" role="alert">{error}</p>}
          {sent && (
            <p className="bug-report-modal__success" role="status">
              Thanks — report sent.
            </p>
          )}

          <div className="bug-report-modal__actions">
            <button
              type="button"
              className="bug-report-modal__btn"
              onClick={onClose}
              disabled={sending}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="bug-report-modal__btn bug-report-modal__btn--primary"
              disabled={!canSend}
            >
              {sending ? 'Sending…' : sent ? 'Sent' : 'Send report'}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  );
}
