/**
 * Face Attendance System — Frontend v2 (Cookie-based Auth)
 */

// ─── Auth Management (HttpOnly Cookies) ───

let _cachedUser = null;

function getUser() {
    return _cachedUser;
}

function logout() {
    _cachedUser = null;
    fetch('/api/auth/logout', { method: 'POST' }).catch(() => {});
    window.location.href = '/login';
}

// Check auth on every page (except login)
function requireAuth() {
    if (window.location.pathname === '/login') return;
    // Verify token via cookie
    fetch('/api/auth/me', { credentials: 'same-origin' })
        .then(r => {
            if (!r.ok) throw new Error('Unauthorized');
            return r.json();
        })
        .then(user => {
            _cachedUser = user;
            const el = document.getElementById('user-info');
            if (el) el.textContent = `${user.username} (${user.role})`;
        })
        .catch(() => {
            logout();
        });
}

// ─── XSS Protection ───

function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// ─── Toast Notifications ───

const MAX_TOASTS = 5;

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const existing = container.querySelectorAll('.toast:not(.toast-exit)');
    if (existing.length >= MAX_TOASTS) {
        dismissToast(existing[existing.length - 1]);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        info: 'fa-info-circle',
        warning: 'fa-exclamation-triangle',
    };

    toast.innerHTML = `
        <i class="fas ${icons[type] || icons.info}"></i>
        <span>${escapeHtml(message)}</span>
        <button class="toast-close" onclick="dismissToast(this.parentElement)">&times;</button>
    `;
    container.appendChild(toast);
    setTimeout(() => dismissToast(toast), 4500);
}

function dismissToast(toast) {
    if (!toast || toast.classList.contains('toast-exit')) return;
    toast.classList.add('toast-exit');
    setTimeout(() => toast.remove(), 300);
}

// ─── API Helpers (cookie-based auth) ───

async function apiFetch(url, options = {}) {
    const defaults = {
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
    };
    const merged = { ...defaults, ...options };
    merged.headers = { ...defaults.headers, ...(options.headers || {}) };

    if (merged.body && typeof merged.body === 'object' && !(merged.body instanceof FormData)) {
        merged.body = JSON.stringify(merged.body);
    }

    const response = await fetch(url, merged);

    if (response.status === 401) {
        logout();
        throw new Error('Session expired');
    }

    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || `Request failed: ${response.status}`);
    }
    return data;
}

// ─── Formatting ───

function formatDate(dateStr) {
    if (!dateStr) return '—';
    return new Date(dateStr).toLocaleDateString('en-IN', {
        year: 'numeric', month: 'short', day: 'numeric'
    });
}

function formatTime(ts) {
    if (!ts) return '—';
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatDuration(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return `${m}:${String(s).padStart(2, '0')}`;
}

// ─── Animated Counter ───

function animateCounter(element, target, duration = 800) {
    const start = parseInt(element.textContent) || 0;
    if (start === target) { element.textContent = target; return; }
    const startTime = performance.now();
    const isFloat = String(target).includes('.');

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = start + (target - start) * eased;
        element.textContent = isFloat ? current.toFixed(1) : Math.round(current);
        if (progress < 1) requestAnimationFrame(update);
        else element.textContent = isFloat ? parseFloat(target).toFixed(1) : target;
    }
    requestAnimationFrame(update);
}

// ─── Live Clock ───

function initClock() {
    const el = document.getElementById('live-clock');
    if (!el) return;
    function update() {
        el.textContent = new Date().toLocaleTimeString([], {
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        });
    }
    update();
    setInterval(update, 1000);
}

// ─── Mobile Sidebar ───

document.addEventListener('DOMContentLoaded', () => {
    requireAuth();

    const sidebar = document.getElementById('sidebar');
    const toggle = document.querySelector('.menu-toggle');

    if (toggle && sidebar) {
        toggle.addEventListener('click', () => sidebar.classList.toggle('open'));
        document.addEventListener('click', (e) => {
            if (sidebar.classList.contains('open') &&
                !sidebar.contains(e.target) && !toggle.contains(e.target)) {
                sidebar.classList.remove('open');
            }
        });
    }

    initClock();
});
