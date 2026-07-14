import React from 'react';
import './santander.css';

export default function SantanderGuidePill({ text }) {
  if (!text) return null;
  return <div className="santander-guide-pill">{text}</div>;
}
