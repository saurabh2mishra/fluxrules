// frontend/js/metrics-viewer.js
async function loadMetrics() {
    try {
        const response = await fetch(`${API_BASE}/metrics`);
        const metricsText = await response.text();

        const container = document.getElementById('metrics-container');
        if (!container) return;

        container.innerHTML = '';

        const metrics = parsePrometheusMetrics(metricsText);

        Object.entries(metrics).forEach(([name, value]) => {
            const card = document.createElement('div');
            card.className = 'metric-card';

            const valueEl = document.createElement('div');
            valueEl.className = 'metric-value';
            valueEl.textContent = value;

            const labelEl = document.createElement('div');
            labelEl.className = 'metric-label';
            labelEl.textContent = name;

            card.appendChild(valueEl);
            card.appendChild(labelEl);

            container.appendChild(card);
        });
    } catch (error) {
        console.error('Error loading metrics:', error);
    }
}

function parsePrometheusMetrics(text) {
    const metrics = {};
    const lines = text.split('\n');

    lines.forEach(line => {
        if (line.startsWith('#') || !line.trim()) return;

        const parts = line.split(' ');
        if (parts.length >= 2) {
            const name = parts[0].replace(/_total$/, '').replace(/_/g, ' ');
            const value = parseFloat(parts[1]);
            metrics[name] = value;
        }
    });

    return metrics;
}