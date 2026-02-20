let conditionTree = null;

// Stepper Wizard Logic
let currentStep = 0;
const totalSteps = 4;

function initRuleBuilder() {
    conditionTree = {
        type: 'group',
        op: 'AND',
        children: []
    };

    renderConditionBuilder('condition-builder');

    // Tab switching for Visual Builder / JSON Editor
    setupTabSwitching();

    document.getElementById('rule-form')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        await saveRule();
    });

    // Save Rule button click handler
    document.getElementById('save-rule-btn')?.addEventListener('click', async () => {
        await saveRule();
    });

    document.getElementById('cancel-rule')?.addEventListener('click', () => {
        showPage('rules');
    });

    // Test Rule button
    document.getElementById('test-rule-btn')?.addEventListener('click', async () => {
        await testRule();
    });

    const dslTextarea = document.getElementById('condition-dsl');
    if (dslTextarea) {
        // Set initial full schema
        syncFullSchemaToTextarea();

        dslTextarea.addEventListener('input', (e) => {
            try {
                if (typeof e.target.value === 'string') {
                    const parsed = JSON.parse(e.target.value);
                    // Sync form fields from JSON
                    if (parsed.name !== undefined) {
                        document.getElementById('rule-name').value = parsed.name || '';
                    }
                    if (parsed.description !== undefined) {
                        document.getElementById('rule-description').value = parsed.description || '';
                    }
                    if (parsed.group !== undefined) {
                        document.getElementById('rule-group').value = parsed.group || '';
                    }
                    if (parsed.priority !== undefined) {
                        document.getElementById('rule-priority').value = parsed.priority || 0;
                    }
                    if (parsed.enabled !== undefined) {
                        document.getElementById('rule-enabled').checked = parsed.enabled;
                    }
                    if (parsed.action !== undefined) {
                        document.getElementById('rule-action').value = parsed.action || '';
                    }
                    // Update condition tree from condition_dsl
                    if (parsed.condition_dsl) {
                        conditionTree = parsed.condition_dsl;
                        renderConditionBuilderOnly('condition-builder');
                    }
                }
            } catch (err) {
                // Invalid JSON - ignore
            }
        });
    }

    // Sync JSON when form fields change
    ['rule-name', 'rule-description', 'rule-group', 'rule-priority', 'rule-action'].forEach(id => {
        document.getElementById(id)?.addEventListener('input', syncFullSchemaToTextarea);
    });
    document.getElementById('rule-enabled')?.addEventListener('change', syncFullSchemaToTextarea);
    
    // Load available actions
    loadAvailableActions();
    
    // Action select change handler
    document.getElementById('rule-action-select')?.addEventListener('change', (e) => {
        const selected = e.target.value;
        updateActionDescription(selected);
        syncActionToHiddenField();
        syncFullSchemaToTextarea();
    });
    
    // Action params change handler
    document.getElementById('rule-action-params')?.addEventListener('input', () => {
        syncActionToHiddenField();
        syncFullSchemaToTextarea();
    });
}

// Store available actions
let availableActions = [];

// Load available actions from API
async function loadAvailableActions() {
    try {
        const response = await fetchWithAuth(`${API_BASE}/rules/actions/available`);
        if (response.ok) {
            const data = await response.json();
            availableActions = data.actions || [];
            populateActionSelect(data.categorized || {});
        }
    } catch (error) {
        console.error('Failed to load actions:', error);
    }
}

// Populate the action dropdown
function populateActionSelect(categorized) {
    const select = document.getElementById('rule-action-select');
    if (!select) return;
    
    // Clear existing options except the first
    select.innerHTML = '<option value="">-- Select an action --</option>';
    
    // Add options grouped by category
    for (const [category, actions] of Object.entries(categorized)) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = category.charAt(0).toUpperCase() + category.slice(1);
        
        actions.forEach(action => {
            const option = document.createElement('option');
            option.value = action.name;
            option.textContent = action.name;
            option.dataset.description = action.description;
            optgroup.appendChild(option);
        });
        
        select.appendChild(optgroup);
    }
}

// Update action description when selection changes
function updateActionDescription(actionName) {
    const descEl = document.getElementById('action-description');
    if (!descEl) return;
    
    const action = availableActions.find(a => a.name === actionName);
    if (action) {
        descEl.textContent = action.description;
    } else {
        descEl.textContent = '';
    }
}

