async function loadDependencyGraph() {
    const container = document.getElementById('dependency-graph');
    if (!container) return;

    container.innerHTML = '<div class="loading">Loading dependency diagnostics...</div>';

    const summary = await fetchDependencySummary({});
    if (summary.__error) {
        container.innerHTML = '<div class="error-message">Failed to load dependency diagnostics.</div>';
        return;
    }

    renderDependencyDiagnostics(summary);
}

async function fetchDependencySummary(filters) {
    return fetchDependencyJson(`${API_BASE}/rules/graph/summary${toQuery(filters)}`);
}

async function fetchDependencyJson(url) {
    try {
        const response = await fetchWithAuth(url);
        if (!response.ok) throw new Error('Request failed');
        return await response.json();
    } catch (error) {
        console.error(error);
        return { __error: true };
    }
}

function toQuery(filters) {
    const params = new URLSearchParams();
    if (filters.group) params.set('group', filters.group);
    if (filters.field) params.set('field', filters.field);
    if (filters.rule_name) params.set('rule_name', filters.rule_name);
    const q = params.toString();
    return q ? `?${q}` : '';
}

function renderDependencyDiagnostics(summary) {
    const container = document.getElementById('dependency-graph');
    if (!container) return;

    const groups = summary.available_groups || [];

    container.innerHTML = `
        <div class="metrics-dashboard">
            <div class="metrics-section">
                <h3>🧭 Dependency Diagnostics</h3>
                <p class="page-description dep-description">Use filters to inspect connected and isolated rule relationships.</p>
                <div class="filters dep-filters">
                    <select id="dep-filter-group">
                        <option value="">All Groups</option>
                        ${groups.map((g) => `<option value="${g}">${g}</option>`).join('')}
                    </select>
                    <input id="dep-filter-field" type="text" placeholder="Field (e.g. amount)">
                    <input id="dep-filter-rule" type="text" placeholder="Rule name contains...">
                    <button class="btn btn-sm" id="dep-apply-filters">Apply Filters</button>
                </div>
            </div>

            <div class="metrics-section">
                <h3>📊 Summary</h3>
                <div class="metrics-grid">
                    <div class="metric-card"><div class="metric-value">${summary.total_rules || 0}</div><div class="metric-label">Total Rules</div></div>
                    <div class="metric-card"><div class="metric-value">${summary.filtered_rules || 0}</div><div class="metric-label">Filtered Rules</div></div>
                    <div class="metric-card"><div class="metric-value">${summary.pair_count || 0}</div><div class="metric-label">Rule Pairs (Shared Field)</div></div>
                    <div class="metric-card"><div class="metric-value">${(summary.isolated_rules || []).length}</div><div class="metric-label">Isolated Rules (top list)</div></div>
                </div>
            </div>

            <div class="metrics-section">
                <h3>🏷️ Top Shared Fields</h3>
                ${renderDiagnosticsTable(summary.top_shared_fields || [], [
                    ['field', 'Field'],
                    ['rule_count', 'Rules'],
                    ['pair_count', 'Rule Pairs'],
                ])}
            </div>

            <div class="metrics-section">
                <h3>🔗 Most Connected Rules</h3>
                ${renderDiagnosticsTable(summary.most_connected_rules || [], [
                    ['name', 'Rule'],
                    ['group', 'Group'],
                    ['connections', 'Connections'],
                    ['field_count', 'Field Count'],
                ])}
            </div>

            <div class="metrics-section">
                <h3>🧊 Isolated Rules</h3>
                ${renderDiagnosticsTable(summary.isolated_rules || [], [
                    ['name', 'Rule'],
                    ['group', 'Group'],
                    ['connections', 'Connections'],
                    ['field_count', 'Field Count'],
                ])}
            </div>
        </div>
    `;

    attachDependencyHandlers();
}

function renderDiagnosticsTable(rows, cols) {
    if (!rows.length) {
        return '<div class="empty-state"><p>No data for current filters.</p></div>';
    }

    return `
        <div class="table-wrap">
            <table class="rules-table">
                <thead>
                    <tr>${cols.map(([, label]) => `<th>${label}</th>`).join('')}</tr>
                </thead>
                <tbody>
                    ${rows.map((row) => `<tr>${cols.map(([key]) => `<td>${row[key] ?? '-'}</td>`).join('')}</tr>`).join('')}
                </tbody>
            </table>
        </div>
    `;
}

function readDependencyFilters() {
    return {
        group: document.getElementById('dep-filter-group')?.value || '',
        field: document.getElementById('dep-filter-field')?.value.trim() || '',
        rule_name: document.getElementById('dep-filter-rule')?.value.trim() || '',
    };
}

function attachDependencyHandlers() {
    document.getElementById('dep-apply-filters')?.addEventListener('click', async () => {
        const summary = await fetchDependencySummary(readDependencyFilters());
        if (summary.__error) return;
        renderDependencyDiagnostics(summary);
    });
}
