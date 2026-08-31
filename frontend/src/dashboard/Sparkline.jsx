import React, { useEffect, useRef, useState } from 'react';

// Lightweight, self-contained sparkline (no chart lib): an SVG line with a soft
// gradient fill and an animated draw-in. Non-scaling stroke keeps the line crisp
// when the SVG stretches to the card width. Degrades to empty space when there
// isn't enough data to draw a trend.
let _uid = 0;

export default function Sparkline({ series = [], color = '#4f7cf7', height = 44 }) {
  const clean = (series || []).filter((v) => typeof v === 'number' && !isNaN(v));
  const pathRef = useRef(null);
  const [len, setLen] = useState(0);
  const gid = useRef('spark' + (++_uid)).current;

  const W = 200;
  const H = height;
  const pad = 5;
  let line = '';
  let pts = [];
  if (clean.length >= 2) {
    const min = Math.min(...clean);
    const max = Math.max(...clean);
    const span = max - min || 1;
    const stepX = W / (clean.length - 1);
    pts = clean.map((v, i) => [i * stepX, H - pad - ((v - min) / span) * (H - pad * 2)]);
    line = pts.map((p, i) => (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  }
  const area = line ? `${line} L ${W} ${H} L 0 ${H} Z` : '';

  useEffect(() => {
    if (pathRef.current && line) {
      try { setLen(pathRef.current.getTotalLength()); } catch (_e) { setLen(0); }
    }
  }, [line]);

  if (!line) return <div style={{ height: H }} aria-hidden="true" />;
  const last = pts[pts.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none"
         aria-hidden="true" style={{ display: 'block', overflow: 'visible' }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} />
      <path ref={pathRef} d={line} fill="none" stroke={color} strokeWidth="2.25"
            strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke"
            style={len ? { strokeDasharray: len, strokeDashoffset: len,
                           animation: 'spark-draw 1.1s ease forwards' } : undefined} />
      <circle cx={last[0]} cy={last[1]} r="3" fill={color} vectorEffect="non-scaling-stroke"
              style={{ animation: 'spark-dot .35s ease .95s both' }} />
    </svg>
  );
}
