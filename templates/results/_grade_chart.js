// Per-grade coloured bar chart for a WAEC / Mock-WAEC subject.
// Re-runs safely under spa-nav (guards the data node + destroys any prior chart).
(function () {
  var node = document.getElementById('saData');
  var canvas = document.getElementById('saGradeChart');
  if (!node || !canvas || typeof Chart === 'undefined') return;
  var dist;
  try { dist = JSON.parse(node.textContent || '[]'); } catch (e) { return; }
  if (!dist.length) return;

  var GC = {A1:'#16a34a',B2:'#0d9488',B3:'#0891b2',C4:'#2563eb',C5:'#4f46e5',
            C6:'#7c3aed',D7:'#d97706',E8:'#ea580c',F9:'#dc2626'};
  var css = getComputedStyle(document.body);
  var grid = (css.getPropertyValue('--border-color') || '#e9edf3').trim();
  var text = (css.getPropertyValue('--text-muted') || '#697690').trim();

  var prev = Chart.getChart(canvas);
  if (prev) prev.destroy();

  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: dist.map(function (d) { return d.grade; }),
      datasets: [{
        data: dist.map(function (d) { return d.count; }),
        backgroundColor: dist.map(function (d) { return GC[d.grade] || '#94a3b8'; }),
        borderRadius: 6,
        maxBarThickness: 54
      }]
    },
    options: {
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
        x: { grid: { display: false }, ticks: { color: text, font: { weight: '700' } } },
        y: { beginAtZero: true, ticks: { precision: 0, color: text }, grid: { color: grid } }
      }
    }
  });
})();
