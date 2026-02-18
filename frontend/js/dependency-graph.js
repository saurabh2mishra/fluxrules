// frontend/js/dependency-graph.js
async function loadDependencyGraph() {
    try {
        const response = await fetchWithAuth(`${API_BASE}/rules/graph/dependencies`);
        const graph = await response.json();

        renderGraph(graph);
    } catch (error) {
        console.error('Error loading graph:', error);
    }
}

function renderGraph(graph) {
    const container = document.getElementById('dependency-graph');
    if (!container) return;

    container.innerHTML = '';

    const width = container.clientWidth || 1000;
    const height = 600;

    const svg = d3.select('#dependency-graph')
        .append('svg')
        .attr('width', width)
        .attr('height', height);

    const simulation = d3.forceSimulation(graph.nodes)
        .force('link', d3.forceLink(graph.edges).id(d => d.id).distance(150))
        .force('charge', d3.forceManyBody().strength(-300))
        .force('center', d3.forceCenter(width / 2, height / 2));

    const link = svg.append('g')
        .selectAll('line')
        .data(graph.edges)
        .enter()
        .append('line')
        .attr('stroke', '#999')
        .attr('stroke-width', 2);

    const node = svg.append('g')
        .selectAll('circle')
        .data(graph.nodes)
        .enter()
        .append('circle')
        .attr('r', 20)
        .attr('fill', '#3b82f6')
        .call(d3.drag()
            .on('start', dragstarted)
            .on('drag', dragged)
            .on('end', dragended));

    const label = svg.append('g')
        .selectAll('text')
        .data(graph.nodes)
        .enter()
        .append('text')
        .text(d => d.name)
        .attr('font-size', 12)
        .attr('dx', 25)
        .attr('dy', 4);

    simulation.on('tick', () => {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);

        node
            .attr('cx', d => d.x)
            .attr('cy', d => d.y);

        label
            .attr('x', d => d.x)
            .attr('y', d => d.y);
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
}