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
