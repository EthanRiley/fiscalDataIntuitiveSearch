// Agent chat widget toggle
const widget = document.getElementById('agent-widget');
const toggle = document.getElementById('agent-toggle');

toggle?.addEventListener('click', () => {
  widget.classList.toggle('collapsed');
});

// Send message on Enter key
document.getElementById('agent-input')?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') document.getElementById('agent-send')?.click();
});

// Dataset grid (index page)
const grid = document.getElementById('dataset-grid');
if (grid) {
  fetch('/api/datasets')
    .then(r => r.json())
    .then(datasets => {
      grid.innerHTML = datasets.map(d => `
        <div class="dataset-card" onclick="window.location='/dashboard?dataset=${d.id}'">
          <h3>${d.name}</h3>
          <p>${d.description}</p>
        </div>
      `).join('');
    })
    .catch(() => { grid.innerHTML = '<p class="loading">Failed to load datasets.</p>'; });
}

// Dashboard page — populate select
const select = document.getElementById('endpoint-select');
if (select) {
  fetch('/api/datasets')
    .then(r => r.json())
    .then(datasets => {
      select.innerHTML = datasets.map(d =>
        `<option value="${d.endpoint}">${d.name}</option>`
      ).join('');

      // Auto-select from query param
      const params = new URLSearchParams(window.location.search);
      const preset = params.get('dataset');
      if (preset) {
        const match = datasets.find(d => d.id === preset);
        if (match) select.value = match.endpoint;
      }
    });
}

// Fetch & plot
document.getElementById('fetch-btn')?.addEventListener('click', () => {
  const endpoint = select?.value;
  if (!endpoint) return;

  fetch(`/api/query?endpoint=${encodeURIComponent(endpoint)}&sort=-record_date`)
    .then(r => r.json())
    .then(data => {
      document.getElementById('raw-json').textContent = JSON.stringify(data, null, 2);

      const records = data.data || [];
      if (!records.length) return;

      const keys = Object.keys(records[0]);
      const xKey = keys.find(k => k.includes('date')) || keys[0];
      const yKey = keys.find(k => k !== xKey) || keys[1];

      Plotly.newPlot('plotly-chart', [{
        x: records.map(r => r[xKey]),
        y: records.map(r => parseFloat(r[yKey])),
        type: 'scatter',
        mode: 'lines',
        line: { color: '#fff' },
      }], {
        paper_bgcolor: '#000',
        plot_bgcolor: '#000',
        font: { color: '#fff' },
        xaxis: { gridcolor: '#222' },
        yaxis: { gridcolor: '#222' },
        margin: { t: 20, r: 20, b: 40, l: 60 },
      });
    });
});
