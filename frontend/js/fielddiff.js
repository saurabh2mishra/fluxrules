function diffRuleFields(ruleA, ruleB) {
    const allKeys = new Set([...Object.keys(ruleA), ...Object.keys(ruleB)]);
    const diffs = [];
    for (const key of allKeys) {
        const valueA = ruleA[key];
        const valueB = ruleB[key];
        const changed = JSON.stringify(valueA) !== JSON.stringify(valueB);
        diffs.push({ field: key, valueA, valueB, changed });
    }
    return diffs;
}

function renderFieldDiff(ruleA, ruleB, containerA, containerB) {
    const diffs = diffRuleFields(ruleA, ruleB);
    containerA.innerHTML = '';
    containerB.innerHTML = '';
    diffs.forEach(({ field, valueA, valueB, changed }) => {
        const rowA = document.createElement('div');
        const rowB = document.createElement('div');
        rowA.className = rowB.className = 'diff-row';
        if (changed) {
            rowA.classList.add('diff-changed-old');
            rowB.classList.add('diff-changed-new');
            rowA.style.fontWeight = rowB.style.fontWeight = '600';
        }
        const fmtVal = (v) => {
            if (v === undefined || v === null) return '<span class="diff-null">' + String(v) + '</span>';
            if (typeof v === 'object') return '<span class="diff-obj">' + escapeHtmlInDiff(JSON.stringify(v, null, 2)) + '</span>';
            return escapeHtmlInDiff(String(v));
        };
        rowA.innerHTML = `<span class="diff-key">${escapeHtmlInDiff(field)}:</span> ${fmtVal(valueA)}`;
        rowB.innerHTML = `<span class="diff-key">${escapeHtmlInDiff(field)}:</span> ${fmtVal(valueB)}`;
        containerA.appendChild(rowA);
        containerB.appendChild(rowB);
    });
}

// Enhanced recursive JSON diff for rule objects with collapsible UI
function diffJson(a, b, path = []) {
    if (typeof a !== typeof b) {
        return [{ path, valueA: a, valueB: b, type: 'changed' }];
    }
    if (typeof a !== 'object' || a === null || b === null) {
        if (a === b) return [{ path, valueA: a, valueB: b, type: 'unchanged' }];
        return [{ path, valueA: a, valueB: b, type: 'changed' }];
    }
    // Both are objects/arrays
    const keys = new Set([...Object.keys(a || {}), ...Object.keys(b || {})]);
    let diffs = [];
    for (const key of keys) {
        if (!(key in a)) {
            diffs.push({ path: [...path, key], valueA: undefined, valueB: b[key], type: 'added' });
        } else if (!(key in b)) {
            diffs.push({ path: [...path, key], valueA: a[key], valueB: undefined, type: 'removed' });
        } else {
            diffs = diffs.concat(diffJson(a[key], b[key], [...path, key]));
        }
    }
    return diffs;
}

function renderJsonDiff(a, b, containerA, containerB) {
    const diffs = diffJson(a, b);
    containerA.innerHTML = '';
    containerB.innerHTML = '';
    // Group diffs by top-level field for collapsible UI
    const groupByTop = {};
    diffs.forEach(d => {
        const top = d.path[0] || '(root)';
        if (!groupByTop[top]) groupByTop[top] = [];
        groupByTop[top].push(d);
    });
    Object.entries(groupByTop).forEach(([top, group]) => {
        const detailsA = document.createElement('details');
        const detailsB = document.createElement('details');
        detailsA.open = detailsB.open = true;
        detailsA.className = detailsB.className = 'diff-details';
        const summaryA = document.createElement('summary');
        const summaryB = document.createElement('summary');
        summaryA.className = summaryB.className = 'diff-summary';
        summaryA.textContent = top;
        summaryB.textContent = top;
        detailsA.appendChild(summaryA);
        detailsB.appendChild(summaryB);
        group.forEach(({ path, valueA, valueB, type }) => {
            const key = path.slice(1).join('.') || top;
            const rowA = document.createElement('div');
            const rowB = document.createElement('div');
            rowA.className = rowB.className = 'diff-row';
            if (type === 'changed') {
                rowA.classList.add('diff-changed-old');
                rowB.classList.add('diff-changed-new');
            } else if (type === 'added') {
                rowA.classList.add('diff-absent');
                rowB.classList.add('diff-added');
            } else if (type === 'removed') {
                rowA.classList.add('diff-removed');
                rowB.classList.add('diff-absent');
            }
            const formatVal = (v) => {
                if (v === undefined) return '<span class="diff-null">undefined</span>';
                if (v === null) return '<span class="diff-null">null</span>';
                if (typeof v === 'object') return '<span class="diff-obj">' + escapeHtmlInDiff(JSON.stringify(v, null, 2)) + '</span>';
                return escapeHtmlInDiff(String(v));
            };
            rowA.innerHTML = `<span class="diff-key">${escapeHtmlInDiff(key)}:</span> ${formatVal(valueA)}`;
            rowB.innerHTML = `<span class="diff-key">${escapeHtmlInDiff(key)}:</span> ${formatVal(valueB)}`;
            detailsA.appendChild(rowA);
            detailsB.appendChild(rowB);
        });
        containerA.appendChild(detailsA);
        containerB.appendChild(detailsB);
    });
}

// Export for global use in compare modal
window.renderJsonDiff = renderJsonDiff;

// HTML escape for safe innerHTML rendering
function escapeHtmlInDiff(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
