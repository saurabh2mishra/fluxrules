// Toast notification utility
window.showToast = function(message, type = "info", duration = 3500) {
    // Remove any existing toast
    document.querySelectorAll('.toast').forEach(t => t.remove());

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    // Color by type
    if (type === 'success') toast.style.borderColor = 'var(--success)';
    if (type === 'danger' || type === 'error') toast.style.borderColor = 'var(--danger)';
    if (type === 'warning') toast.style.borderColor = 'var(--warning)';
    if (type === 'info') toast.style.borderColor = 'var(--primary)';

    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = 0;
        setTimeout(() => toast.remove(), 400);
    }, duration);
};
