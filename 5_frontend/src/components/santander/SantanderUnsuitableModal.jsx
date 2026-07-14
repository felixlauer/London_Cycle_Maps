import React from 'react';
import './santander.css';

export default function SantanderUnsuitableModal({ open, title, message, onCancel, onProceed }) {
  if (!open) return null;
  return (
    <div className="santander-modal-backdrop" role="dialog" aria-modal="true">
      <div className="santander-modal">
        <h3>{title}</h3>
        <p>{message}</p>
        <div className="santander-modal-actions">
          <button type="button" className="ui-btn" onClick={onCancel}>Cancel</button>
          <button type="button" className="ui-btn primary" onClick={onProceed}>Proceed</button>
        </div>
      </div>
    </div>
  );
}
