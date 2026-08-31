// Mirror of the server-side `naira` Jinja filter so React pages render money
// identically to the classic templates.
export const naira = (n) =>
  '₦' + (Number(n) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// Compact money for tight spaces (KPIs/charts): 1_250_000 -> ₦1.25M, 9_500 -> ₦9.5k.
// Single shared definition — screens previously re-declared this locally.
export const nairaShort = (n) => {
  const v = Number(n) || 0;
  const abs = Math.abs(v);
  if (abs >= 1e6) return '₦' + (v / 1e6).toFixed(v % 1e6 === 0 ? 0 : 2).replace(/\.0+$/, '') + 'M';
  if (abs >= 1e3) return '₦' + (v / 1e3).toFixed(v % 1e3 === 0 ? 0 : 1).replace(/\.0+$/, '') + 'k';
  return '₦' + v.toLocaleString();
};
