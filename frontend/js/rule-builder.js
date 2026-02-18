let conditionTree = null;

function initRuleBuilder() {
    conditionTree = {
        type: 'group',
        op: 'AND',
        children: []
    };

    renderConditionBuilder('condition-builder');

    document.getElementById('rule-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        await saveRule();
    });

    document.getElementById('cancel-rule')?.addEventListener('click', () => {
        showPage('rules');
    });

    const dslTextarea = document.getElementById('condition-dsl');
    if (dslTextarea) {
        // Always set textarea value to string when loading
        dslTextarea.value = JSON.stringify(conditionTree, null, 2);

        dslTextarea.addEventListener('input', (e) => {
            try {
                // Only parse if value is a string
                if (typeof e.target.value === 'string') {
                    conditionTree = JSON.parse(e.target.value);
                    renderConditionBuilder('condition-builder');
                }
            } catch (err) {
                // Invalid JSON
            }
        });
        // When DSL JSON is pasted/edited, sync only the condition builder, not the other fields
        dslTextarea.addEventListener('blur', () => {
            // Re-sync form fields from their own inputs
            document.getElementById('rule-name').value = document.getElementById('rule-name').value;
            document.getElementById('rule-description').value = document.getElementById('rule-description').value;
            document.getElementById('rule-group').value = document.getElementById('rule-group').value;
            document.getElementById('rule-priority').value = document.getElementById('rule-priority').value;
            document.getElementById('rule-enabled').checked = document.getElementById('rule-enabled').checked;
            document.getElementById('rule-action').value = document.getElementById('rule-action').value;
        });
    }
}

function renderConditionBuilder(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = '';
    container.appendChild(buildGroupNode(conditionTree, []));

    syncToTextarea(containerId);
}

function buildGroupNode(node, path) {
    const div = document.createElement('div');
    div.className = 'condition-group';
    div.dataset.path = JSON.stringify(path);

    const header = document.createElement('div');
    header.style.marginBottom = '0.5rem';
    header.style.display = 'flex';
    header.style.gap = '0.5rem';

    const opSelect = document.createElement('select');
    opSelect.innerHTML = '<option value="AND">AND</option><option value="OR">OR</option>';
    opSelect.value = node.op || 'AND';
    opSelect.onchange = function() {
        node.op = this.value;
        syncToTextarea(document.getElementById('condition-builder') ? 'condition-builder' : 'edit-condition-builder');
    };

    const addCondBtn = document.createElement('button');
    addCondBtn.textContent = '+ Condition';
    addCondBtn.className = 'btn btn-sm';
    addCondBtn.type = 'button';
    addCondBtn.onclick = function() {
        if (!node.children) node.children = [];
        node.children.push({type: 'condition', field: '', op: '==', value: ''});
        renderConditionBuilder(document.getElementById('condition-builder') ? 'condition-builder' : 'edit-condition-builder');
    };

    const addGroupBtn = document.createElement('button');
    addGroupBtn.textContent = '+ Group';
    addGroupBtn.className = 'btn btn-sm';
    addGroupBtn.type = 'button';
    addGroupBtn.onclick = function() {
        if (!node.children) node.children = [];
        node.children.push({type: 'group', op: 'AND', children: []});
        renderConditionBuilder(document.getElementById('condition-builder') ? 'condition-builder' : 'edit-condition-builder');
    };

    header.appendChild(opSelect);
    header.appendChild(addCondBtn);
    header.appendChild(addGroupBtn);
    div.appendChild(header);

    const childrenDiv = document.createElement('div');
    if (node.children) {
        node.children.forEach((child, idx) => {
            const childPath = [...path, idx];
            const childDiv = child.type === 'group' 
                ? buildGroupNode(child, childPath)
                : buildConditionNode(child, childPath);
            
            const removeBtn = document.createElement('button');
            removeBtn.textContent = '×';
            removeBtn.className = 'btn btn-sm btn-danger';
            removeBtn.type = 'button';
            removeBtn.style.marginLeft = 'auto';
            removeBtn.onclick = function() {
                node.children.splice(idx, 1);
                renderConditionBuilder(document.getElementById('condition-builder') ? 'condition-builder' : 'edit-condition-builder');
            };
            
            childDiv.appendChild(removeBtn);
            childrenDiv.appendChild(childDiv);
        });
    }
    div.appendChild(childrenDiv);

    return div;
}

