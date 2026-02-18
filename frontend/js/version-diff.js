// frontend/js/version-diff.js
async function loadVersions(ruleId) {
    try {
        const response = await fetchWithAuth(`${API_BASE}/rules/${ruleId}/versions`);
        const versions = await response.json();

        const modal = document.getElementById('versions-modal');
        const versionsList = document.getElementById('versions-list');

        if (!modal || !versionsList) return;

        versionsList.innerHTML = '';

        versions.forEach(version => {
            const versionItem = document.createElement('div');
            versionItem.style.padding = '0.75rem';
            versionItem.style.marginBottom = '0.5rem';
            versionItem.style.background = 'var(--bg)';
            versionItem.style.borderRadius = '0.375rem';
            versionItem.style.cursor = 'pointer';

            versionItem.innerHTML = `
                <strong>Version ${version.version}</strong>
                <div style="font-size: 0.875rem; color: var(--text-light);">
                    ${new Date(version.created_at).toLocaleString()}
                </div>
            `;

            versionItem.addEventListener('click', () => {
                if (version.version > 1) {
                    loadVersionDiff(ruleId, version.version - 1, version.version);
                }
            });

            versionsList.appendChild(versionItem);
        });

        modal.style.display = 'flex';

        modal.querySelector('.modal-close').addEventListener('click', () => {
            modal.style.display = 'none';
        });
    } catch (error) {
        alert(`Error: ${error.message}`);
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

        diffContainer.innerHTML = '<h3>Version Differences</h3>';

        if (Object.keys(diff.differences).length === 0) {
            diffContainer.innerHTML += '<p>No differences found</p>';
            return;
        }

        Object.entries(diff.differences).forEach(([field, values]) => {
            const diffItem = document.createElement('div');
            diffItem.style.marginTop = '1rem';
            diffItem.style.padding = '1rem';
            diffItem.style.background = 'var(--bg)';
            diffItem.style.borderRadius = '0.375rem';

            diffItem.innerHTML = `
                <h4>${field}</h4>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 0.5rem;">
                    <div>
                        <strong>Version ${version1}:</strong>
                        <pre style="margin-top: 0.5rem; padding: 0.5rem; background: white; border-radius: 0.25rem;">${JSON.stringify(values.version1, null, 2)}</pre>
                    </div>
                    <div>
                        <strong>Version ${version2}:</strong>
                        <pre style="margin-top: 0.5rem; padding: 0.5rem; background: white; border-radius: 0.25rem;">${JSON.stringify(values.version2, null, 2)}</pre>
                    </div>
                </div>
            `;

            diffContainer.appendChild(diffItem);
        });
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}