// Sync action select + params to hidden field
function syncActionToHiddenField() {
    const select = document.getElementById('rule-action-select');
    const params = document.getElementById('rule-action-params');
    const hidden = document.getElementById('rule-action');
    
    if (!select || !hidden) return;
    
    const actionName = select.value;
    let actionValue = actionName;
    
    // If params provided, create a JSON string combining action and params
    if (params && params.value.trim()) {
        try {
            const paramsObj = JSON.parse(params.value);
            actionValue = JSON.stringify({ action: actionName, params: paramsObj });
        } catch (e) {
            // Invalid JSON, just use the action name
            actionValue = actionName;
        }
    }
    
    hidden.value = actionValue;
}

// Build the full rule schema for JSON Editor
function getFullRuleSchema() {
    return {
        name: document.getElementById('rule-name')?.value.trim() || '',
        description: document.getElementById('rule-description')?.value.trim() || null,
        group: document.getElementById('rule-group')?.value.trim() || null,
        priority: parseInt(document.getElementById('rule-priority')?.value) || 0,
        enabled: document.getElementById('rule-enabled')?.checked ?? true,
        condition_dsl: conditionTree || { type: 'group', op: 'AND', children: [] },
        action: document.getElementById('rule-action')?.value.trim() || ''
    };
}

// Sync full schema to textarea
function syncFullSchemaToTextarea() {
    const dslTextarea = document.getElementById('condition-dsl');
    if (dslTextarea) {
        dslTextarea.value = JSON.stringify(getFullRuleSchema(), null, 2);
    }
}

// Render condition builder without syncing to textarea (to avoid loops)
function renderConditionBuilderOnly(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';
    container.appendChild(buildGroupNode(conditionTree, []));
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
        if (containerId === 'condition-builder') {
            // For create page, sync full schema
            syncFullSchemaToTextarea();
        } else {
            // For edit page, sync only condition tree
            const textarea = document.getElementById('edit-condition-dsl');
            if (textarea) {
                textarea.value = JSON.stringify(conditionTree, null, 2);
            }
        }
    }, 300);
}

async function saveRule() {
    // Get values from form fields (they are synced with JSON Editor)
    const name = document.getElementById('rule-name').value.trim();
    const description = document.getElementById('rule-description').value.trim();
    const group = document.getElementById('rule-group').value.trim();
    const priority = parseInt(document.getElementById('rule-priority').value) || 0;
    const enabled = document.getElementById('rule-enabled').checked;
    
    // Get action from select or hidden field
    const actionSelect = document.getElementById('rule-action-select');
    const actionParams = document.getElementById('rule-action-params');
    const actionHidden = document.getElementById('rule-action');
    
    let action = '';
    if (actionSelect && actionSelect.value) {
        action = actionSelect.value;
        // Include params if provided
        if (actionParams && actionParams.value.trim()) {
            try {
                const params = JSON.parse(actionParams.value);
                action = JSON.stringify({ action: actionSelect.value, params: params });
            } catch (e) {
                // Keep just the action name if params are invalid JSON
            }
        }
    } else if (actionHidden) {
        action = actionHidden.value.trim();
    }
    
    // Validation
    if (!name) {
        showToast('Please enter a rule name.', 'error');
        return;
    }
    if (!action) {
        showToast('Please select an action.', 'error');
        return;
    }
    
    // Use conditionTree for condition_dsl
    const conditionDsl = conditionTree || { type: 'group', op: 'AND', children: [] };

    // Build rule data matching backend RuleCreate schema
    const ruleData = {
        name: name,
        description: description || null,
        group: group || null,
        priority: priority,
        enabled: enabled,
        condition_dsl: conditionDsl,
        action: action
    };

    console.log('Sending rule data:', JSON.stringify(ruleData, null, 2));

    try {
        const response = await fetchWithAuth(`${API_BASE}/rules`, {
            method: 'POST',
            body: JSON.stringify(ruleData)
        });

        console.log('Response status:', response.status);

        if (response.ok) {
            showToast('Rule created successfully!', 'success');
            showPage('rules');
            loadRules();
        } else {
            // Try to parse error response as JSON
            let errorMsg = 'Error creating rule';
            try {
                const responseData = await response.json();
                console.log('Error response:', responseData);
                
                if (responseData.detail && responseData.detail.conflicts) {
                    errorMsg = responseData.detail.message + '\n\n';
                    responseData.detail.conflicts.forEach(c => errorMsg += `- ${c.description}\n`);
                } else if (Array.isArray(responseData.detail)) {
                    errorMsg = 'Validation errors:\n';
                    responseData.detail.forEach(err => {
                        errorMsg += `- ${err.loc.join('.')}: ${err.msg}\n`;
                    });
                } else {
                    errorMsg = 'Error: ' + JSON.stringify(responseData.detail || responseData);
                }
            } catch (parseError) {
                // Response is not JSON
                const text = await response.text().catch(() => '');
                errorMsg = `Error (${response.status}): ${text || response.statusText}`;
            }
            showToast(errorMsg, 'error');
        }
    } catch (error) {
        console.error('Save rule error:', error);
        showToast('Error: ' + error.message, 'error');
    }
}