function buildConditionNode(node, path) {
    const div = document.createElement('div');
    div.className = 'condition-item';
    div.dataset.path = JSON.stringify(path);

    const fieldInput = document.createElement('input');
    fieldInput.type = 'text';
    fieldInput.placeholder = 'field_name';
    fieldInput.value = node.field || '';
    fieldInput.oninput = function() {
        node.field = this.value.replace(/\s+/g, '');
        syncToTextarea(document.getElementById('condition-builder') ? 'condition-builder' : 'edit-condition-builder');
    };

    fieldInput.onblur = function() {
        node.field = this.value; // or this.value.replace(/\s+/g, '') if you want to remove spaces
        syncToTextarea(document.getElementById('condition-builder') ? 'condition-builder' : 'edit-condition-builder');
    };

    const opSelect = document.createElement('select');
    opSelect.innerHTML = `
        <option value="==">==</option>
        <option value="!=">!=</option>
        <option value=">">></option>
        <option value=">=">>=</option>
        <option value="<"><</option>
        <option value="<="><=</option>
        <option value="in">in</option>
        <option value="contains">contains</option>
    `;
    opSelect.value = node.op || '==';
    opSelect.onchange = function() {
        node.op = this.value;
        syncToTextarea(document.getElementById('condition-builder') ? 'condition-builder' : 'edit-condition-builder');
    };

    const valueInput = document.createElement('input');
    valueInput.type = 'text';
    valueInput.placeholder = 'value';
    valueInput.value = typeof node.value === 'string' ? node.value : JSON.stringify(node.value);
    valueInput.oninput = function() {
        try {
            node.value = JSON.parse(this.value);
        } catch {
            node.value = this.value;
        }
        syncToTextarea(document.getElementById('condition-builder') ? 'condition-builder' : 'edit-condition-builder');
    };

    div.appendChild(fieldInput);
    div.appendChild(opSelect);
    div.appendChild(valueInput);

    return div;
}

let syncTimeout;
function syncToTextarea(containerId) {
    clearTimeout(syncTimeout);
    syncTimeout = setTimeout(() => {
        const textarea = containerId === 'condition-builder' 
            ? document.getElementById('condition-dsl')
            : document.getElementById('edit-condition-dsl');
        if (textarea) {
            textarea.value = JSON.stringify(conditionTree, null, 2);
        }
    }, 300);
}

async function saveRule() {
    const name = document.getElementById('rule-name').value;
    const description = document.getElementById('rule-description').value;
    const group = document.getElementById('rule-group').value;
    const priority = parseInt(document.getElementById('rule-priority').value);
    const enabled = document.getElementById('rule-enabled').checked;
    const action = document.getElementById('rule-action').value;
    
    let dslObj;
    try {
        const dslText = document.getElementById('condition-dsl').value;
        dslObj = JSON.parse(dslText);
    } catch (e) {
        alert('Invalid condition DSL JSON: ' + e.message);
        return;
    }

    // Merge form fields into DSL JSON
    dslObj.name = name;
    dslObj.description = description;
    dslObj.group = group;
    dslObj.action = action;

    const ruleData = {
        ...dslObj,
        priority,
        enabled
    };

    try {
        const response = await fetchWithAuth(`${API_BASE}/rules`, {
            method: 'POST',
            body: JSON.stringify(ruleData)
        });

        if (response.ok) {
            alert('Rule created successfully!');
            showPage('rules');
            loadRules();
        } else {
            const error = await response.json();
            if (error.detail && error.detail.conflicts) {
                let msg = error.detail.message + '\n\n';
                error.detail.conflicts.forEach(c => msg += `- ${c.description}\n`);
                alert(msg);
            } else {
                alert('Error: ' + JSON.stringify(error.detail || error));
            }
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
}