// Score-band bar chart for a JAMB / Mock-JAMB subject.
// Re-runs safely under spa-nav (guards the data node + destroys any prior chart).
(function () {
  var node = document.getElementById('saData');
  var canvas = document.getElementById('saScoreChart');
  if (!node || !canvas || typeof Chart === 'undefined') return;
  var dist;
  try { dist = JSON.parse(node.textContent || '[]'); } catch (e) { return; }
  if (!dist.length) return;

  // Excellent → Poor, best band greenest.
  var COLORS = ['#16a34a', '#0d9488', '#2563eb', '#d97706', '#dc2626'];
  var css = getComputedStyle(document.body);
  var grid = (css.getPropertyValue('--border-color') || '#e9edf3').trim();
  var text = (css.getPropertyValue('--text-muted') || '#697690').trim();

  var prev = Chart.getChart(canvas);
  if (prev) prev.destroy();

  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: dist.map(function (d) { return d.label.replace(/\s*\(.*\)$/, ''); }),
      datasets: [{
        data: dist.map(function (d) { return d.count; }),
        backgroundColor: dist.map(function (d, i) { return COLORS[i] || '#94a3b8'; }),
        borderRadius: 6,
        maxBarThickness: 40
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              var d = dist[ctx.dataIndex];
              return d.count + ' candidate' + (d.count === 1 ? '' : 's') + ' · ' + d.pct + '%';
            }
          }
        }
      },
      scales: {
        x: { beginAtZero: true, ticks: { precision: 0, color: text }, grid: { color: grid } },
        y: { grid: { display: false }, ticks: { color: text, font: { weight: '700' } } }
      }
    }
  });
})();
