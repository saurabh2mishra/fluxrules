// Parked Conflict Rules Management

async function loadParkedConflicts() {
    const container = document.getElementById('conflicts-list');
    if (!container) return;

    const statusFilter = document.getElementById('conflict-status-filter')?.value || '';

    container.innerHTML = '<div class="loading">Loading parked conflicts...</div>';

    try {
        let url = `${API_BASE}/rules/conflicts/parked`;
        if (statusFilter) url += `?status=${statusFilter}`;

        const response = await fetchWithAuth(url);
        if (!response.ok) {
            container.innerHTML = '<p style="color: var(--danger);">Failed to load parked conflicts.</p>';
            return;
        }

        const conflicts = await response.json();
        renderParkedConflicts(conflicts, container);
    } catch (error) {
        console.error('Error loading parked conflicts:', error);
        container.innerHTML = '<p style="color: var(--danger);">Error: ' + error.message + '</p>';
    }
}

function renderParkedConflicts(conflicts, container) {
    container.innerHTML = '';

    if (!conflicts || conflicts.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div style="font-size:2.5rem;">✅</div>
                <h3>No Parked Conflicts</h3>
                <p>All clear! No rules are waiting for review.</p>
            </div>
        `;
        return;
    }

    // Summary bar
    const pending = conflicts.filter(c => c.status === 'pending').length;
    const approved = conflicts.filter(c => c.status === 'approved').length;
    const dismissed = conflicts.filter(c => c.status === 'dismissed').length;

    const summary = document.createElement('div');
    summary.className = 'conflict-summary';
    summary.innerHTML = `
        <div class="stats-grid" style="margin-bottom: 1rem;">
            <div class="stat-box">
                <span class="stat-number" style="color: #f59e0b;">${pending}</span>
                <span class="stat-label">Pending</span>
            </div>
            <div class="stat-box">
                <span class="stat-number" style="color: #22c55e;">${approved}</span>
                <span class="stat-label">Approved</span>
            </div>
            <div class="stat-box">
                <span class="stat-number" style="color: #6b7280;">${dismissed}</span>
                <span class="stat-label">Dismissed</span>
            </div>
        </div>
    `;
    container.appendChild(summary);

    conflicts.forEach(conflict => {
        const card = createConflictCard(conflict);
        container.appendChild(card);
    });
}

function createConflictCard(conflict) {
    const card = document.createElement('div');
    card.className = 'card conflict-card';
    card.style.borderLeft = conflict.status === 'pending'
        ? '4px solid #f59e0b'
        : conflict.status === 'approved'
            ? '4px solid #22c55e'
            : '4px solid #6b7280';

    const statusColors = {
        pending: '#f59e0b',
        approved: '#22c55e',
        dismissed: '#6b7280'
    };
    const statusLabels = {
        pending: '⏳ Pending Review',
        approved: '✅ Approved',
        dismissed: '🚫 Dismissed'
    };

    const conditionStr = typeof conflict.condition_dsl === 'string'
        ? conflict.condition_dsl
        : JSON.stringify(conflict.condition_dsl, null, 2);

    card.innerHTML = `
        <div class="card-header" style="align-items: flex-start;">
            <div>
                <div class="card-title">${escapeHtml(conflict.name)}</div>
                <div class="card-meta">
                    <span>Group: ${escapeHtml(conflict.group || 'None')}</span>
                    <span>Priority: ${conflict.priority}</span>
                    <span style="color: ${statusColors[conflict.status] || '#6b7280'}; font-weight: 600;">
                        ${statusLabels[conflict.status] || conflict.status}
                    </span>
                </div>
                <p style="color: var(--text-light); margin: 0.5rem 0 0;">${escapeHtml(conflict.description || '')}</p>
            </div>
        </div>
        <div class="conflict-detail-section" style="margin: 0.75rem 0; padding: 0.75rem; background: var(--bg); border-radius: 0.375rem; border: 1px solid var(--border);">
            <div style="margin-bottom: 0.5rem;">
                <strong style="color: var(--danger);">⚠️ Conflict:</strong>
                <span style="color: var(--text);">${escapeHtml(conflict.conflict_description)}</span>
            </div>
            <div style="font-size: 0.85rem; color: var(--text-light);">
                <span>Type: <strong>${escapeHtml(conflict.conflict_type)}</strong></span>
                ${conflict.conflicting_rule_name ? ` · Conflicts with: <strong>${escapeHtml(conflict.conflicting_rule_name)}</strong> (ID: ${conflict.conflicting_rule_id})` : ''}
            </div>
        </div>
        <details style="margin-bottom: 0.75rem;">
            <summary style="cursor: pointer; color: var(--primary); font-size: 0.85rem; font-weight: 500;">View Condition & Action</summary>
            <pre style="font-size: 0.78rem; background: var(--bg); padding: 0.75rem; border-radius: 0.25rem; overflow: auto; max-height: 200px; margin-top: 0.5rem;">${escapeHtml(conditionStr)}</pre>
            <div style="margin-top: 0.5rem; font-size: 0.85rem;">
                <strong>Action:</strong> <code>${escapeHtml(conflict.action || 'None')}</code>
            </div>
        </details>
        <div style="font-size: 0.78rem; color: var(--text-light); margin-bottom: 0.75rem;">
            Submitted: ${conflict.submitted_at ? new Date(conflict.submitted_at).toLocaleString() : 'N/A'}
            ${conflict.reviewed_at ? ` · Reviewed: ${new Date(conflict.reviewed_at).toLocaleString()}` : ''}
            ${conflict.review_notes ? ` · Notes: ${escapeHtml(conflict.review_notes)}` : ''}
        </div>
        <div class="conflict-actions" style="display: flex; gap: 0.5rem;" id="conflict-actions-${conflict.id}">
        </div>
    `;

    // Add action buttons
    const actionsDiv = card.querySelector(`#conflict-actions-${conflict.id}`);

    if (conflict.status === 'pending') {
        const resolveBtn = document.createElement('button');
        resolveBtn.className = 'btn btn-sm btn-primary';
        resolveBtn.textContent = '✏️ Edit & Resolve';
        resolveBtn.onclick = () => openResolveEditor(conflict, card);

        const dismissBtn = document.createElement('button');
        dismissBtn.className = 'btn btn-sm btn-secondary';
        dismissBtn.textContent = '🚫 Dismiss';
        dismissBtn.onclick = () => dismissParkedConflict(conflict.id);

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'btn btn-sm btn-danger';
        deleteBtn.textContent = '🗑 Delete';
        deleteBtn.onclick = () => deleteParkedConflict(conflict.id);

        actionsDiv.appendChild(resolveBtn);
        actionsDiv.appendChild(dismissBtn);
        actionsDiv.appendChild(deleteBtn);
    } else {
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'btn btn-sm btn-danger';
        deleteBtn.textContent = '🗑 Delete';
        deleteBtn.onclick = () => deleteParkedConflict(conflict.id);
        actionsDiv.appendChild(deleteBtn);
    }

    if (conflict.conflicting_rule_id) {
        const compareBtn = document.createElement('button');
        compareBtn.className = 'btn btn-sm btn-info';
        compareBtn.textContent = '🔍 Compare';
        compareBtn.onclick = () => showRuleComparison(conflict, conflict.conflicting_rule_id);
        actionsDiv.appendChild(compareBtn);
    }

    return card;
}

function openResolveEditor(conflict, card) {
    // Remove any existing editor in this card
    const existing = card.querySelector('.resolve-editor');
    if (existing) { existing.remove(); return; }

    const conditionObj = typeof conflict.condition_dsl === 'string'
        ? JSON.parse(conflict.condition_dsl)
        : conflict.condition_dsl;

    const editor = document.createElement('div');
    editor.className = 'resolve-editor';
    editor.style.cssText = 'margin-top: 1rem; padding: 1rem; background: var(--bg); border: 1px solid var(--border); border-radius: 0.5rem;';
    editor.innerHTML = `
        <h4 style="margin: 0 0 0.75rem; color: var(--text);">✏️ Edit Rule to Resolve Conflict</h4>
        <p style="font-size: 0.82rem; color: var(--text-light); margin-bottom: 0.75rem;">
            Modify the <strong>priority</strong>, <strong>group</strong>, <strong>condition</strong>, or <strong>action</strong> to resolve the conflict. Unchanged rules cannot be created.
        </p>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 0.75rem;">
            <div>
                <label style="font-size: 0.8rem; font-weight: 600; color: var(--text);">Name</label>
                <input type="text" id="resolve-name-${conflict.id}" value="${escapeHtml(conflict.name)}" style="width:100%; padding: 0.4rem 0.5rem; border: 1px solid var(--border); border-radius: 0.25rem; background: var(--card); color: var(--text);">
            </div>
            <div>
                <label style="font-size: 0.8rem; font-weight: 600; color: var(--text);">Group</label>
                <input type="text" id="resolve-group-${conflict.id}" value="${escapeHtml(conflict.group || '')}" style="width:100%; padding: 0.4rem 0.5rem; border: 1px solid var(--border); border-radius: 0.25rem; background: var(--card); color: var(--text);">
            </div>
            <div>
                <label style="font-size: 0.8rem; font-weight: 600; color: var(--danger);">Priority ⚡</label>
                <input type="number" id="resolve-priority-${conflict.id}" value="${conflict.priority}" style="width:100%; padding: 0.4rem 0.5rem; border: 1px solid var(--border); border-radius: 0.25rem; background: var(--card); color: var(--text);">
            </div>
            <div>
                <label style="font-size: 0.8rem; font-weight: 600; color: var(--text);">Action</label>
                <input type="text" id="resolve-action-${conflict.id}" value="${escapeHtml(conflict.action || '')}" style="width:100%; padding: 0.4rem 0.5rem; border: 1px solid var(--border); border-radius: 0.25rem; background: var(--card); color: var(--text);">
            </div>
        </div>
        <div style="margin-bottom: 0.75rem;">
            <label style="font-size: 0.8rem; font-weight: 600; color: var(--text);">Description</label>
            <input type="text" id="resolve-desc-${conflict.id}" value="${escapeHtml(conflict.description || '')}" style="width:100%; padding: 0.4rem 0.5rem; border: 1px solid var(--border); border-radius: 0.25rem; background: var(--card); color: var(--text);">
        </div>
        <div style="margin-bottom: 0.75rem;">
            <label style="font-size: 0.8rem; font-weight: 600; color: var(--text);">Condition DSL (JSON)</label>
            <textarea id="resolve-condition-${conflict.id}" rows="6" style="width:100%; padding: 0.5rem; border: 1px solid var(--border); border-radius: 0.25rem; font-family: monospace; font-size: 0.8rem; background: var(--card); color: var(--text);">${escapeHtml(JSON.stringify(conditionObj, null, 2))}</textarea>
        </div>
        <div style="display: flex; gap: 0.5rem;">
            <button class="btn btn-sm btn-primary" id="resolve-submit-${conflict.id}">💾 Submit Resolved Rule</button>
            <button class="btn btn-sm" id="resolve-cancel-${conflict.id}">Cancel</button>
        </div>
        <div id="resolve-error-${conflict.id}" style="margin-top: 0.5rem; display: none;"></div>
    `;

    card.appendChild(editor);

    document.getElementById(`resolve-cancel-${conflict.id}`).onclick = () => editor.remove();
    document.getElementById(`resolve-submit-${conflict.id}`).onclick = () => submitResolvedRule(conflict.id);
}

async function submitResolvedRule(id) {
    const name = document.getElementById(`resolve-name-${id}`)?.value?.trim();
    const group = document.getElementById(`resolve-group-${id}`)?.value?.trim();
    const priority = parseInt(document.getElementById(`resolve-priority-${id}`)?.value, 10);
    const action = document.getElementById(`resolve-action-${id}`)?.value?.trim();
    const description = document.getElementById(`resolve-desc-${id}`)?.value?.trim();
    const conditionRaw = document.getElementById(`resolve-condition-${id}`)?.value?.trim();
    const errorDiv = document.getElementById(`resolve-error-${id}`);

    // Validate JSON
    let conditionDsl;
    try {
        conditionDsl = JSON.parse(conditionRaw);
    } catch (e) {
        if (errorDiv) {
            errorDiv.style.display = 'block';
            errorDiv.innerHTML = '<p style="color: var(--danger); font-size: 0.85rem;">❌ Invalid JSON in Condition DSL. Please fix and try again.</p>';
        }
        return;
    }

    const modifiedRule = {
        name: name,
        description: description,
        group: group || null,
        priority: isNaN(priority) ? 0 : priority,
        enabled: true,
        condition_dsl: conditionDsl,
        action: action
    };

    try {
        const response = await fetchWithAuth(`${API_BASE}/rules/conflicts/parked/${id}/resolve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(modifiedRule)
        });

        if (response.ok) {
            const result = await response.json();
            showToast(result.message, 'success');
            loadParkedConflicts();
        } else {
            const error = await response.json();
            const detail = error.detail;
            let msg = '';
            if (typeof detail === 'string') {
                msg = detail;
            } else if (detail?.message) {
                msg = detail.message;
                if (detail.conflicts) {
                    msg += '<ul style="margin: 0.5rem 0 0; padding-left: 1.25rem;">';
                    detail.conflicts.forEach(c => {
                        msg += `<li>${escapeHtml(c.description || c.type)}</li>`;
                    });
                    msg += '</ul>';
                }
            } else {
                msg = JSON.stringify(detail);
            }
            if (errorDiv) {
                errorDiv.style.display = 'block';
                errorDiv.innerHTML = `<div style="color: var(--danger); font-size: 0.85rem; background: rgba(239,68,68,0.08); padding: 0.5rem 0.75rem; border-radius: 0.25rem;">❌ ${msg}</div>`;
            }
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

async function dismissParkedConflict(id) {
    const notes = prompt('Optional: Add a note for why this rule is being dismissed:');

    try {
        let url = `${API_BASE}/rules/conflicts/parked/${id}?action=dismiss`;
        if (notes) url += `&notes=${encodeURIComponent(notes)}`;

        const response = await fetchWithAuth(url, { method: 'PUT' });

        if (response.ok) {
            const result = await response.json();
            showToast(result.message, 'success');
            loadParkedConflicts();
        } else {
            const error = await response.json();
            showToast('Error: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

async function deleteParkedConflict(id) {
    if (!window.confirm('Are you sure you want to permanently delete this parked rule?')) return;

    try {
        const response = await fetchWithAuth(`${API_BASE}/rules/conflicts/parked/${id}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            showToast('Parked rule deleted.', 'success');
            loadParkedConflicts();
        } else {
            const error = await response.json();
            showToast('Error: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        showToast('Error: ' + error.message, 'error');
    }
}

// Side-by-side rule comparison with diff highlighting
window.showRuleComparison = async function(ruleADataOrObj, ruleBId) {
    let ruleA;
    if (typeof ruleADataOrObj === 'object') {
        ruleA = ruleADataOrObj;
    } else {
        ruleA = await fetchWithAuth(`${API_BASE}/rules/${ruleADataOrObj}`).then(r => r.json());
    }
    const ruleB = await fetchWithAuth(`${API_BASE}/rules/${ruleBId}`).then(r => r.json());
    const modal = document.getElementById('rule-compare-modal');
    const containerA = document.getElementById('ruleA-details');
    const containerB = document.getElementById('ruleB-details');
    // Prefer enhanced JSON diff if available
    if (window.renderJsonDiff) {
        renderJsonDiff(ruleA, ruleB, containerA, containerB);
    } else if (window.renderFieldDiff) {
        renderFieldDiff(ruleA, ruleB, containerA, containerB);
    } else if (window.renderDiff) {
        const aStr = JSON.stringify(ruleA, null, 2);
        const bStr = JSON.stringify(ruleB, null, 2);
        renderDiff(aStr, bStr, containerA, containerB);
    } else {
        containerA.textContent = JSON.stringify(ruleA, null, 2);
        containerB.textContent = JSON.stringify(ruleB, null, 2);
    }
    modal.style.display = 'flex';
}
