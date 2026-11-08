import React, { useState } from 'react';
import { useSection, NavCtx } from '../lib/section';
import { Banner, SectionShell } from '../components/ui';
import * as Screens from './screens';
import { Assets as AssetsPage } from './assets';

const SCREENS = { dashboard: Screens.Dashboard, products: Screens.Products, new_sale: Screens.NewSale,
  history: Screens.History, analytics: Screens.Analytics, movements: Screens.Movements,
  suppliers: Screens.Suppliers, supplier_detail: Screens.SupplierDetail, purchases: Screens.Purchases,
  purchase_detail: Screens.PurchaseDetail, reports: Screens.Reports, promos: Screens.Promos,
  audits: Screens.Audits, audit_detail: Screens.AuditDetail, assets: AssetsPage, batches: Screens.Batches };

export default function SalesApp({ data }) {
  const { data: d, go, refresh } = useSection(data);
  const [msg, setMsg] = useState(null);
  const notify = (tone, text) => setMsg({ tone, text });
  const Screen = SCREENS[d.page] || Screens.Dashboard;
  return (
    <NavCtx.Provider value={{ go, refresh }}>
      <SectionShell go={go}>
        {msg && <Banner tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Banner>}
        <Screen d={d} notify={notify} />
      </SectionShell>
    </NavCtx.Provider>
  );
}
