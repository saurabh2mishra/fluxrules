async function loadVersions(ruleId) {
    try {
        const response = await fetchWithAuth(`${API_BASE}/rules/${ruleId}/versions`);
        const versions = await response.json();

        const modal = document.getElementById('versions-modal');
        const versionsList = document.getElementById('versions-list');
        const diffContainer = document.getElementById('version-diff');

        if (!modal || !versionsList) {
            console.error('versions-modal or versions-list element not found in DOM');
            alert('Error: Version modal not found. Please refresh the page.');
            return;
        }

        versionsList.innerHTML = '';
        if (diffContainer) diffContainer.innerHTML = '';

        if (!versions || versions.length === 0) {
            versionsList.innerHTML = '<p style="color: var(--text-secondary); padding: 1rem;">No versions found for this rule.</p>';
        } else {
            versions.forEach(version => {
                const versionItem = document.createElement('div');
                versionItem.style.padding = '0.75rem';
                versionItem.style.marginBottom = '0.5rem';
                versionItem.style.background = 'var(--bg)';
                versionItem.style.borderRadius = '0.375rem';
                versionItem.style.cursor = 'pointer';
                versionItem.style.border = '1px solid var(--border, #e5e7eb)';
                versionItem.style.transition = 'background 0.15s';

                versionItem.innerHTML = `
                    <strong>Version ${version.version}</strong>
                    <div style="font-size: 0.875rem; color: var(--text-light);">
                        ${new Date(version.created_at).toLocaleString()}
                    </div>
                `;

                versionItem.addEventListener('mouseenter', () => {
                    versionItem.style.background = 'var(--bg-hover, #f3f4f6)';
                });
                versionItem.addEventListener('mouseleave', () => {
                    versionItem.style.background = 'var(--bg)';
                });

                versionItem.addEventListener('click', () => {
                    if (version.version > 1) {
                        loadVersionDiff(ruleId, version.version - 1, version.version);
                    }
                });

                versionsList.appendChild(versionItem);
            });
        }

        modal.style.display = 'flex';

        // Use onclick instead of addEventListener to avoid stacking listeners
        const closeBtn = modal.querySelector('.modal-close');
        if (closeBtn) {
            closeBtn.onclick = () => {
                modal.style.display = 'none';
                // Reset maximized state on close
                const inner = document.getElementById('versions-modal-inner');
                if (inner) inner.classList.remove('maximized');
            };
        }

        // Maximize/minimize toggle
        const maxBtn = document.getElementById('versions-modal-maximize');
        const inner = document.getElementById('versions-modal-inner');
        if (maxBtn && inner) {
            maxBtn.onclick = (e) => {
                e.stopPropagation();
                const isMax = inner.classList.toggle('maximized');
                maxBtn.textContent = isMax ? '⛶' : '⛶';
                maxBtn.title = isMax ? 'Restore' : 'Maximize';
                // Use different icons for state
                maxBtn.innerHTML = isMax ? '⧉' : '⛶';
            };
        }

        // Also close on backdrop click
        modal.onclick = (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
                if (inner) inner.classList.remove('maximized');
            }
        };
    } catch (error) {
        console.error('loadVersions error:', error);
        alert(`Error loading versions: ${error.message}`);
    }
}

async function loadVersionDiff(ruleId, version1, version2) {
    try {
        const response = await fetchWithAuth(
            `${API_BASE}/rules/${ruleId}/diff/${version1}/${version2}`
        );
        const diff = await response.json();

        const diffContainer = document.getElementById('version-diff');
        if (!diffContainer) return;

        diffContainer.innerHTML = '<h3 style="margin-bottom: 0.75rem;">Version Differences</h3>';

        if (Object.keys(diff.differences).length === 0) {
            diffContainer.innerHTML += '<p>No differences found</p>';
            return;
        }

        Object.entries(diff.differences).forEach(([field, values]) => {
            // Parse JSON strings into objects for proper display
            let val1 = parseJsonValue(values.version1);
            let val2 = parseJsonValue(values.version2);

            const diffItem = document.createElement('div');
            diffItem.style.marginTop = '1rem';
            diffItem.style.padding = '1rem';
            diffItem.style.background = 'var(--bg)';
            diffItem.style.borderRadius = '0.375rem';
            diffItem.style.border = '1px solid var(--border, #e5e7eb)';

            const heading = document.createElement('h4');
            heading.textContent = field;
            heading.style.marginBottom = '0.5rem';
            diffItem.appendChild(heading);

            // If both values are objects, use the enhanced JSON diff from fielddiff.js
            if (typeof val1 === 'object' && val1 !== null && typeof val2 === 'object' && val2 !== null && window.renderJsonDiff) {
                const grid = document.createElement('div');
                grid.style.display = 'grid';
                grid.style.gridTemplateColumns = '1fr 1fr';
                grid.style.gap = '1rem';
                grid.style.marginTop = '0.5rem';

                const colA = document.createElement('div');
                const labelA = document.createElement('strong');
                labelA.textContent = `Version ${version1}:`;
                const containerA = document.createElement('div');
                containerA.className = 'version-diff-container';
                colA.appendChild(labelA);
                colA.appendChild(containerA);

                const colB = document.createElement('div');
                const labelB = document.createElement('strong');
                labelB.textContent = `Version ${version2}:`;
                const containerB = document.createElement('div');
                containerB.className = 'version-diff-container';
                colB.appendChild(labelB);
                colB.appendChild(containerB);

                grid.appendChild(colA);
                grid.appendChild(colB);
                diffItem.appendChild(grid);

                renderJsonDiff(val1, val2, containerA, containerB);
            } else {
                // Simple values — render side by side with formatted display
                const grid = document.createElement('div');
                grid.style.display = 'grid';
                grid.style.gridTemplateColumns = '1fr 1fr';
                grid.style.gap = '1rem';
                grid.style.marginTop = '0.5rem';

                const colA = document.createElement('div');
                const labelA = document.createElement('strong');
                labelA.textContent = `Version ${version1}:`;
                const valA = document.createElement('div');
                valA.className = 'version-diff-value version-diff-old';
                valA.innerHTML = formatDiffValue(val1);
                colA.appendChild(labelA);
                colA.appendChild(valA);

                const colB = document.createElement('div');
                const labelB = document.createElement('strong');
                labelB.textContent = `Version ${version2}:`;
                const valB = document.createElement('div');
                valB.className = 'version-diff-value version-diff-new';
                valB.innerHTML = formatDiffValue(val2);
                colB.appendChild(labelB);
                colB.appendChild(valB);

                grid.appendChild(colA);
                grid.appendChild(colB);
                diffItem.appendChild(grid);
            }

            diffContainer.appendChild(diffItem);
        });
    } catch (error) {
        console.error('loadVersionDiff error:', error);
        alert(`Error loading version diff: ${error.message}`);
    }
}

// Parse a value that might be a JSON string into an object
function parseJsonValue(val) {
    if (typeof val === 'string') {
        try {
            return JSON.parse(val);
        } catch {
            return val;
        }
    }
    return val;
}

// Format a value for display in a <pre> tag (HTML-escaped)
function formatDiffValue(val) {
    if (val === null || val === undefined) return '<em>null</em>';
    if (typeof val === 'object') {
        return escapeHtmlForDiff(JSON.stringify(val, null, 2));
    }
    return escapeHtmlForDiff(String(val));
}

// Minimal HTML escaping for diff display
function escapeHtmlForDiff(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}