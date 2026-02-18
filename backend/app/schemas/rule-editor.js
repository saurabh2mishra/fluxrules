// frontend/js/rule-editor.js
async function editRule(ruleId) {
    try {
        const response = await fetchWithAuth(`${API_BASE}/rules/${ruleId}`);
        const rule = await response.json();

        document.getElementById('edit-rule-id').value = rule.id;
        document.getElementById('edit-rule-name').value = rule.name;
        document.getElementById('edit-rule-description').value = rule.description || '';
        document.getElementById('edit-rule-group').value = rule.group || '';
        document.getElementById('edit-rule-priority').value = rule.priority;
        document.getElementById('edit-rule-enabled').checked = rule.enabled;
        document.getElementById('edit-rule-action').value = rule.action;

        conditionTree = typeof rule.condition_dsl === 'string' ? JSON.parse(rule.condition_dsl) : rule.condition_dsl;
        renderConditionBuilder('edit-condition-builder', conditionTree);

        showPage('edit');

        setupEditForm();
    } catch (error) {
        const msg = error && error.message ? error.message : (typeof error === 'object' ? JSON.stringify(error, null, 2) : String(error));
        alert(`Error: ${msg}`);
    }
}

function setupEditForm() {
    document.getElementById('edit-form')?.removeEventListener('submit', handleEditSubmit);
    document.getElementById('edit-form')?.addEventListener('submit', handleEditSubmit);

    document.getElementById('cancel-edit')?.addEventListener('click', () => {
        showPage('rules');
    });

    document.getElementById('view-versions')?.addEventListener('click', async () => {
        const ruleId = document.getElementById('edit-rule-id').value;
        await loadVersions(ruleId);
    });

    document.getElementById('edit-condition-dsl')?.addEventListener('input', (e) => {
        try {
            conditionTree = JSON.parse(e.target.value);
            renderConditionBuilder('edit-condition-builder', conditionTree);
        } catch (err) {
        }
    });
}

async function handleEditSubmit(e) {
    e.preventDefault();

    const ruleId = document.getElementById('edit-rule-id').value;
    const name = document.getElementById('edit-rule-name').value;
    const description = document.getElementById('edit-rule-description').value;
    const group = document.getElementById('edit-rule-group').value;
    const priority = parseInt(document.getElementById('edit-rule-priority').value);
    const enabled = document.getElementById('edit-rule-enabled').checked;
    const action = document.getElementById('edit-rule-action').value;
    let condition_dsl;
    try {
        condition_dsl = JSON.parse(document.getElementById('edit-condition-dsl').value);
    } catch (e) {
        alert('Invalid condition DSL JSON format');
        return;
    }

    const ruleData = {
        id: ruleId,
        name,
        description,
        group,
        action,
        priority,
        enabled,
        condition_dsl: dslObj  
    };


    try {
        const response = await fetchWithAuth(`${API_BASE}/rules/${ruleId}`, {
            method: 'PUT',
            body: JSON.stringify(ruleData)
        });

        if (response.ok) {
            alert('Rule updated successfully!');
            showPage('rules');
        } else {
            const error = await response.json();
            if (error.detail) {
                if (typeof error.detail === 'string') {
                    alert(`Error: ${error.detail}`);
                } else {
                    alert(`Error: ${JSON.stringify(error.detail, null, 2)}`);
                }
            } else {
                alert('Error updating rule');
            }
        }
    } catch (error) {
        const msg = error && error.message ? error.message : (typeof error === 'object' ? JSON.stringify(error, null, 2) : String(error));
        alert(`Error: ${msg}`);
    }
}