// Tab switching for Visual Builder / JSON Editor
function switchTab(tabName) {
    console.log('switchTab called with:', tabName);
    
    // Update tab buttons
    const tabButtons = document.querySelectorAll('.tab-navigation .tab-btn');
    tabButtons.forEach(btn => {
        if (btn.dataset.tab === tabName) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
    
    // Update tab panes
    const visualTab = document.getElementById('visual-tab');
    const jsonTab = document.getElementById('json-tab');
    
    if (tabName === 'visual') {
        if (visualTab) visualTab.classList.add('active');
        if (jsonTab) jsonTab.classList.remove('active');
    } else if (tabName === 'json') {
        if (visualTab) visualTab.classList.remove('active');
        if (jsonTab) jsonTab.classList.add('active');
        
        // Sync full rule schema to JSON textarea
        syncFullSchemaToTextarea();
    }
}

function setupTabSwitching() {
    // This function is kept for backward compatibility but switchTab handles everything now
}

// Test Rule - Validate before saving
async function testRule() {
    const name = document.getElementById('rule-name').value.trim();
    const description = document.getElementById('rule-description').value.trim();
    const group = document.getElementById('rule-group').value.trim();
    const priority = parseInt(document.getElementById('rule-priority').value) || 0;
    const enabled = document.getElementById('rule-enabled').checked;
    const action = document.getElementById('rule-action').value.trim();
    
    const resultsSection = document.getElementById('test-results-section');
    const resultsDiv = document.getElementById('test-results');
    
    // Basic validation
    if (!name) {
        showTestResults('error', '❌ Validation Failed', '<p>Please enter a rule name.</p>');
        return;
    }
    if (!action) {
        showTestResults('error', '❌ Validation Failed', '<p>Please enter an action code.</p>');
        return;
    }
    
    // Use conditionTree for condition_dsl
    const conditionDsl = conditionTree || { type: 'group', op: 'AND', children: [] };
    
    // Build rule data
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
    showTestResults('warning', '🔄 Testing...', '<p>Validating rule and checking for conflicts...</p>');
    
    try {
        const response = await fetchWithAuth(`${API_BASE}/rules/validate`, {
            method: 'POST',
            body: JSON.stringify(ruleData)
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            showTestResults('error', '❌ Validation Error', `<p>Server error: ${errorText}</p>`);
            return;
        }
        
        const result = await response.json();
        console.log('Validation result:', result);
        
        let html = '';
        
        // Show conflicts
        if (result.conflicts && result.conflicts.length > 0) {
            html += '<div class="conflicts-section">';
            html += '<h4>⚠️ Conflicts Found:</h4>';
            result.conflicts.forEach(conflict => {
                html += `<div class="conflict-item">
                    <strong>${conflict.type === 'duplicate_condition' ? '🔄 Duplicate Condition' : '⚡ Priority Collision'}</strong>
                    <p>${conflict.description}</p>
                    <small>Existing Rule: <a href="#" onclick="viewRule(${conflict.existing_rule_id}); return false;">${conflict.existing_rule_name}</a> (ID: ${conflict.existing_rule_id})</small>
                </div>`;
            });
            html += '</div>';
        }
        
        // Show similar rules
        if (result.similar_rules && result.similar_rules.length > 0) {
            html += '<div class="similar-section" style="margin-top: 1rem;">';
            html += '<h4>📋 Similar Existing Rules:</h4>';
            html += '<p style="font-size: 0.875rem; margin-bottom: 0.5rem;">These rules have similarities with your new rule:</p>';
            result.similar_rules.forEach(rule => {
                html += `<div class="similar-rule" onclick="viewRule(${rule.rule_id})">
                    <strong>${rule.rule_name}</strong>
                    <span style="float: right; font-size: 0.75rem; color: #666;">Similarity: ${rule.similarity_score}%</span>
                    <br><small>Group: ${rule.group || 'default'} | Reasons: ${rule.reasons.join(', ')}</small>
                </div>`;
            });
            html += '</div>';
        }
        
        // Determine overall status
        if (result.conflicts && result.conflicts.length > 0) {
            html = `<p><strong>⚠️ ${result.conflicts.length} conflict(s) found.</strong> Please resolve before saving.</p>` + html;
            showTestResults('warning', '⚠️ Conflicts Detected', html);
        } else if (result.similar_rules && result.similar_rules.length > 0) {
            html = `<p><strong>✅ No conflicts found.</strong> However, similar rules exist. Please review to avoid duplicates.</p>` + html;
            showTestResults('success', '✅ Rule Valid (With Suggestions)', html);
        } else {
            html = `<p><strong>✅ No conflicts or similar rules found.</strong> Your rule is ready to save!</p>`;
            showTestResults('success', '✅ Rule Valid', html);
        }
        
    } catch (error) {
        console.error('Test rule error:', error);
        showTestResults('error', '❌ Error', `<p>Failed to validate rule: ${error.message}</p>`);
    }
}

function showTestResults(type, title, content) {
    const resultsSection = document.getElementById('test-results-section');
    const resultsDiv = document.getElementById('test-results');
    
    if (resultsSection && resultsDiv) {
        resultsSection.style.display = 'block';
        resultsDiv.className = `test-results ${type}`;
        resultsDiv.innerHTML = `<h3>${title}</h3>${content}`;
        
        // Scroll to results
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

// View an existing rule (for clicking on similar/conflicting rules)
function viewRule(ruleId) {
    // This would navigate to the edit page for the rule
    showToast(`View rule ID: ${ruleId} (Navigating to edit page...)`, 'info');
    // TODO: Implement navigation to edit rule page
    // editRule(ruleId);
}

// Show/hide steps and update stepper UI
function showStep(step) {
    currentStep = step;
    document.querySelectorAll('.form-step').forEach((el, idx) => {
        el.style.display = idx === step ? 'block' : 'none';
        el.classList.toggle('active', idx === step);
    });
    // Stepper UI
    document.querySelectorAll('.stepper .step').forEach((el, idx) => {
        el.classList.toggle('active', idx === step);
        el.classList.toggle('completed', idx < step);
    });
    // Navigation buttons
    document.getElementById('step-back').style.display = step > 0 ? '' : 'none';
    document.getElementById('step-next').style.display = step < totalSteps - 1 ? '' : 'none';
    document.getElementById('save-rule-btn').style.display = step === totalSteps - 1 ? '' : 'none';
    document.getElementById('test-rule-btn').style.display = step === totalSteps - 1 ? '' : 'none';
    // Review JSON
    if (step === 3) {
        const review = document.getElementById('rule-review-json');
        if (review) review.textContent = JSON.stringify(getFullRuleSchema(), null, 2);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('create-page')) {
        // Stepper navigation
        document.getElementById('step-back').onclick = () => showStep(Math.max(0, currentStep - 1));
        document.getElementById('step-next').onclick = () => {
            if (validateStep(currentStep)) {
                showStep(Math.min(totalSteps - 1, currentStep + 1));
            }
        };
        // Show first step
        showStep(0);
    }
});

function validateStep(step) {
    if (step === 0) {
        // Basic Info validation
        if (!document.getElementById('rule-name').value.trim()) {
            showToast('Please enter a rule name.', 'error');
            return false;
        }
        return true;
    }
    if (step === 2) {
        // Action validation
        if (!document.getElementById('rule-action-select').value) {
            showToast('Please select an action.', 'error');
            return false;
        }
    }
    return true;
}

// Prism.js JSON syntax highlighting for JSON editor
function updateJsonHighlight() {
    const textarea = document.getElementById('condition-dsl');
    const code = document.getElementById('json-highlight-code');
    if (textarea && code) {
        let val = textarea.value;
        try {
            val = JSON.stringify(JSON.parse(val), null, 2);
        } catch {}
        code.textContent = val;
        if (window.Prism) Prism.highlightElement(code);
    }
}
if (document.getElementById('condition-dsl')) {
    document.getElementById('condition-dsl').addEventListener('input', updateJsonHighlight);
    updateJsonHighlight();
}