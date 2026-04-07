function escapeHtml(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

let allRules = []; // Store all rules for filtering
let loadedRules = [];
let skip = 0;
const limit = 50;
let allLoaded = false;

async function loadRules(initial = false) {
    if (initial) {
        skip = 0;
        loadedRules = [];
        allLoaded = false;
    }
    try {
        const response = await fetchWithAuth(`${API_BASE}/rules?skip=${skip}&limit=${limit}`);
        
        if (!response.ok) {
            console.error('Failed to load rules:', response.status);
            const container = document.getElementById('rules-list');
            if (container) {
                container.innerHTML = '<p style="color: red;">Failed to load rules. Please try again.</p>';
            }
            return;
        }
        
        const rules = await response.json();
        if (rules.length < limit) allLoaded = true;
        loadedRules = loadedRules.concat(rules);
        allRules = loadedRules;

        // Populate group filter dropdown from API
        await populateGroupFilterFromAPI();

        // Setup filter event listeners (only once)
        setupFilterListeners();

        // Render rules
        renderFilteredRules();
        renderLoadMoreButton();
    } catch (error) {
        console.error('Error loading rules:', error);
        const container = document.getElementById('rules-list');
        if (container) {
            container.innerHTML = '<p style="color: red;">Error loading rules: ' + error.message + '</p>';
        }
    }
}

async function populateGroupFilterFromAPI() {
    const groupSelect = document.getElementById('filter-group');
    if (!groupSelect) return;
    try {
        const response = await fetchWithAuth(`${API_BASE}/rules/groups`);
        if (!response.ok) throw new Error('Failed to fetch groups');
        const data = await response.json();
        const groups = data.groups || [];
        groupSelect.innerHTML = '<option value="">All Groups</option>' +
            groups.map(g => `<option value="${escapeHtml(g)}">${escapeHtml(g)}</option>`).join('');
    } catch (e) {
        groupSelect.innerHTML = '<option value="">All Groups</option>';
    }
}

let filtersInitialized = false;
function setupFilterListeners() {
    if (filtersInitialized) return;
    filtersInitialized = true;

    const searchInput = document.getElementById('search-rules');
    const groupSelect = document.getElementById('filter-group');
    const statusSelect = document.getElementById('filter-enabled');

    if (searchInput) {
        searchInput.addEventListener('input', renderFilteredRules);
    }
    if (groupSelect) {
        groupSelect.addEventListener('change', renderFilteredRules);
    }
    if (statusSelect) {
        statusSelect.addEventListener('change', renderFilteredRules);
    }
}

function renderLoadMoreButton() {
    const container = document.getElementById('rules-list');
    let btn = document.getElementById('load-more-rules-btn');
    if (!container) return;
    if (!allLoaded) {
        if (!btn) {
            btn = document.createElement('button');
            btn.id = 'load-more-rules-btn';
            btn.className = 'btn btn-secondary';
            btn.textContent = 'Load More Rules';
            btn.onclick = () => {
                skip += limit;
                loadRules();
            };
            container.parentNode.appendChild(btn);
        }
        btn.style.display = 'block';
    } else if (btn) {
        btn.style.display = 'none';
    }
}

function renderFilteredRules() {
    const container = document.getElementById('rules-list');
    if (!container) return;

    const searchValue = (document.getElementById('search-rules')?.value || '').toLowerCase();
    const groupValue = document.getElementById('filter-group')?.value || '';
    const statusValue = document.getElementById('filter-enabled')?.value || '';

    let filtered = allRules;

    // Filter by search (name or description)
    if (searchValue) {
        filtered = filtered.filter(rule =>
            (rule.name && rule.name.toLowerCase().includes(searchValue)) ||
            (rule.description && rule.description.toLowerCase().includes(searchValue))
        );
    }

    // Filter by group
    if (groupValue) {
        filtered = filtered.filter(rule => rule.group === groupValue);
    }

    // Filter by enabled status
    if (statusValue !== '') {
        const enabledBool = statusValue === 'true';
        filtered = filtered.filter(rule => rule.enabled === enabledBool);
    }

    container.innerHTML = '';

    if (!filtered || filtered.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div style="font-size:2.5rem;">🔍</div>
                <h3>No Rules Found</h3>
                <p>No rules match your search or filter criteria.</p>
            </div>
        `;
        return;
    }

    filtered.forEach(rule => {
        const card = createRuleCard(rule);
        container.appendChild(card);
    });

    // After rendering cards, call renderLoadMoreButton()
    renderLoadMoreButton();
}

function createRuleCard(rule) {
    const card = document.createElement('div');
    card.className = 'card rule-card';

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

    // Expand/collapse button
    const expandBtn = document.createElement('button');
    expandBtn.className = 'btn btn-sm btn-secondary expand-btn';
    expandBtn.innerHTML = '<span class="expand-icon">▼</span> Details';
    expandBtn.setAttribute('aria-expanded', 'false');
    actions.appendChild(statusBadge);
    actions.appendChild(editBtn);
    actions.appendChild(deleteBtn);
    actions.appendChild(expandBtn);

    // Copy button
    const copyBtn = document.createElement('button');
    copyBtn.className = 'btn btn-sm btn-secondary';
    copyBtn.textContent = 'Copy';
    copyBtn.addEventListener('click', () => {
        const jsonString = JSON.stringify(rule, null, 2);
        navigator.clipboard.writeText(jsonString).then(() => {
            showToast('Rule copied to clipboard!', 'success');
        }, () => {
            showToast('Failed to copy rule.', 'error');
        });
    });
    actions.appendChild(copyBtn);

    header.appendChild(titleSection);
    header.appendChild(actions);

    const description = document.createElement('p');
    description.textContent = rule.description || 'No description';
    description.style.color = 'var(--text-light)';
    description.style.marginBottom = '1rem';

    // Collapsible details section
    const details = document.createElement('div');
    details.className = 'rule-details-collapsible';
    details.style.display = 'none';
    const jsonString = JSON.stringify(rule, null, 2);
    details.innerHTML = `
        <div class="rule-details-block">
            <strong class="details-label">Full JSON:</strong>
            <pre class="details-pre">${escapeHtml(jsonString)}</pre>
        </div>
        <div class="rule-details-block">
            <strong class="details-label">Action:</strong>
            <pre class="details-pre">${escapeHtml(rule.action || 'None')}</pre>
        </div>
    `;

    expandBtn.onclick = function() {
        const expanded = details.style.display === 'block';
        details.style.display = expanded ? 'none' : 'block';
        expandBtn.setAttribute('aria-expanded', String(!expanded));
        expandBtn.querySelector('.expand-icon').textContent = expanded ? '▼' : '▲';
    };

    // Condition preview (always visible)
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
    card.appendChild(details);

    return card;
}

async function deleteRule(ruleId) {
    if (!window.confirm('Are you sure you want to delete this rule?')) {
        showToast('Delete cancelled.', 'info');
        return;
    }

    try {
        const response = await fetchWithAuth(`${API_BASE}/rules/${ruleId}`, {
            method: 'DELETE'
        });
        if (response.ok) {
            showToast('Rule deleted successfully.', 'success');
            await loadRules(true);
        } else {
            showToast('Failed to delete rule.', 'error');
        }
    } catch (error) {
        showToast('Error deleting rule: ' + error.message, 'error');
    }
}