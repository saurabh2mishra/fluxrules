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

async function fetchDependencyGraph(filters) {
    return fetchDependencyJson(`${API_BASE}/rules/graph/dependencies${toQuery(filters)}`);
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
    if (filters.max_nodes) params.set('max_nodes', String(filters.max_nodes));
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
                <h3>🧭 Dependency Diagnostics (Insight-first)</h3>
                <p class="page-description" style="margin-top:0.25rem;">Graph rendering is optional and limited for large datasets. Use filters to inspect meaningful subsets.</p>
                <div class="filters" style="margin-top:0.5rem; gap:0.5rem; flex-wrap:wrap;">
                    <select id="dep-filter-group">
                        <option value="">All Groups</option>
                        ${groups.map((g) => `<option value="${g}">${g}</option>`).join('')}
                    </select>
                    <input id="dep-filter-field" type="text" placeholder="Field (e.g. amount)">
                    <input id="dep-filter-rule" type="text" placeholder="Rule name contains...">
                    <select id="dep-max-nodes">
                        <option value="100">Max nodes: 100</option>
                        <option value="150" selected>Max nodes: 150</option>
                        <option value="200">Max nodes: 200</option>
                    </select>
                    <button class="btn btn-sm" id="dep-apply-filters">Apply Filters</button>
                    <button class="btn btn-sm" id="dep-render-graph">Render Graph Subset</button>
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

            <div class="metrics-section">
                <h3>🕸️ Filtered Graph (Optional)</h3>
                <div id="dependency-graph-canvas" class="graph-canvas" style="min-height:500px;"></div>
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
        max_nodes: document.getElementById('dep-max-nodes')?.value || '150',
    };
}

function attachDependencyHandlers() {
    document.getElementById('dep-apply-filters')?.addEventListener('click', async () => {
        const summary = await fetchDependencySummary(readDependencyFilters());
        if (summary.__error) return;
        renderDependencyDiagnostics(summary);
    });

    document.getElementById('dep-render-graph')?.addEventListener('click', async () => {
        const graph = await fetchDependencyGraph(readDependencyFilters());
        renderFilteredGraph(graph);
    });
}

function renderFilteredGraph(graph) {
    const holder = document.getElementById('dependency-graph-canvas');
    if (!holder) return;
    holder.innerHTML = '';

    if (!graph || graph.__error) {
        holder.innerHTML = '<div class="error-message">Unable to render graph for selected filters.</div>';
        return;
    }

    if (graph.summary_only) {
        holder.innerHTML = `<div class="empty-state"><h3>Summary Mode Only</h3><p>${graph.message || 'Graph disabled for large datasets. Apply filters.'}</p></div>`;
        return;
    }

    if (!graph.nodes?.length) {
        holder.innerHTML = '<div class="empty-state"><p>No graph nodes for selected filters.</p></div>';
        return;
    }

    const width = Math.max(holder.clientWidth || 800, 800);
    const height = 520;

    const svg = d3.select(holder).append('svg').attr('width', width).attr('height', height);

    const simulation = d3.forceSimulation(graph.nodes)
        .force('link', d3.forceLink(graph.edges).id(d => d.id).distance(70).strength(0.4))
        .force('charge', d3.forceManyBody().strength(-140))
        .force('center', d3.forceCenter(width / 2, height / 2));

    const link = svg.append('g')
        .selectAll('line')
        .data(graph.edges)
        .enter()
        .append('line')
        .attr('stroke', '#94a3b8')
        .attr('stroke-width', d => Math.min(1 + (d.weight || 1), 4));

    const node = svg.append('g')
        .selectAll('circle')
        .data(graph.nodes)
        .enter()
        .append('circle')
        .attr('r', 7)
        .attr('fill', '#3b82f6')
        .call(d3.drag()
            .on('start', (event, d) => {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            })
            .on('drag', (event, d) => {
                d.fx = event.x;
                d.fy = event.y;
            })
            .on('end', (event, d) => {
                if (!event.active) simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            })
        );

    node.append('title').text(d => `${d.name}\nFields: ${(d.fields || []).join(', ')}`);

    simulation.on('tick', () => {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);

        node
            .attr('cx', d => d.x)
            .attr('cy', d => d.y);
    });
}
