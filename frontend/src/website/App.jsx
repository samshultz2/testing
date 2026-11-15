// Website Builder — one app for the overview, page editor, news, media,
// holiday assignments and analytics. Navigation swaps screens in place.
import React, { useState, useCallback } from 'react';
import { useSection, NavCtx } from '../lib/section';
import { SectionShell } from '../components/ui';
import { canWrite } from '../lib/perms';
import { Ctx, Toast } from './kit';
import { Overview } from './Overview';
import { PageEditor } from './PageEditor';
import { NewsList, PostEditor } from './News';
import { Media } from './Media';
import { Assignments } from './Assignments';
import { Analytics } from './Analytics';

const TABS = [
  { key: 'home', label: 'Site', icon: 'fa-globe', pages: ['home', 'page'] },
  { key: 'news', label: 'News', icon: 'fa-newspaper', pages: ['news', 'post'] },
  { key: 'media', label: 'Media', icon: 'fa-images', pages: ['media'] },
  { key: 'assignments', label: 'Assignments', icon: 'fa-file-arrow-down', pages: ['assignments'] },
  { key: 'analytics', label: 'Visitors', icon: 'fa-chart-line', pages: ['analytics'] },
];

const SCREENS = { home: Overview, page: PageEditor, news: NewsList, post: PostEditor,
  media: Media, assignments: Assignments, analytics: Analytics };

export default function WebsiteApp({ data }) {
  const { data: d, go, refresh, setData } = useSection(data);
  const [toast, setToast] = useState(null);
  const notify = useCallback((tone, text) => { if (text) setToast({ tone, text, at: Date.now() }); }, []);
  const Screen = SCREENS[d.page] || Overview;
  const write = canWrite(d);
  const ctx = { d, go, refresh, setData, notify, write, urls: d.urls || {} };
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <Ctx.Provider value={ctx}>
        <SectionShell go={go}>
          <div className={'ws ws-on-' + d.page}>
            <nav className="ws-tabs" aria-label="Website Builder">
              {TABS.map((t) => {
                const on = t.pages.includes(d.page);
                return (
                  <a key={t.key} href={d.nav[t.key]} className={on ? 'on' : ''} aria-current={on ? 'page' : undefined}>
                    <i className={'fas ' + t.icon} aria-hidden="true" /><span>{t.label}</span></a>
                );
              })}
              <a className="ws-tabs-live" href={d.public_home} target="_blank" rel="noopener">
                <span className={'ws-dot ' + (d.published ? 'live' : 'draft')} aria-hidden="true" />
                <span>{d.published ? 'View live site' : 'Preview draft'}</span>
                <i className="fas fa-arrow-up-right-from-square" aria-hidden="true" /></a>
            </nav>
            <Screen key={d.page + ':' + ((d.pg && d.pg.id) || (d.post && d.post.id) || '')} />
          </div>
          <Toast toast={toast} onDone={() => setToast(null)} />
        </SectionShell>
      </Ctx.Provider>
    </NavCtx.Provider>
  );
}
