window.setupJSONEditor = function(textareaId, statusId) {
    const textarea = document.getElementById(textareaId);
    const status = document.getElementById(statusId);

    if (!textarea) return;

    textarea.addEventListener("input", () => {
        try {
            JSON.parse(textarea.value);
            status.textContent = "✓ Valid JSON";
            status.style.color = "green";
        } catch {
            status.textContent = "✗ Invalid JSON";
            status.style.color = "red";
        }
    });
};

// Ensure conditionTree is global and shared
window.conditionTree = window.conditionTree || null;

// Use a separate variable for Edit Rule
window.editConditionTree = null;

// Use shared render and sync functions from rule-builder.js
window.syncFullSchemaToTextarea = window.syncFullSchemaToTextarea || function(){};
window.renderConditionBuilderOnly = window.renderConditionBuilderOnly || function(){};

// Global editRule function (async)
window.editRule = window.editRule;
window.editRule = async function(ruleId) {
    window.clearEditTestResults();
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

        // Assign condition DSL to editConditionTree
        window.editConditionTree = rule.condition_dsl;
        if (!window.editConditionTree || typeof window.editConditionTree !== 'object' || !window.editConditionTree.op) {
            window.editConditionTree = { type: 'group', op: 'AND', children: [] };
        }
        renderEditConditionBuilder('edit-condition-builder');

        // Set JSON textarea
        const textarea = document.getElementById('edit-condition-dsl');
        if (textarea) {
            textarea.value = JSON.stringify(window.editConditionTree, null, 2);
            textarea.addEventListener('input', function() {
                try {
                    const parsed = JSON.parse(textarea.value);
                    window.editConditionTree = parsed;
                    renderEditConditionBuilder('edit-condition-builder');
                } catch (err) {
                    // Ignore invalid JSON
                }
            });
        }

        showPage('edit');
        window.setupEditForm();
    } catch (error) {
        console.error('Edit error:', error);
        alert(`Error loading rule: ${error.message}`);
    }
};

// Render function for Edit Rule
window.renderEditConditionBuilder = function(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';
    container.appendChild(buildEditGroupNode(window.editConditionTree, []));
    // Update JSON textarea
    const textarea = document.getElementById('edit-condition-dsl');
    if (textarea) {
        textarea.value = JSON.stringify(window.editConditionTree, null, 2);
    }
};

// Edit-specific group node builder
function buildEditGroupNode(node, path) {
    if (!node || typeof node !== 'object' || !node.op) {
        node = { type: 'group', op: 'AND', children: [] };
    }
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
        window.renderEditConditionBuilder('edit-condition-builder');
    };
    const addCondBtn = document.createElement('button');
    addCondBtn.textContent = '+ Condition';
    addCondBtn.className = 'btn btn-sm';
    addCondBtn.type = 'button';
    addCondBtn.onclick = function() {
        if (!node.children) node.children = [];
        node.children.push({type: 'condition', field: '', op: '==', value: ''});
        window.renderEditConditionBuilder('edit-condition-builder');
    };
    const addGroupBtn = document.createElement('button');
    addGroupBtn.textContent = '+ Group';
    addGroupBtn.className = 'btn btn-sm';
    addGroupBtn.type = 'button';
    addGroupBtn.onclick = function() {
        if (!node.children) node.children = [];
        node.children.push({type: 'group', op: 'AND', children: []});
        window.renderEditConditionBuilder('edit-condition-builder');
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
                ? buildEditGroupNode(child, childPath)
                : buildConditionNode(child, childPath);
            const removeBtn = document.createElement('button');
            removeBtn.textContent = '×';
            removeBtn.className = 'btn btn-sm btn-danger';
            removeBtn.type = 'button';
            removeBtn.style.marginLeft = 'auto';
            removeBtn.onclick = function() {
                node.children.splice(idx, 1);
                window.renderEditConditionBuilder('edit-condition-builder');
            };
            childDiv.appendChild(removeBtn);
            childrenDiv.appendChild(childDiv);
        });
    }
    div.appendChild(childrenDiv);
    return div;
}

// Global setupEditForm function
window.setupEditForm = function() {
    // Tab buttons
    document.querySelectorAll('.tab-btn[data-tab^="edit-"]').forEach(btn => {
        btn.onclick = function() {
            this.parentElement.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            document.getElementById('edit-visual-tab').classList.toggle('active', this.dataset.tab === 'edit-visual');
            document.getElementById('edit-json-tab').classList.toggle('active', this.dataset.tab === 'edit-json');
        };
    });

    // JSON editor
    window.setupJSONEditor('edit-condition-dsl', 'edit-json-status');

    // Form submit
    const form = document.getElementById('edit-form');
    if (form) form.onsubmit = window.handleEditSubmit;

    document.getElementById('cancel-edit').onclick = () => showPage('rules');
    document.getElementById('view-versions').onclick = async () => {
        const ruleId = document.getElementById('edit-rule-id').value;
        await loadVersions(ruleId);
    };
};

