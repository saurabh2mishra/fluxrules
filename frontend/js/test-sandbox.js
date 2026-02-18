// frontend/js/test-sandbox.js
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('run-test')?.addEventListener('click', runTest);
});

async function runTest() {
    const eventText = document.getElementById('test-event').value;
    
    try {
        const event = JSON.parse(eventText);
        
        const response = await fetchWithAuth(`${API_BASE}/rules/simulate`, {
            method: 'POST',
            body: JSON.stringify({ event })
        });

        const result = await response.json();
        displayTestResults(result);
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

function displayTestResults(result) {
    const container = document.getElementById('test-results');
    if (!container) return;

    container.innerHTML = '';

    const summary = document.createElement('div');
    summary.innerHTML = `<h3>Matched ${result.matched_rules.length} rule(s)</h3>`;
    container.appendChild(summary);

    result.matched_rules.forEach((rule, idx) => {
        const ruleCard = document.createElement('div');
        ruleCard.style.marginTop = '1rem';
        ruleCard.style.padding = '1rem';
        ruleCard.style.background = 'var(--bg)';
        ruleCard.style.borderRadius = '0.375rem';

        ruleCard.innerHTML = `
            <h4>${idx + 1}. ${rule.name}</h4>
            <p><strong>Priority:</strong> ${rule.priority}</p>
            <p><strong>Action:</strong> ${rule.action}</p>
            <p><strong>Explanation:</strong> ${result.explanations[rule.id]}</p>
        `;

        container.appendChild(ruleCard);
    });
}