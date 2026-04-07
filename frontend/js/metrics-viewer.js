async function loadMetrics() {
    const container = document.getElementById('metrics-container');
    if (!container) return;

    container.innerHTML = '<div class="loading">Loading analytics dashboard...</div>';

    const [runtime, topRules, explanations] = await Promise.all([
        fetchJson(`${API_BASE}/analytics/runtime`),
        fetchJson(`${API_BASE}/analytics/rules/top?limit=10`),
        fetchJson(`${API_BASE}/analytics/explanations?limit=20`),
    ]);

    renderDashboard({ runtime, topRules, explanations });
}

async function fetchJson(url) {
    try {
        const response = await fetchWithAuth(url);
        if (!response.ok) {
            throw new Error(`Request failed: ${url}`);
        }
        return await response.json();
    } catch (error) {
        console.error(error);
        return { __error: true };
    }
}

function renderDashboard(data) {
    const container = document.getElementById('metrics-container');
    if (!container) return;

    const summary = data.runtime?.summary || {};
    const hotRules = data.topRules?.top_hot_rules || data.runtime?.top_hot_rules || [];
    const coldRules = data.topRules?.cold_rules || data.runtime?.cold_rules || [];
    const explanationItems = data.explanations?.items || data.runtime?.recent_explanations || [];

    container.innerHTML = `
        <div class="metrics-dashboard">
            ${renderWarning(data)}

            <div class="metrics-section">
                <h3>📈 Runtime Summary</h3>
                <div class="metrics-grid">
                    <div class="metric-card"><div class="metric-value">${summary.coverage_pct ?? 0}%</div><div class="metric-label">Coverage</div></div>
                    <div class="metric-card"><div class="metric-value">${summary.triggered_rules ?? 0} / ${summary.total_rules ?? 0}</div><div class="metric-label">Triggered / Total Rules</div></div>
                    <div class="metric-card"><div class="metric-value">${summary.rules_never_fired_count ?? 0}</div><div class="metric-label">Never Fired Rules</div></div>
                    <div class="metric-card"><div class="metric-value">${summary.events_processed ?? 0}</div><div class="metric-label">Events Processed</div></div>
                    <div class="metric-card"><div class="metric-value">${summary.rules_fired ?? 0}</div><div class="metric-label">Rules Fired</div></div>
                    <div class="metric-card"><div class="metric-value">${summary.avg_processing_time_ms ?? 0} ms</div><div class="metric-label">Avg Processing Time</div></div>
                </div>
            </div>

            <div class="metrics-section">
                <h3>🔥 Top Fired Rules</h3>
                ${renderRuleTable(hotRules, true)}
            </div>

            <div class="metrics-section">
                <h3>🧊 Never Fired Rules</h3>
                ${renderRuleTable(coldRules, false)}
            </div>

            <div class="metrics-section">
                <h3>🧠 Recent Explanations</h3>
                ${renderExplanations(explanationItems)}
            </div>

            <div class="metrics-footer">
                <button class="btn btn-sm" onclick="loadMetrics()">🔄 Refresh</button>
                <span class="last-updated">Last updated: ${new Date().toLocaleTimeString()}</span>
            </div>
        </div>
    `;

    attachRuleDrilldown();
}

function renderWarning(data) {
    const hasError = [data.runtime, data.topRules, data.explanations].some((x) => x && x.__error);
    if (!hasError) return '';
    return '<div class="error-message">Some analytics sections failed to load. Showing partial data.</div>';
}

function renderRuleTable(items, clickable) {
    if (!items || items.length === 0) {
        return '<div class="empty-state"><p>No rules to display.</p></div>';
    }

    return `
        <div class="table-wrap">
            <table class="rules-table">
                <thead>
                    <tr>
                        <th>Rule</th>
                        <th>Hit Count</th>
                        <th>Avg Exec Time</th>
                        <th>Last Fired</th>
                    </tr>
                </thead>
                <tbody>
                    ${items.map((item) => `
                        <tr class="${clickable ? 'rule-drilldown-row' : ''}" data-rule-id="${item.rule_id}">
                            <td>${item.rule_name || `Rule #${item.rule_id}`}</td>
                            <td>${item.hit_count ?? 0}</td>
                            <td>${item.avg_execution_time_ms ?? 0} ms</td>
                            <td>${item.last_fired_at ? new Date(item.last_fired_at).toLocaleString() : 'Never'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function renderExplanations(items) {
    if (!items || items.length === 0) {
        return '<div class="empty-state"><p>No explanations captured yet.</p></div>';
    }

    return items.map((item) => `
        <details class="explanation-item">
            <summary><strong>Rule ${item.rule_id}</strong> — ${new Date(item.timestamp).toLocaleString()}</summary>
            <div class="rule-explanation">${item.explanation || ''}</div>
            <div><strong>Matched:</strong> ${(item.matched_conditions || []).join(', ') || 'None'}</div>
            <div><strong>Missing/Failed:</strong> ${(item.missing_conditions || []).join(', ') || 'None'}</div>
            <pre>${JSON.stringify(item.sample_fact || {}, null, 2)}</pre>
        </details>
    `).join('');
}

function attachRuleDrilldown() {
    document.querySelectorAll('.rule-drilldown-row').forEach((row) => {
        row.addEventListener('click', async () => {
            const ruleId = row.dataset.ruleId;
            if (!ruleId) return;
            const data = await fetchJson(`${API_BASE}/analytics/rules/${ruleId}`);
            if (data.__error) {
                showToast('Failed to load rule analytics.', 'error');
                return;
            }
            showRuleDrilldown(ruleId, data);
        });
    });
}

function showRuleDrilldown(ruleId, data) {
    const existing = document.getElementById('analytics-drilldown-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'analytics-drilldown-modal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;z-index:2100;';

    const metric = data.metric || {};
    const explanations = data.recent_explanations || [];

    modal.innerHTML = `
        <div style="background:var(--card,#fff);color:var(--text,#111);padding:1rem;max-width:750px;width:95%;max-height:85vh;overflow:auto;border-radius:8px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <h3>Rule Analytics: ${metric.rule_name || `#${ruleId}`}</h3>
                <button class="btn btn-sm" id="close-analytics-modal">✕</button>
            </div>
            <p><strong>Hits:</strong> ${metric.hit_count || 0} | <strong>Avg:</strong> ${metric.avg_execution_time_ms || 0} ms</p>
            <h4>Recent Explanations</h4>
            ${renderExplanations(explanations)}
        </div>
    `;

    document.body.appendChild(modal);
    document.getElementById('close-analytics-modal')?.addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (event) => {
        if (event.target === modal) modal.remove();
    });
}
