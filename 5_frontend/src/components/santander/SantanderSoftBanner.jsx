import React from 'react';
import './santander.css';

export default function SantanderSoftBanner({ text }) {
  if (!text) return null;
  return <div className="santander-soft-banner">{text}</div>;
}
