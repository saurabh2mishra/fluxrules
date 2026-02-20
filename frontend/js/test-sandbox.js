// frontend/js/test-sandbox.js

// Initialize test sandbox when navigating to the page
function initTestSandbox() {
    console.log('🧪 Initializing Test Sandbox');
    
    // Attach event listeners
    const runBtn = document.getElementById('run-test');
    const clearBtn = document.getElementById('clear-test');
    
    console.log('Run button found:', !!runBtn);
    console.log('Clear button found:', !!clearBtn);
    
    if (runBtn) {
        // Remove existing listeners to avoid duplicates
        runBtn.replaceWith(runBtn.cloneNode(true));
        const newRunBtn = document.getElementById('run-test');
        newRunBtn.addEventListener('click', function(e) {
            console.log('🚀 Run Test button clicked!');
            runTest();
        });
        console.log('Run button listener attached');
    }
    
    if (clearBtn) {
        clearBtn.replaceWith(clearBtn.cloneNode(true));
        const newClearBtn = document.getElementById('clear-test');
        newClearBtn.addEventListener('click', function(e) {
            console.log('🧹 Clear button clicked!');
            clearTest();
        });
        console.log('Clear button listener attached');
    }
}

function clearTest() {
    document.getElementById('test-event').value = '';
    document.getElementById('sandbox-results').innerHTML = '';
}

async function runTest() {
    console.log('📝 runTest() called');
    const eventText = document.getElementById('test-event').value.trim();
    const resultsContainer = document.getElementById('sandbox-results');
    
    console.log('Event text:', eventText);
    console.log('Results container:', !!resultsContainer);
    
    if (!eventText) {
        resultsContainer.innerHTML = `
            <div class="empty-state">
                <div style="font-size:2.5rem;">🧪</div>
                <h3>No Event Entered</h3>
                <p>Please enter a JSON event to test your rules.</p>
                <button class="btn btn-primary" onclick="document.getElementById('test-event').value = '{\n  \"amount\": 15000, \"type\": \"transfer\", \"country\": \"US\"\n}';">Insert Example Event</button>
            </div>
        `;
        return;
    }
    
    let event;
    try {
        event = JSON.parse(eventText);
        console.log('Parsed event:', event);
    } catch (error) {
        console.error('JSON parse error:', error);
        resultsContainer.innerHTML = `<div class="test-results error"><h3>❌ Invalid JSON</h3><p>${error.message}</p></div>`;
        return;
    }
    
    // Show loading
    resultsContainer.innerHTML = '<div class="test-results warning"><h3>🔄 Running...</h3><p>Evaluating rules against your event...</p></div>';
    
    try {
        console.log('Calling API:', `${API_BASE}/rules/simulate`);
        const response = await fetchWithAuth(`${API_BASE}/rules/simulate`, {
            method: 'POST',
            body: JSON.stringify({ event })
        });

        if (!response.ok) {
            const errorText = await response.text();
            resultsContainer.innerHTML = `<div class="test-results error"><h3>❌ Error</h3><p>Server error: ${errorText}</p></div>`;
            return;
        }

        const result = await response.json();
        displayTestResults(result);
    } catch (error) {
        resultsContainer.innerHTML = `<div class="test-results error"><h3>❌ Error</h3><p>${error.message}</p></div>`;
    }
}

function displayTestResults(result) {
    const container = document.getElementById('sandbox-results');
    if (!container) return;

    container.innerHTML = '';
    
    // Show stats if available
    const statsHtml = result.stats ? `
        <div class="test-stats">
            <span>Total Rules: ${result.stats.total_rules || 'N/A'}</span>
            <span>Evaluated: ${result.stats.candidates_evaluated || 'N/A'}</span>
            <span>Time: ${result.stats.evaluation_time_ms || 'N/A'}ms</span>
            <span>Engine: ${result.stats.optimization || 'simple'}</span>
        </div>
    ` : '';

    if (result.matched_rules.length === 0) {
        container.innerHTML = `
            <div class="test-results warning">
                <h3>📭 No Rules Matched</h3>
                <p>No rules matched the provided event. Try modifying your event data or check your rule conditions.</p>
                ${statsHtml}
            </div>
        `;
        return;
    }

    // Success - rules matched
    let html = `
        <div class="test-results success">
            <h3>✅ ${result.matched_rules.length} Rule(s) Matched</h3>
            ${statsHtml}
        </div>
    `;

    result.matched_rules.forEach((rule, idx) => {
        html += `
            <div class="matched-rule-card">
                <div class="rule-header">
                    <span class="rule-order">#${idx + 1}</span>
                    <strong>${rule.name}</strong>
                    <span class="rule-priority">Priority: ${rule.priority}</span>
                </div>
                <div class="rule-details">
                    <p><strong>Action:</strong> <code>${rule.action}</code></p>
                    ${result.explanations && result.explanations[rule.id] ? 
                        `<p><strong>Explanation:</strong> ${result.explanations[rule.id]}</p>` : ''}
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}