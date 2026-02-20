if (window.location.pathname.endsWith('index.html') || window.location.pathname === '/') {
    if (!isAuthenticated()) {
        window.location.href = 'login.html';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (!window.location.pathname.endsWith('login.html')) {
        initApp();
        setupDarkModeToggle();
        displayUsername();
    }
});

function displayUsername() {
    const usernameDisplay = document.getElementById('username-display');
    if (usernameDisplay) {
        const username = getUsername();
        usernameDisplay.textContent = username || 'User';
    }
}

function initApp() {
    setupNavigation();
    displayUsername();
    initTypingAnimation();

    document.getElementById('logout-btn')?.addEventListener('click', function() {
        showToast('Logged out successfully.', 'info');
        setTimeout(() => logout(), 800);
    });
}

function setupNavigation() {
    const navLinks = document.querySelectorAll('.nav-link, .nav-brand');
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const page = link.dataset.page;
            if (page) {
                showPage(page);
                // Set active state on nav links only
                document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
                if (link.classList.contains('nav-link')) {
                    link.classList.add('active');
                }
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
    } else if (pageName === 'test') {
        initTestSandbox();
    }
}

function setupDarkModeToggle() {
    const toggleBtn = document.getElementById('dark-toggle');
    const iconSpan = document.getElementById('dark-toggle-icon');
    if (!toggleBtn || !iconSpan) return;

    // Set initial mode from localStorage or system preference
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    let darkMode = localStorage.getItem('darkMode');
    if (darkMode === null) {
        darkMode = prefersDark ? 'true' : 'false';
    }
    applyDarkMode(darkMode === 'true');

    toggleBtn.addEventListener('click', () => {
        const isDark = document.body.classList.toggle('dark-mode');
        localStorage.setItem('darkMode', isDark ? 'true' : 'false');
        updateDarkModeIcon(isDark);
    });

    // Ensure icon is correct on load
    updateDarkModeIcon(document.body.classList.contains('dark-mode'));
}

function applyDarkMode(enable) {
    if (enable) {
        document.body.classList.add('dark-mode');
    } else {
        document.body.classList.remove('dark-mode');
    }
    updateDarkModeIcon(enable);
}

function updateDarkModeIcon(isDark) {
    const iconSpan = document.getElementById('dark-toggle-icon');
    if (!iconSpan) return;
    iconSpan.textContent = isDark ? '☀️' : '🌙';
}

// Typing animation for landing page
function initTypingAnimation() {
    const typedElement = document.querySelector('.typed-text');
    if (!typedElement) return;

    const phrases = ['Simple, but Fast!', 'Built for Speed.', 'Easy to Use.'];
    let phraseIndex = 0;
    let charIndex = 0;
    let isDeleting = false;
    let typingSpeed = 100;

    function type() {
        const currentPhrase = phrases[phraseIndex];
        
        if (isDeleting) {
            typedElement.textContent = currentPhrase.substring(0, charIndex - 1);
            charIndex--;
            typingSpeed = 50;
        } else {
            typedElement.textContent = currentPhrase.substring(0, charIndex + 1);
            charIndex++;
            typingSpeed = 100;
        }

        if (!isDeleting && charIndex === currentPhrase.length) {
            // Pause at end of phrase
            typingSpeed = 2000;
            isDeleting = true;
        } else if (isDeleting && charIndex === 0) {
            isDeleting = false;
            phraseIndex = (phraseIndex + 1) % phrases.length;
            typingSpeed = 500;
        }

        setTimeout(type, typingSpeed);
    }

    // Start typing animation
    setTimeout(type, 1000);
}