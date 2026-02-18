async function loadRules() {
    try {
        const response = await fetchWithAuth(`${API_BASE}/rules`);
        
        if (!response.ok) {
            console.error('Failed to load rules:', response.status);
            const container = document.getElementById('rules-list');
            if (container) {
                container.innerHTML = '<p style="color: red;">Failed to load rules. Please try again.</p>';
            }
            return;
        }
        
        const rules = await response.json();
        console.log('Loaded rules:', rules);

        const container = document.getElementById('rules-list');
        if (!container) {
            console.error('Rules list container not found');
            return;
        }

        container.innerHTML = '';

        if (!rules || rules.length === 0) {
            container.innerHTML = '<div class="card"><p>No rules found. Create your first rule!</p></div>';
            return;
        }

        rules.forEach(rule => {
            const card = createRuleCard(rule);
            container.appendChild(card);
        });
    } catch (error) {
        console.error('Error loading rules:', error);
        const container = document.getElementById('rules-list');
        if (container) {
            container.innerHTML = '<p style="color: red;">Error loading rules: ' + error.message + '</p>';
        }
    }
}

function createRuleCard(rule) {
    const card = document.createElement('div');
    card.className = 'card';

    const header = document.createElement('div');
    header.className = 'card-header';

    const titleSection = document.createElement('div');
    
    const title = document.createElement('div');
    title.className = 'card-title';
    title.textContent = rule.name;

    const meta = document.createElement('div');
    meta.className = 'card-meta';
    meta.innerHTML = `
        <span>Group: ${rule.group || 'None'}</span>
        <span>Priority: ${rule.priority}</span>
        <span>Version: ${rule.current_version}</span>
    `;

    titleSection.appendChild(title);
    titleSection.appendChild(meta);

    const actions = document.createElement('div');
    actions.style.display = 'flex';
    actions.style.gap = '0.5rem';
    actions.style.alignItems = 'center';

    const statusBadge = document.createElement('span');
    statusBadge.className = rule.enabled ? 'badge badge-success' : 'badge badge-danger';
    statusBadge.textContent = rule.enabled ? 'Enabled' : 'Disabled';

    const editBtn = document.createElement('button');
    editBtn.className = 'btn btn-sm';
    editBtn.textContent = 'Edit';
    editBtn.addEventListener('click', () => editRule(rule.id));

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn btn-sm btn-danger';
    deleteBtn.textContent = 'Delete';
    deleteBtn.addEventListener('click', () => deleteRule(rule.id));

    actions.appendChild(statusBadge);
    actions.appendChild(editBtn);
    actions.appendChild(deleteBtn);

    header.appendChild(titleSection);
    header.appendChild(actions);

    const description = document.createElement('p');
    description.textContent = rule.description || 'No description';
    description.style.color = 'var(--text-light)';
    description.style.marginBottom = '1rem';

    const conditionPreview = document.createElement('pre');
    conditionPreview.style.fontSize = '0.813rem';
    conditionPreview.style.background = 'var(--bg)';
    conditionPreview.style.padding = '0.75rem';
    conditionPreview.style.borderRadius = '0.25rem';
    conditionPreview.style.overflow = 'auto';
    conditionPreview.style.maxHeight = '200px';
    
    try {
        const conditionObj = typeof rule.condition_dsl === 'string' 
            ? JSON.parse(rule.condition_dsl) 
            : rule.condition_dsl;
        conditionPreview.textContent = JSON.stringify(conditionObj, null, 2);
    } catch (e) {
        conditionPreview.textContent = rule.condition_dsl;
    }

    card.appendChild(header);
    card.appendChild(description);
    card.appendChild(conditionPreview);

    return card;
}

async function deleteRule(ruleId) {
    if (!confirm('Are you sure you want to delete this rule?')) {
        return;
    }

    try {
        const response = await fetchWithAuth(`${API_BASE}/rules/${ruleId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            alert('Rule deleted successfully!');
            loadRules();
        } else {
            const error = await response.json();
            alert('Error deleting rule: ' + (error.detail || 'Unknown error'));
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}