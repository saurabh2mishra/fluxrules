// async function editRule(ruleId) {
//     try {
//         const response = await fetchWithAuth(`${API_BASE}/rules/${ruleId}`);
//         const rule = await response.json();

//         document.getElementById('edit-rule-id').value = rule.id;
//         document.getElementById('edit-rule-name').value = rule.name;
//         document.getElementById('edit-rule-description').value = rule.description || '';
//         document.getElementById('edit-rule-group').value = rule.group || '';
//         document.getElementById('edit-rule-priority').value = rule.priority;
//         document.getElementById('edit-rule-enabled').checked = rule.enabled;
//         document.getElementById('edit-rule-action').value = rule.action;

//         // FIX: condition_dsl is already an object, assign directly
//         conditionTree = rule.condition_dsl;
        
//         // Render visual builder
//         const container = document.getElementById('edit-condition-builder');
//         if (container) {
//             container.innerHTML = '';
//             container.appendChild(buildGroupNode(conditionTree, []));
//         }
        
//         // Set JSON textarea
//         const textarea = document.getElementById('edit-condition-dsl');
//         if (textarea) {
//             textarea.value = JSON.stringify(conditionTree, null, 2);
//         }

//         showPage('edit');
//         setupEditForm();
//     } catch (error) {
//         console.error('Edit error:', error);
//         alert(`Error loading rule: ${error.message}`);
//     }
// }

// function setupEditForm() {
//     // Setup tabs for edit page
//     document.querySelectorAll('.tab-btn[data-tab^="edit-"]').forEach(btn => {
//         btn.onclick = function() {
//             this.parentElement.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
//             this.classList.add('active');
            
//             document.getElementById('edit-visual-tab').classList.toggle('active', this.dataset.tab === 'edit-visual');
//             document.getElementById('edit-json-tab').classList.toggle('active', this.dataset.tab === 'edit-json');
//         };
//     });
    
//     // Setup JSON editor
//     setupJSONEditor('edit-condition-dsl', 'edit-json-status');
    
//     // Form submit
//     const form = document.getElementById('edit-form');
//     if (form) {
//         form.onsubmit = handleEditSubmit;
//     }
    
//     document.getElementById('cancel-edit').onclick = () => showPage('rules');
//     document.getElementById('view-versions').onclick = async () => {
//         const ruleId = document.getElementById('edit-rule-id').value;
//         await loadVersions(ruleId);
//     };
// }

// async function handleEditSubmit(e) {
//     e.preventDefault();

//     const ruleId = document.getElementById('edit-rule-id').value;
//     const name = document.getElementById('edit-rule-name').value;
//     const description = document.getElementById('edit-rule-description').value;
//     const group = document.getElementById('edit-rule-group').value;
//     const priority = parseInt(document.getElementById('edit-rule-priority').value);
//     const enabled = document.getElementById('edit-rule-enabled').checked;
//     const action = document.getElementById('edit-rule-action').value;

//     let dslObj;

//     try {
//         const textarea = document.getElementById('edit-condition-dsl');

//         let raw = textarea.value;

//         // defensive fix
//         if (raw === '[object Object]') {
//             raw = JSON.stringify(conditionTree);
//         }

//         if (typeof raw !== 'string') {
//             raw = JSON.stringify(raw);
//         }

//         dslObj = JSON.parse(raw);

//     } catch (e) {
//         alert('Invalid condition DSL JSON: ' + e.message);
//         return;
//     }



//     // Merge form fields into DSL JSON
//     dslObj.name = name;
//     dslObj.description = description;
//     dslObj.group = group;
//     dslObj.action = action;

//     const ruleData = {
//         ...dslObj,
//         priority,
//         enabled
//     };

//     try {
//         const response = await fetchWithAuth(`${API_BASE}/rules/${ruleId}`, {
//             method: 'PUT',
//             body: JSON.stringify(ruleData)
//         });

//         if (response.ok) {
//             alert('Rule updated successfully!');
//             showPage('rules');
//             loadRules();
//         } else {
//             let errorMsg = 'Error updating rule';
//             try {
//                 const error = await response.json();
//                 if (error.detail && error.detail.conflicts) {
//                     let msg = error.detail.message + '\n\nConflicts:\n';
//                     error.detail.conflicts.forEach(c => msg += `- ${c.description}\n`);
//                     errorMsg = msg;
//                 } else if (error.detail) {
//                     if (typeof error.detail === 'string') {
//                         errorMsg = `Error: ${error.detail}`;
//                     } else {
//                         errorMsg = `Error: ${JSON.stringify(error.detail, null, 2)}`;
//                     }
//                 } else {
//                     errorMsg = 'Error: ' + JSON.stringify(error);
//                 }
//             } catch (parseErr) {
//                 // If response is not JSON
//                 errorMsg = 'Error: ' + (await response.text());
//             }
//             alert(errorMsg);
//         }
//     } catch (error) {
//         alert('Error: ' + error.message);
//     }
// }

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

// Global editRule function (async)
window.editRule = async function(ruleId) {
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

        // Assign condition DSL
        conditionTree = rule.condition_dsl;

        // Render visual builder
        const container = document.getElementById('edit-condition-builder');
        if (container) {
            container.innerHTML = '';
            container.appendChild(buildGroupNode(conditionTree, []));
        }

        // Set JSON textarea
        const textarea = document.getElementById('edit-condition-dsl');
        if (textarea) {
            textarea.value = JSON.stringify(conditionTree, null, 2);
        }

        showPage('edit');
        window.setupEditForm();
    } catch (error) {
        console.error('Edit error:', error);
        alert(`Error loading rule: ${error.message}`);
    }
};

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

    const ruleData = { ...dslObj, priority, enabled };

    try {
        const response = await fetchWithAuth(`${API_BASE}/rules/${ruleId}`, {
            method: 'PUT',
            body: JSON.stringify(ruleData)
        });

        if (response.ok) {
            alert('Rule updated successfully!');
            showPage('rules');
            loadRules();
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