// Global handleEditSubmit function
window.handleEditSubmit = async function(e) {
    e.preventDefault();

    const ruleId = document.getElementById('edit-rule-id').value;
    const name = document.getElementById('edit-rule-name').value;
    const description = document.getElementById('edit-rule-description').value;
    const group = document.getElementById('edit-rule-group').value;
    const priority = parseInt(document.getElementById('edit-rule-priority').value);
    const enabled = document.getElementById('edit-rule-enabled').checked;
    const action = document.getElementById('edit-rule-action').value;

    let dslObj;

    try {
        const textarea = document.getElementById('edit-condition-dsl');
        let raw = textarea.value;

        // Defensive fix for object
        if (raw === '[object Object]') {
            raw = JSON.stringify(conditionTree);
        }

        if (typeof raw !== 'string') raw = JSON.stringify(raw);

        dslObj = JSON.parse(raw);
    } catch (e) {
        alert('Invalid condition DSL JSON: ' + e.message);
        return;
    }

    // Merge form fields into DSL JSON
    dslObj.name = name;
    dslObj.description = description;
    dslObj.group = group;
    dslObj.action = action;

    // Only send fields allowed by RuleUpdate schema
    const ruleUpdateData = {
        name,
        description,
        group,
        priority,
        enabled,
        action,
        condition_dsl: window.editConditionTree || dslObj.condition_dsl || dslObj
    };

    try {
        const response = await fetchWithAuth(`${API_BASE}/rules/${ruleId}`, {
            method: 'PUT',
            body: JSON.stringify(ruleUpdateData)
        });

        if (response.ok) {
            alert('Rule updated successfully!');
            showPage('rules');
            loadRules(true); // Force reload rules from backend
        } else {
            let errorMsg = 'Error updating rule';
            try {
                const error = await response.json();
                if (error.detail && error.detail.conflicts) {
                    let msg = error.detail.message + '\n\nConflicts:\n';
                    error.detail.conflicts.forEach(c => msg += `- ${c.description}\n`);
                    errorMsg = msg;
                } else if (error.detail) {
                    errorMsg = typeof error.detail === 'string' ? `Error: ${error.detail}` : `Error: ${JSON.stringify(error.detail, null, 2)}`;
                } else {
                    errorMsg = 'Error: ' + JSON.stringify(error);
                }
            } catch {
                errorMsg = 'Error: ' + (await response.text());
            }
            alert(errorMsg);
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
};

// --- Edit Rule Test Feature ---
let editDuplicateNameConflict = false; // Track duplicate name conflict for Edit Rule

window.testEditRule = async function() {
    const ruleId = document.getElementById('edit-rule-id').value;
    const name = document.getElementById('edit-rule-name').value.trim();
    const description = document.getElementById('edit-rule-description').value.trim();
    const group = document.getElementById('edit-rule-group').value.trim();
    const priority = parseInt(document.getElementById('edit-rule-priority').value) || 0;
    const enabled = document.getElementById('edit-rule-enabled').checked;
    const action = document.getElementById('edit-rule-action').value.trim();
    
    // Use editConditionTree for condition_dsl
    const conditionDsl = window.editConditionTree || { type: 'group', op: 'AND', children: [] };
    
    // Build rule data for validation
    const ruleData = {
        name: name,
        description: description || null,
        group: group || null,
        priority: priority,
        enabled: enabled,
        condition_dsl: conditionDsl,
        action: action
    };
    
    // Show loading state
    showEditTestResults('warning', '🔄 Testing...', '<p>Validating rule and checking for conflicts...</p>');
    editDuplicateNameConflict = false;
    try {
        const response = await fetchWithAuth(`${API_BASE}/rules/validate?rule_id=${encodeURIComponent(ruleId)}`, {
            method: 'POST',
            body: JSON.stringify(ruleData)
        });
        if (!response.ok) {
            const errorText = await response.text();
            showEditTestResults('error', '❌ Validation Error', `<p>Server error: ${errorText}</p>`);
            return;
        }
        const result = await response.json();
        console.log('Validation API response:', result);
        let html = '';
        let hasDuplicateName = false;
        // Show conflicts
        if (result.conflicts && result.conflicts.length > 0) {
            html += '<div class="conflicts-section">';
            html += '<h4>⚠️ Conflicts Found:</h4>';
            result.conflicts.forEach(conflict => {
                if (conflict.type === 'duplicate_name' && conflict.existing_rule_id !== parseInt(ruleId)) {
                    hasDuplicateName = true;
                    html += `<div class="conflict-item" style="color: #b30000; font-weight: bold;">`;
                    html += `<strong>🚫 Duplicate Name</strong>`;
                    html += `<p>This rule name is already in use. Please choose a unique name.</p>`;
                    html += `<small>Existing Rule: <a href='#' onclick='viewRule(${conflict.existing_rule_id}); return false;'>${conflict.existing_rule_name}</a> (ID: ${conflict.existing_rule_id})</small>`;
                    html += `</div>`;
                } else {
                    html += `<div class="conflict-item">`;
                    const typeLabel = conflict.type === 'duplicate_condition' ? '🔄 Duplicate Condition'
                        : conflict.type === 'priority_collision' ? '⚡ Priority Collision'
                        : conflict.type === 'brms_overlap' ? '🔀 Condition Overlap'
                        : conflict.type === 'brms_dead_rule' ? '💀 Dead Rule'
                        : '⚠️ Conflict';
                    html += `<strong>${typeLabel}</strong>`;
                    html += `<p>${conflict.description}</p>`;
                    html += `<small>Existing Rule: <a href='#' onclick='viewRule(${conflict.existing_rule_id}); return false;'>${conflict.existing_rule_name}</a> (ID: ${conflict.existing_rule_id})</small>`;
                    html += `</div>`;
                }
            });
            html += '</div>';
        }
        // Show similar rules
        if (result.similar_rules && result.similar_rules.length > 0) {
            html += '<div class="similar-section" style="margin-top: 1rem;">';
            html += '<h4>📋 Similar Existing Rules:</h4>';
            html += '<p style="font-size: 0.875rem; margin-bottom: 0.5rem;">These rules have similarities with your rule:</p>';
            result.similar_rules.forEach(rule => {
                html += `<div class="similar-rule" onclick="viewRule(${rule.rule_id})">`;
                html += `<strong>${rule.rule_name}</strong>`;
                html += `<span style="float: right; font-size: 0.75rem; color: #666;">Similarity: ${rule.similarity_score}%</span>`;
                html += `<br><small>Group: ${rule.group || 'default'} | Reasons: ${rule.reasons.join(', ')}</small>`;
                html += `</div>`;
            });
            html += '</div>';
        }
        // Determine overall status
        if (result.conflicts && result.conflicts.length > 0) {
            if (hasDuplicateName) {
                editDuplicateNameConflict = true;
                html = `<p style='color: #b30000; font-weight: bold;'><strong>🚫 Duplicate rule name detected. Please choose a unique name before saving.</strong></p>` + html;
                showEditTestResults('error', '🚫 Duplicate Name', html);
            } else {
                html = `<p><strong>⚠️ ${result.conflicts.length} conflict(s) found.</strong> Please resolve before saving.</p>` + html;
                showEditTestResults('warning', '⚠️ Conflicts Detected', html);
            }
        } else if (result.similar_rules && result.similar_rules.length > 0) {
            html = `<p><strong>✅ No conflicts found.</strong> However, similar rules exist. Please review to avoid duplicates.</p>` + html;
            showEditTestResults('success', '✅ Rule Valid (With Suggestions)', html);
        } else {
            html = `<p><strong>✅ No conflicts or similar rules found.</strong> Your rule is ready to save!</p>`;
            showEditTestResults('success', '✅ Rule Valid', html);
        }
    } catch (error) {
        showEditTestResults('error', '❌ Error', `<p>Failed to validate rule: ${error.message}</p>`);
    }
};

function showEditTestResults(type, title, content) {
    let section = document.getElementById('edit-test-results-section');
    let div = document.getElementById('edit-test-results');
    if (!section) {
        // Create if not present
        section = document.createElement('div');
        section.id = 'edit-test-results-section';
        section.className = 'form-section';
        section.innerHTML = `<h2>Test Results</h2><div id='edit-test-results' class='test-results'></div>`;
        // Insert after last form-group
        const form = document.getElementById('edit-form');
        const lastGroup = form.querySelector('.form-actions');
        form.insertBefore(section, lastGroup);
        div = document.getElementById('edit-test-results');
    }
    section.style.display = 'block';
    div.className = `test-results ${type}`;
    div.innerHTML = `<h3>${title}</h3>${content}`;
    section.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// Add Test Rule button to Edit form if not present
window.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('edit-form');
    if (form && !document.getElementById('edit-test-rule-btn')) {
        const actions = form.querySelector('.form-actions');
        const testBtn = document.createElement('button');
        testBtn.type = 'button';
        testBtn.className = 'btn btn-secondary';
        testBtn.id = 'edit-test-rule-btn';
        testBtn.textContent = '🧪 Test Rule';
        testBtn.onclick = window.testEditRule;
        actions.insertBefore(testBtn, actions.firstChild);
    }
    // Reset editDuplicateNameConflict when name changes
    const nameInput = document.getElementById('edit-rule-name');
    if (nameInput) {
        nameInput.addEventListener('input', () => {
            editDuplicateNameConflict = false;
        });
    }
});

// Block update if duplicate name conflict
const origHandleEditSubmit = window.handleEditSubmit;
window.handleEditSubmit = async function(e) {
    if (editDuplicateNameConflict) {
        alert('Duplicate rule name detected. Please choose a unique name before saving.');
        e.preventDefault();
        return;
    }
    await origHandleEditSubmit(e);
};
// Clear Edit Rule test results
window.clearEditTestResults = function() {
    const section = document.getElementById('edit-test-results-section');
    if (section) {
        section.style.display = 'none';
        const div = document.getElementById('edit-test-results');
        if (div) {
            div.innerHTML = '';
        }
    }
};
