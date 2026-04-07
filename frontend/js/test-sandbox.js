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

function insertExampleEvent() {
    const exampleEvent = {
        "amount": 15000,
        "type": "transfer",
        "country": "US",
        "user_id": "user_12345",
        "account_age": 30
    };
    document.getElementById('test-event').value = JSON.stringify(exampleEvent, null, 2);
    // Clear the results area so user knows to click Run Test
    document.getElementById('sandbox-results').innerHTML = `
        <div class="empty-state">
            <div style="font-size:2.5rem;">✅</div>
            <h3>Example Event Inserted</h3>
            <p>Click <strong>Run Test</strong> to evaluate this event against your rules.</p>
        </div>
    `;
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
                <button class="btn btn-primary" onclick="insertExampleEvent()">Insert Example Event</button>
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
        const explanation = result.explanations && result.explanations[rule.id] 
            ? formatExplanation(result.explanations[rule.id]) 
            : '';
        
        html += `
            <div class="matched-rule-card">
                <div class="rule-header">
                    <span class="rule-order">#${idx + 1}</span>
                    <strong>${rule.name}</strong>
                    <span class="rule-priority">Priority: ${rule.priority}</span>
                </div>
                <div class="rule-details">
                    <p><strong>Action:</strong> <code>${rule.action}</code></p>
                    ${explanation}
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

/**
 * Format the explanation with styled pass/fail indicators
 */
function formatExplanation(explanation) {
    if (!explanation) return '';
    
    // Split by the pipe separator to get main explanation and matching conditions
    const parts = explanation.split(' | ');
    const mainExplanation = parts[0];
    const matchingConditions = parts[1] || '';
    
    // Format the main explanation with colored indicators
    let formatted = mainExplanation
        // Style passing conditions [✓ ...]
        .replace(/\[✓([^\]]+)\]/g, '<span class="condition-pass">[✓$1]</span>')
        // Style failing conditions with missing fields [✗ ...=MISSING ...]
        .replace(/\[✗([^=]+)=MISSING([^\]]+)\]/g, '<span class="condition-missing">[✗$1=MISSING$2]</span>')
        // Style other failing conditions [✗ ...]
        .replace(/\[✗([^\]]+)\]/g, '<span class="condition-fail">[✗$1]</span>');
    
    let html = `<div class="rule-explanation">${formatted}</div>`;
    
    // Add matching conditions summary if present
    if (matchingConditions) {
        html += `<div class="matching-conditions"><strong>✓ Why it matched:</strong> ${matchingConditions.replace('Matching conditions: ', '')}</div>`;
    }
    
    return html;
}