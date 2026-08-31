# Vendored third-party assets — provenance

These files are committed to the repo (served directly to browsers) rather than
pulled from a CDN, so they are outside npm/pip dependency scanning. This manifest
records where each came from and its SHA-256, so the bytes can be re-verified
against upstream and re-fetched reproducibly.

Verify:  `sha256sum -c SOURCES.sha256`  (generate that file from the table below),
or spot-check a single file: `sha256sum <file>`.

| File | Library | Version | SHA-256 |
|------|---------|---------|---------|
| `chart.umd.min.js` | Chart.js | 4.4.1 | `d2af8974e95271638772e9e9524db5b9a6f58d6ec2d5d781400447b4a31c681e` |
| `html2canvas.min.js` | html2canvas | 1.4.1 | `e87e550794322e574a1fda0c1549a3c70dae5a93d9113417a429016838eab8cb` |
| `jspdf.umd.min.js` | jsPDF | 2.5.1 | `98ccf17aa10c20bb1301762618fcc9b6ab3a4e7f26b6071d64d0b41154df3875` |
| `react.production.min.js` | React (UMD, production) | 18.3.1 | `d949f1c3687aedadcedac85261865f29b17cd273997e7f6b2bfc53b2f9d4c4dd` |
| `react-dom.production.min.js` | ReactDOM (UMD, production) | 18.3.1 | `35f4f974f4b2bcd44da73963347f8952e341f83909e4498227d4e26b98f66f0d` |
| `fontawesome/css/all.min.css` | Font Awesome Free | 6.4.0 | `1edb1725a9ea8ca4dcf2f5508cee183218aa1685e47c1b23056717f754f58ebf` |

`fontawesome/webfonts/*` are the matching 6.4.0 font files shipped with the CSS
above.

## Upstream sources
- Chart.js 4.4.1 — https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js
- html2canvas 1.4.1 — https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js
- jsPDF 2.5.1 — https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js
- React / ReactDOM 18.3.1 — https://unpkg.com/react@18.3.1/umd/react.production.min.js and
  https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js
- Font Awesome Free 6.4.0 — https://fontawesome.com/download (Free for Web)

## Updating a vendored file
1. Download the new version from the upstream source above.
2. Recompute its hash: `sha256sum <file>`.
3. Update the version + SHA-256 in the table here, in the same commit as the file.
