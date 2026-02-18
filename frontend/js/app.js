if (window.location.pathname.endsWith('index.html') || window.location.pathname === '/') {
    if (!isAuthenticated()) {
        window.location.href = 'login.html';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (!window.location.pathname.endsWith('login.html')) {
        initApp();
    }
});

function initApp() {
    setupNavigation();
    loadRules(); // Load rules on initial page load

    document.getElementById('logout-btn')?.addEventListener('click', logout);
}

function setupNavigation() {
    const navLinks = document.querySelectorAll('.nav-link');
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const page = link.dataset.page;
            if (page) {
                showPage(page);
            }
        });
    });
}

function showPage(pageName) {
    const pages = document.querySelectorAll('.page');
    pages.forEach(page => {
        page.style.display = 'none';
    });

    const targetPage = document.getElementById(`${pageName}-page`);
    if (targetPage) {
        targetPage.style.display = 'block';
    }

    // Load data when switching to specific pages
    if (pageName === 'rules') {
        loadRules();
    } else if (pageName === 'graph') {
        loadDependencyGraph();
    } else if (pageName === 'metrics') {
        loadMetrics();
    } else if (pageName === 'create') {
        initRuleBuilder();
    }
}