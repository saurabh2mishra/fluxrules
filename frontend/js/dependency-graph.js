async function loadDependencyGraph() {
    const container = document.getElementById('dependency-graph');
    if (!container) return;
    
    container.innerHTML = '<div class="loading">Loading dependency graph...</div>';
    
    try {
        const response = await fetchWithAuth(`${API_BASE}/rules/graph/dependencies`);
        const graph = await response.json();

        renderGraph(graph);
    } catch (error) {
        console.error('Error loading graph:', error);
        container.innerHTML = '<div class="error-message">Error loading dependency graph. Please try again.</div>';
    }
}

function renderGraph(graph) {
    const container = document.getElementById('dependency-graph');
    if (!container) return;

    container.innerHTML = '';
    
    // Show message if no rules or no connections
    if (!graph.nodes || graph.nodes.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div style="font-size:2.5rem;">🕸️</div>
                <h3>No Rules Found</h3>
                <p>There are no rules to display in the dependency graph.</p>
            </div>
        `;
        return;
    }
    
    if (graph.nodes.length === 1) {
        container.innerHTML = `
            <div class="empty-state">
                <div style="font-size:2.5rem;">🕸️</div>
                <h3>Single Rule</h3>
                <p>You have 1 rule: <strong>${graph.nodes[0].name}</strong></p>
                <p>Dependencies will appear when multiple rules share fields.</p>
            </div>
        `;
        return;
    }
    
    if (graph.edges.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div style="font-size:2.5rem;">🕸️</div>
                <h3>No Dependencies Found</h3>
                <p>You have ${graph.nodes.length} rules, but they don't share any fields.</p>
                <p>Rules are connected when they check the same fields (e.g., both check "amount").</p>
                <div class="rule-list-mini">
                    ${graph.nodes.map(n => `<span class="rule-chip">${n.name}</span>`).join('')}
                </div>
            </div>
        `;
        return;
    }

    // Calculate statistics
    const totalRules = graph.nodes.length;
    const totalConnections = graph.edges.length;
    const sharedFields = [...new Set(graph.edges.map(e => e.shared_field || e.label || 'field').filter(Boolean))];
    
    // Count connections per node
    const connectionCount = {};
    graph.nodes.forEach(n => connectionCount[n.id] = 0);
    graph.edges.forEach(e => {
        connectionCount[e.source.id || e.source]++;
        connectionCount[e.target.id || e.target]++;
    });
    
    // Get most connected rules
    const mostConnected = graph.nodes
        .map(n => ({ ...n, connections: connectionCount[n.id] }))
        .sort((a, b) => b.connections - a.connections)
        .slice(0, 5);

    // --- Cluster/grouping logic ---
    // Group nodes by shared fields for clustering
    const clusters = {};
    graph.nodes.forEach(n => {
        const fields = n.fields || [];
        fields.forEach(f => {
            if (!clusters[f]) clusters[f] = [];
            clusters[f].push(n);
        });
    });
    const clusterKeys = Object.keys(clusters);

    // --- Collapsible clusters ---
    let collapsedClusters = {};
    clusterKeys.forEach(k => collapsedClusters[k] = false);

    function toggleCluster(clusterKey) {
        collapsedClusters[clusterKey] = !collapsedClusters[clusterKey];
        renderGraph(graph); // re-render
    }

    // --- Help section expanded state ---
    let helpSectionExpanded = false;

    // --- Minimap ---
    function renderMinimap(nodes, edges) {
        const minimap = document.getElementById('graph-minimap');
        if (!minimap) return;
        minimap.innerHTML = '';
        const miniWidth = 180, miniHeight = 120;
        const svgMini = d3.select(minimap)
            .append('svg')
            .attr('width', miniWidth)
            .attr('height', miniHeight);
        svgMini.append('g')
            .selectAll('line')
            .data(edges)
            .enter()
            .append('line')
            .attr('x1', d => d.source.x / 4)
            .attr('y1', d => d.source.y / 4)
            .attr('x2', d => d.target.x / 4)
            .attr('y2', d => d.target.y / 4)
            .attr('stroke', '#bbb')
            .attr('stroke-width', 0.5);
        svgMini.append('g')
            .selectAll('circle')
            .data(nodes)
            .enter()
            .append('circle')
            .attr('cx', d => d.x / 4)
            .attr('cy', d => d.y / 4)
            .attr('r', 2)
            .attr('fill', '#888');
    }

    // --- Main graph rendering ---
    const wrapper = document.createElement('div');
    wrapper.className = 'graph-layout';
    wrapper.innerHTML = `
        <div class="graph-main">
            <div class="graph-canvas" id="graph-canvas"></div>
            <div class="graph-tooltip" id="graph-tooltip"></div>
            <div class="graph-minimap" id="graph-minimap"></div>
        </div>
        <div class="graph-sidebar">
            <div class="sidebar-section">
                <h4>Clusters</h4>
                <ul class="cluster-list">
                    ${clusterKeys.map(k => `
                        <li>
                            <button class="cluster-toggle" onclick="toggleCluster('${k}')">
                                ${collapsedClusters[k] ? '▶' : '▼'} ${k} (${clusters[k].length})
                            </button>
                        </li>
                    `).join('')}
                </ul>
            </div>
            
            <div class="sidebar-section">
                <h4>Overview</h4>
                <div class="stats-grid">
                    <div class="stat-box">
                        <span class="stat-number">${totalRules}</span>
                        <span class="stat-label">Rules</span>
                    </div>
                    <div class="stat-box">
                        <span class="stat-number">${totalConnections}</span>
                        <span class="stat-label">Connections</span>
                    </div>
                    <div class="stat-box">
                        <span class="stat-number">${sharedFields.length}</span>
                        <span class="stat-label">Shared Fields</span>
                    </div>
                </div>
            </div>
            
            <div class="sidebar-section">
                <h4>🔗 Most Connected Rules</h4>
                <ul class="connected-rules-list">
                    ${mostConnected.map(r => `
                        <li>
                            <span class="rule-name" title="${r.name}">${truncateName(r.name, 25)}</span>
                            <span class="connection-badge">${r.connections}</span>
                        </li>
                    `).join('')}
                </ul>
            </div>
            
            <div class="sidebar-section">
                <h4>Shared Fields</h4>
                <div class="shared-fields-list">
                    ${sharedFields.length > 0 
                        ? sharedFields.map(f => `<span class="field-tag">${f}</span>`).join('') 
                        : '<span class="no-fields">No shared fields</span>'}
                </div>
            </div>
            
            <div class="sidebar-section">
                <h4>Legend</h4>
                <div class="legend-compact">
                    <div class="legend-row">
                        <span class="legend-dot" style="background: #3b82f6;"></span>
                        <span>10-20 connections</span>
                    </div>
                    <div class="legend-row">
                        <span class="legend-dot" style="background: #f59e0b;"></span>
                        <span>30-40 connections</span>
                    </div>
                    <div class="legend-row">
                        <span class="legend-dot" style="background: #ef4444;"></span>
                        <span>50+ connections</span>
                    </div>
                </div>
            </div>
            
            <div class="sidebar-section learn-more">
                <button class="learn-more-btn">
                    <span>📖 How to Read This Graph</span>
                    <span class="chevron">${helpSectionExpanded ? '▲' : '▼'}</span>
                </button>
                <div class="learn-more-content${helpSectionExpanded ? ' expanded' : ''}" id="graph-help-content" style="display:${helpSectionExpanded ? 'block' : 'none'};">
                    <div class="help-block">
                        <strong>What is this graph?</strong>
                        <p>This visualization shows relationships between your business rules based on the data fields they examine.</p>
                    </div>
                    <div class="help-block">
                        <strong>Understanding Connections</strong>
                        <p>Two rules are connected when they both check the same data field. For example, if Rule A checks "amount > 1000" and Rule B checks "amount < 500", they share the "amount" field.</p>
                    </div>
                    <div class="help-block">
                        <strong>Why does this matter?</strong>
                        <ul>
                            <li><strong>Impact Analysis:</strong> When you modify a rule, connected rules might need review.</li>
                            <li><strong>Conflict Detection:</strong> Highly connected rules are more likely to have overlapping or conflicting conditions.</li>
                            <li><strong>Optimization:</strong> Rules checking similar fields can sometimes be consolidated.</li>
                        </ul>
                    </div>
                    <div class="help-block">
                        <strong>Interacting with the Graph</strong>
                        <ul>
                            <li><strong>Hover</strong> over a node to see rule details</li>
                            <li><strong>Drag</strong> nodes to rearrange the layout</li>
                            <li><strong>Scroll</strong> to zoom in/out</li>
                            <li><strong>Click &amp; drag</strong> the background to pan</li>
                            <li>Node <strong>size</strong> indicates number of connections</li>
                            <li>Node <strong>color</strong> indicates connection level (see legend)</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    `;
    container.appendChild(wrapper);

    // --- Event delegation for sidebar ---
    const sidebar = wrapper.querySelector('.graph-sidebar');
    if (sidebar) {
        sidebar.addEventListener('click', function(e) {
            const btn = e.target.closest('.learn-more-btn');
            if (btn) {
                helpSectionExpanded = !helpSectionExpanded;
                renderGraph(graph);
            }
        });
    }

    const canvasContainer = document.getElementById('graph-canvas');
    const tooltip = document.getElementById('graph-tooltip');
    
    const width = canvasContainer.clientWidth || 800;
    const height = canvasContainer.clientHeight || 480;

    // Only clear the graph area, not the whole container
    let canvas = container.querySelector('.graph-canvas');
    if (!canvas) {
        canvas = document.createElement('div');
        canvas.className = 'graph-canvas';
        container.appendChild(canvas);
    }
    canvas.innerHTML = '';

    const svg = d3.select(canvas)
        .append('svg')
        .attr('width', width)
        .attr('height', height);

    const g = svg.append('g');

    // --- Filter nodes/edges for collapsed clusters ---
    let visibleNodes = graph.nodes;
    let visibleEdges = graph.edges;
    clusterKeys.forEach(k => {
        if (collapsedClusters[k]) {
            visibleNodes = visibleNodes.filter(n => !(n.fields || []).includes(k));
            visibleEdges = visibleEdges.filter(e => {
                const srcFields = e.source.fields || [];
                const tgtFields = e.target.fields || [];
                return !srcFields.includes(k) && !tgtFields.includes(k);
            });
        }
    });

    // --- Improved force layout for cluster spacing ---
    const nodeCount = visibleNodes.length;
    const dynamicDistance = Math.max(60, Math.min(120, 700 / Math.sqrt(nodeCount)));
    const dynamicCharge = Math.max(-250, Math.min(-100, -2000 / Math.sqrt(nodeCount)));
    const dynamicCollision = Math.max(10, Math.min(18, 120 / Math.sqrt(nodeCount)));

    const simulation = d3.forceSimulation(visibleNodes)
        .force('link', d3.forceLink(visibleEdges).id(d => d.id).distance(dynamicDistance))
        .force('charge', d3.forceManyBody().strength(dynamicCharge))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(dynamicCollision))
        .force('cluster', d3.forceX().strength(0.12).x(d => {
            // Cluster by first field
            const f = (d.fields && d.fields[0]) || '';
            const idx = clusterKeys.indexOf(f);
            return width * (idx + 1) / (clusterKeys.length + 1);
        }));

    // Draw edges
    const link = g.append('g')
        .selectAll('line')
        .data(graph.edges)
        .enter()
        .append('line')
        .attr('stroke', 'var(--text-light)')
        .attr('stroke-opacity', 0.25)
        .attr('stroke-width', 0.7);

    // Draw nodes
    const node = g.append('g')
        .selectAll('circle')
        .data(visibleNodes)
        .enter()
        .append('circle')
        .attr('r', d => Math.min(4 + (connectionCount[d.id] * 1.1), 10))
        .attr('fill', d => getNodeColor(connectionCount[d.id]))
        .attr('stroke', 'var(--card)')
        .attr('stroke-width', 1)
        .attr('cursor', 'pointer')
        .call(d3.drag()
            .on('start', dragstarted)
            .on('drag', dragged)
            .on('end', dragended))
        .on('mouseover', (event, d) => showTooltip(event, d, connectionCount[d.id], visibleEdges))
        .on('mouseout', hideTooltip);

    // Node labels
    const label = g.append('g')
        .selectAll('text')
        .data(visibleNodes)
        .enter()
        .append('text')
        .text(d => truncateName(d.name, 10))
        .attr('font-size', 7)
        .attr('font-weight', '400')
        .attr('fill', 'var(--text)')
        .attr('text-anchor', 'middle')
        .attr('dy', d => Math.min(4 + (connectionCount[d.id] * 1.1), 10) + 7);

    simulation.on('tick', () => {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);

        node
            .attr('cx', d => d.x = Math.max(10, Math.min(width - 10, d.x)))
            .attr('cy', d => d.y = Math.max(10, Math.min(height - 10, d.y)));

        label
            .attr('x', d => d.x)
            .attr('y', d => d.y);

        renderMinimap(visibleNodes, visibleEdges);
    });

    function dragstarted(event, d) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }

    function dragged(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }

    function dragended(event, d) {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }

    function showTooltip(event, d, connections, edges) {
        const relatedEdges = edges.filter(e => 
            (e.source.id || e.source) === d.id || (e.target.id || e.target) === d.id
        );
        const sharedFields = relatedEdges.map(e => e.shared_field || e.label || '').filter(Boolean);
        const uniqueFields = [...new Set(sharedFields)];
        
        tooltip.innerHTML = `
            <div class="tooltip-title">${d.name}</div>
            <div class="tooltip-row"><span>Priority:</span> <strong>${d.priority || 'N/A'}</strong></div>
            <div class="tooltip-row"><span>Connections:</span> <strong>${connections}</strong></div>
            ${uniqueFields.length > 0 ? `<div class="tooltip-row"><span>Shared:</span> <strong>${uniqueFields.join(', ')}</strong></div>` : ''}
        `;
        tooltip.style.display = 'block';
        tooltip.style.left = (event.pageX + 15) + 'px';
        tooltip.style.top = (event.pageY - 10) + 'px';
    }

    function hideTooltip() {
        tooltip.style.display = 'none';
    }
}

function getNodeColor(connections) {
    if (connections >= 50) return '#ef4444';
    if (connections >= 20) return '#f59e0b';
    if (connections >= 10) return '#3b82f6';
    return '#6b7280';
}

function truncateName(name, maxLength) {
    if (!name) return '';
    if (name.length <= maxLength) return name;
    return name.substring(0, maxLength - 3) + '...';
}