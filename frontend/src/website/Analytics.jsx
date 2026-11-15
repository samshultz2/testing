// Visitors: simple, private traffic numbers with a daily chart.
import React, { useState } from 'react';
import { Seg, Tiles, Blank } from '../subjects/results';
import { useWs } from './kit';

const n = (v) => Number(v || 0).toLocaleString();

export function Analytics() {
  const { d, go } = useWs();
  const [hover, setHover] = useState(null);
  const peak = d.peak || 0;
  const step = d.series.length > 40 ? 14 : d.series.length > 10 ? 7 : 1;
  const shown = hover != null ? d.series[hover] : null;
  const maxPage = Math.max(1, ...d.top_pages.map((p) => p.views));
  const maxRef = Math.max(1, ...d.top_referrers.map((p) => p.views));
  return (
    <div className="ws-list-page">
      <header className="ws-page-h">
        <div><h1>Visitors</h1><p>{d.start} – {d.end}. Private: no cookies, no trackers, no personal data.</p></div>
        <div className="ws-page-a">
          <Seg label="Period" value={String(d.days)} onChange={(v) => go(d.nav.analytics + '?days=' + v, { replace: true })}
               options={[{ value: '7', label: '7 days' }, { value: '30', label: '30 days' }, { value: '90', label: '90 days' }]} />
          <a className="rs-btn ghost" href={d.urls.csv} data-native="" download><i className="fas fa-download" aria-hidden="true" /><span className="rs-hide-sm">CSV</span></a>
        </div>
      </header>
      <Tiles items={[
        { label: 'Page views', value: n(d.total), sub: `in ${d.days} days` },
        { label: 'Visitors', value: n(d.unique), sub: 'counted without identifying anyone' },
        { label: 'Busiest day', value: n(peak), sub: d.busiest || 'No visits yet' },
        d.trend != null && { label: 'Trend', value: (d.trend > 0 ? '+' : '') + d.trend + '%', sub: 'second half vs first half', tone: d.trend >= 0 ? 'good' : 'bad' },
      ]} />
      <section className="ws-card ws-chart">
        <header className="ws-card-h"><div><h2>Daily views</h2><p>{shown ? `${shown.label}: ${n(shown.views)} view${shown.views === 1 ? '' : 's'}` : 'Touch or hover a bar to see the day.'}</p></div></header>
        {d.total ? (
          <div className="ws-bars" role="img" aria-label={`Daily page views from ${d.start} to ${d.end}`} onMouseLeave={() => setHover(null)}>
            {d.series.map((p, i) => (
              <div key={p.day} className={'ws-bar' + (hover === i ? ' on' : '')} onMouseEnter={() => setHover(i)} onClick={() => setHover(i)}>
                <i style={{ height: (peak ? (p.views / peak) * 100 : 0) + '%' }} />
                {i % step === 0 && <span>{p.short}</span>}
              </div>
            ))}
          </div>
        ) : <Blank icon="fa-chart-line" title="No visits yet"><p>{d.published ? 'Share your website link — visits will show up here.' : 'Publish your website and visits will show up here.'}</p></Blank>}
      </section>
      <div className="ws-ov-grid">
        <section className="ws-card">
          <header className="ws-card-h"><div><h2>Most viewed pages</h2></div></header>
          <Ranked rows={d.top_pages.map((p) => ({ k: p.path, l: p.path, v: p.views }))} max={maxPage} />
        </section>
        <section className="ws-card">
          <header className="ws-card-h"><div><h2>Where visitors came from</h2></div></header>
          <Ranked rows={d.top_referrers.map((r) => ({ k: r.source, l: r.source === 'direct' ? 'Typed the link / bookmark' : r.source, v: r.views }))} max={maxRef} />
        </section>
      </div>
    </div>
  );
}

function Ranked({ rows, max }) {
  if (!rows.length) return <p className="rs-muted ws-pad">No data yet.</p>;
  return (
    <ol className="ws-rank">
      {rows.map((r) => (
        <li key={r.k}><span className="ws-rank-l" title={r.l}>{r.l}</span><b>{n(r.v)}</b>
          <i style={{ width: Math.max(2, (r.v / max) * 100) + '%' }} aria-hidden="true" /></li>
      ))}
    </ol>
  );
}
