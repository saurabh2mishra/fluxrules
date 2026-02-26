// Usage: diffLines(a, b) returns array of {line, type: 'added'|'removed'|'unchanged'}
function diffLines(a, b) {
    const aLines = a.split('\n');
    const bLines = b.split('\n');
    const maxLen = Math.max(aLines.length, bLines.length);
    const diffs = [];
    for (let i = 0; i < maxLen; i++) {
        if (aLines[i] === bLines[i]) {
            diffs.push({ lineA: aLines[i] || '', lineB: bLines[i] || '', type: 'unchanged' });
        } else {
            diffs.push({ lineA: aLines[i] || '', lineB: bLines[i] || '', type: 'changed' });
        }
    }
    return diffs;
}

function renderDiff(a, b, containerA, containerB) {
    const diffs = diffLines(a, b);
    containerA.innerHTML = '';
    containerB.innerHTML = '';
    diffs.forEach(({ lineA, lineB, type }) => {
        const spanA = document.createElement('div');
        const spanB = document.createElement('div');
        spanA.textContent = lineA;
        spanB.textContent = lineB;
        if (type === 'changed') {
            spanA.style.background = '#fee2e2'; // red-100
            spanB.style.background = '#dbeafe'; // blue-100
        }
        containerA.appendChild(spanA);
        containerB.appendChild(spanB);
    });
}
