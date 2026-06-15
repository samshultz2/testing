// Mirror of the server-side `naira` Jinja filter so React pages render money
// identically to the classic templates.
export const naira = (n) =>
  '₦' + (Number(n) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
