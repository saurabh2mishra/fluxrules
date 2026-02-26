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
        rowA.style.padding = rowB.style.padding = '2px 0';
        rowA.style.fontWeight = rowB.style.fontWeight = '400';
        if (changed) {
            rowA.style.background = '#fee2e2'; // red-100
            rowB.style.background = '#dbeafe'; // blue-100
            rowA.style.fontWeight = rowB.style.fontWeight = '600';
        }
        rowA.innerHTML = `<span style='color:#888;'>${field}:</span> ` +
            (typeof valueA === 'object' ? `<pre style='display:inline;'>${JSON.stringify(valueA, null, 2)}</pre>` : String(valueA));
        rowB.innerHTML = `<span style='color:#888;'>${field}:</span> ` +
            (typeof valueB === 'object' ? `<pre style='display:inline;'>${JSON.stringify(valueB, null, 2)}</pre>` : String(valueB));
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
        const summaryA = document.createElement('summary');
        const summaryB = document.createElement('summary');
        summaryA.textContent = top;
        summaryB.textContent = top;
        detailsA.appendChild(summaryA);
        detailsB.appendChild(summaryB);
        group.forEach(({ path, valueA, valueB, type }) => {
            const key = path.slice(1).join('.') || top;
            const rowA = document.createElement('div');
            const rowB = document.createElement('div');
            rowA.style.padding = rowB.style.padding = '2px 0 2px 1em';
            if (type === 'changed') {
                rowA.style.background = '#fee2e2';
                rowB.style.background = '#dbeafe';
            } else if (type === 'added') {
                rowA.style.background = '#f1f5f9';
                rowB.style.background = '#bbf7d0';
            } else if (type === 'removed') {
                rowA.style.background = '#fca5a5';
                rowB.style.background = '#f1f5f9';
            }
            rowA.innerHTML = `<span style='color:#888;'>${key}:</span> ` +
                (typeof valueA === 'object' && valueA !== null ? `<pre style='display:inline;'>${JSON.stringify(valueA, null, 2)}</pre>` : String(valueA));
            rowB.innerHTML = `<span style='color:#888;'>${key}:</span> ` +
                (typeof valueB === 'object' && valueB !== null ? `<pre style='display:inline;'>${JSON.stringify(valueB, null, 2)}</pre>` : String(valueB));
            detailsA.appendChild(rowA);
            detailsB.appendChild(rowB);
        });
        containerA.appendChild(detailsA);
        containerB.appendChild(detailsB);
    });
}

// Export for global use in compare modal
window.renderJsonDiff = renderJsonDiff;
