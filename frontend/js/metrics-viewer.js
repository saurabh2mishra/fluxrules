// frontend/js/metrics-viewer.js

async function loadMetrics() {
    const container = document.getElementById('metrics-container');
    if (!container) return;
    
    container.innerHTML = '<div class="loading">Loading metrics...</div>';
    
    try {
        const response = await fetchWithAuth(`${API_BASE}/metrics/dashboard`);
        
        if (!response.ok) {
            throw new Error('Failed to load metrics');
        }
        
        const data = await response.json();
        if (!data || !data.rules) {
            container.innerHTML = `
                <div class="empty-state">
                    <div style="font-size:2.5rem;">📊</div>
                    <h3>No Metrics Available</h3>
                    <p>There are no rules or events to show metrics for yet.</p>
                    <button class="btn btn-primary" onclick="showPage('create')">+ Create Rule</button>
                </div>
            `;
            return;
        }
        renderDashboard(data);
    } catch (error) {
        console.error('Error loading metrics:', error);
        container.innerHTML = '<div class="error-message">Error loading metrics. Please try again.</div>';
    }
}

function renderDashboard(data) {
    const container = document.getElementById('metrics-container');
    if (!container) return;
    
    container.innerHTML = `
        <div class="metrics-dashboard">
            <!-- Rules Section -->
            <div class="metrics-section">
                <h3>📋 Rules Overview</h3>
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-value">${data.rules.total}</div>
                        <div class="metric-label">Total Rules</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">${data.rules.enabled}</div>
                        <div class="metric-label">Enabled</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">${data.rules.disabled}</div>
                        <div class="metric-label">Disabled</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">${data.rules.groups}</div>
                        <div class="metric-label">Groups</div>
                    </div>
                </div>
            </div>
            
            <!-- Processing Section -->
            <div class="metrics-section">
                <h3>⚡ Processing Statistics</h3>
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-value">${data.processing.events_processed}</div>
                        <div class="metric-label">Events Processed</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">${data.processing.rules_fired}</div>
                        <div class="metric-label">Rules Fired</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">${data.processing.total_evaluations}</div>
                        <div class="metric-label">Total Evaluations</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">${data.processing.avg_processing_time_ms} ms</div>
                        <div class="metric-label">Avg Processing Time</div>
                    </div>
                </div>
            </div>
            
            <!-- Engine Section -->
            <div class="metrics-section">
                <h3>🔧 Engine Status</h3>
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-value">${data.engine.type}</div>
                        <div class="metric-label">Engine Type</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value status-badge">${data.engine.status}</div>
                        <div class="metric-label">Status</div>
                    </div>
                </div>
            </div>
            
            <div class="metrics-footer">
                <button class="btn btn-sm" onclick="loadMetrics()">🔄 Refresh</button>
                <span class="last-updated">Last updated: ${new Date().toLocaleTimeString()}</span>
            </div>
        </div>
    `;
}