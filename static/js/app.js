/**
 * PosyHub Student Management System
 * Complete JavaScript - Mobile First
 */

// =============================================================================
// SIDEBAR
// =============================================================================
function openSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    if (sidebar) sidebar.classList.add('open');
    if (overlay) overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('active');
    document.body.style.overflow = '';
}

// =============================================================================
// THEME
// =============================================================================
function isAuthed() {
    return !!document.querySelector('meta[name="user-authed"]');
}

function getPreferredTheme() {
    // For a logged-in user the server-rendered theme (their saved choice) wins.
    if (isAuthed()) {
        const meta = document.querySelector('meta[name="user-theme"]');
        if (meta && meta.content) return meta.content;
    }
    const stored = localStorage.getItem('theme');
    if (stored) return stored;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function saveTheme(key) {
    fetch('/set-theme', {
        method: 'POST',
        headers: { 'X-Requested-With': 'fetch', 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'theme=' + encodeURIComponent(key),
        credentials: 'same-origin'
    }).catch(function () {});
}

function markActiveTheme(key) {
    document.querySelectorAll('.theme-swatch').forEach(function (sw) {
        var on = sw.getAttribute('data-theme-key') === key;
        sw.classList.toggle('active', on);
        sw.setAttribute('aria-checked', on ? 'true' : 'false');
    });
}

function initThemePicker() {
    var btn = document.getElementById('themeBtn');
    var menu = document.getElementById('themeMenu');
    if (!btn || !menu) return;
    markActiveTheme(document.documentElement.getAttribute('data-theme') || 'light');
    btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var open = menu.classList.toggle('open');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    document.addEventListener('click', function (e) {
        if (!menu.contains(e.target) && e.target !== btn) menu.classList.remove('open');
    });
    menu.querySelectorAll('.theme-swatch').forEach(function (sw) {
        sw.addEventListener('click', function () {
            var key = sw.getAttribute('data-theme-key');
            setTheme(key);
            markActiveTheme(key);
            menu.classList.remove('open');
            saveTheme(key);
        });
    });
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    setTheme(current === 'dark' ? 'light' : 'dark');
}

// =============================================================================
// MODALS
// =============================================================================
function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

function closeAllModals() {
    document.querySelectorAll('.modal.active').forEach(m => m.classList.remove('active'));
    document.body.style.overflow = '';
}

// =============================================================================
// SUBMENUS
// =============================================================================
function initSubmenus() {
    document.querySelectorAll('.has-submenu > .nav-link').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const parent = this.parentElement;
            document.querySelectorAll('.has-submenu.open').forEach(item => {
                if (item !== parent) item.classList.remove('open');
            });
            parent.classList.toggle('open');
        });
    });
}

// =============================================================================
// ADD CONTACT FUNCTIONALITY
// =============================================================================
function addNewContact() {
    const container = document.getElementById('contactsContainer');
    if (!container) return;
    
    const contactRow = document.createElement('div');
    contactRow.className = 'contact-row';
    contactRow.innerHTML = `
        <div class="form-group">
            <label class="form-label">Name</label>
            <input type="text" name="contact_name[]" class="form-control" placeholder="e.g., Mr. John">
        </div>
        <div class="form-group">
            <label class="form-label">Phone</label>
            <input type="tel" name="phone_number[]" class="form-control" placeholder="08012345678">
        </div>
        <div class="form-group">
            <label class="form-label">Relationship</label>
            <select name="relationship[]" class="form-control">
                <option value="Father">Father</option>
                <option value="Mother">Mother</option>
                <option value="Guardian">Guardian</option>
                <option value="Sibling">Sibling</option>
                <option value="Other">Other</option>
            </select>
        </div>
        <button type="button" class="btn btn-danger btn-sm remove-contact-btn" onclick="this.parentElement.remove()">
            <i class="fas fa-times"></i> Remove
        </button>
    `;
    container.appendChild(contactRow);
}

// =============================================================================
// ATTENDANCE FUNCTIONS
// =============================================================================
function markAllPresent() {
    document.querySelectorAll('input[name="present[]"]').forEach(cb => cb.checked = true);
    updateAttendanceCount();
}

function markAllAbsent() {
    document.querySelectorAll('input[name="present[]"]').forEach(cb => cb.checked = false);
    updateAttendanceCount();
}

function updateAttendanceCount() {
    const total = document.querySelectorAll('input[name="present[]"]').length;
    const present = document.querySelectorAll('input[name="present[]"]:checked').length;
    const countEl = document.getElementById('attendanceCount');
    if (countEl) {
        countEl.textContent = `${present}/${total}`;
    }
}

// =============================================================================
// SELECT ALL STUDENTS
// =============================================================================
function toggleSelectAll(checkbox) {
    document.querySelectorAll('.student-checkbox').forEach(cb => cb.checked = checkbox.checked);
    updateSelectionCount();
}

function updateSelectionCount() {
    const selected = document.querySelectorAll('.student-checkbox:checked').length;
    const countEl = document.getElementById('selectedCount');
    if (countEl) countEl.textContent = selected;
}

// =============================================================================
// CONFIRM DELETE
// =============================================================================
function confirmDelete(message) {
    return confirm(message || 'Are you sure you want to delete this? This action cannot be undone.');
}

// =============================================================================
// FLASH MESSAGES
// =============================================================================
function initFlashMessages() {
    document.querySelectorAll('.flash-message').forEach(flash => {
        setTimeout(() => {
            flash.style.transition = 'opacity 0.3s, transform 0.3s';
            flash.style.opacity = '0';
            flash.style.transform = 'translateY(-10px)';
            setTimeout(() => flash.remove(), 300);
        }, 5000);
    });
}

// =============================================================================
// VIEW-ONLY PAGES — hide create / update / delete controls
// =============================================================================
// The server still blocks every write; this just removes the controls a
// view-only user could otherwise click. Scoped to .page-content so the shared
// sidebar/header are never touched.
function hideWriteControls() {
    var scope = document.querySelector('.page-content[data-readonly]');
    if (!scope) return;

    var WRITE_ICONS = '.fa-plus, .fa-trash, .fa-trash-can, .fa-trash-alt, .fa-pen, .fa-pen-to-square, .fa-edit, .fa-pencil, .fa-pencil-alt';
    var WRITE_SEGMENTS = /\/(add|new|create|edit|update|delete|remove|assign|record)(\/|$|\?|-)/i;

    function hide(el) {
        if (!el || el.classList.contains('keep-on-readonly')) return;
        // climb to the clickable control (a/button) if an inner icon matched
        var ctl = el.closest ? (el.closest('a, button') || el) : el;
        if (ctl.classList && ctl.classList.contains('keep-on-readonly')) return;
        ctl.style.display = 'none';
    }

    // 1) Controls carrying a write icon (Add / Edit / Delete).
    scope.querySelectorAll(WRITE_ICONS).forEach(hide);
    // 2) Links pointing at a write endpoint.
    scope.querySelectorAll('a[href]').forEach(function (a) {
        try {
            var path = new URL(a.href, window.location.origin).pathname;
            if (WRITE_SEGMENTS.test(path)) hide(a);
        } catch (e) {}
    });
    // 3) Destructive buttons + submit buttons inside non-GET forms.
    scope.querySelectorAll('.btn-danger').forEach(hide);
    scope.querySelectorAll('form').forEach(function (f) {
        var m = (f.getAttribute('method') || 'get').toLowerCase();
        if (m === 'get') return;
        f.querySelectorAll('button[type="submit"], input[type="submit"], button:not([type])').forEach(hide);
    });
}

// =============================================================================
// SIDEBAR ACCORDION + BOTTOM NAV
// =============================================================================
// Groups the sidebar into collapsible sections; on mobile only the section for
// the current page is expanded (and scrolled into view) so you don't hunt for it.
// Also builds a bottom nav of the current section's key items on mobile.
function initSidebarNav() {
    var list = document.querySelector('.sidebar-nav > ul');
    if (!list) return;

    // Build groups: a .nav-section header + the items until the next header.
    var groups = [];
    var current = { header: null, items: [] };
    Array.prototype.forEach.call(list.children, function (li) {
        if (li.classList.contains('nav-section')) {
            if (current.header || current.items.length) groups.push(current);
            current = { header: li, items: [] };
        } else {
            current.items.push(li);
        }
    });
    if (current.header || current.items.length) groups.push(current);

    // Active link = the longest nav href that prefixes the current path.
    var path = window.location.pathname, bestLink = null, bestLen = -1;
    list.querySelectorAll('a.nav-link[href]').forEach(function (a) {
        var p;
        try { p = new URL(a.href).pathname; } catch (e) { return; }
        if (p === '/') { if (path === '/' && bestLen < 0) { bestLink = a; bestLen = 0; } return; }
        if (path === p || path.indexOf(p + '/') === 0 || path.indexOf(p) === 0) {
            if (p.length > bestLen) { bestLink = a; bestLen = p.length; }
        }
    });
    var activeLi = bestLink ? bestLink.closest('li') : null;
    var activeGroup = null;
    groups.forEach(function (g) { if (activeLi && g.items.indexOf(activeLi) >= 0) activeGroup = g; });

    var mobile = window.innerWidth < 1024;
    groups.forEach(function (g) {
        if (!g.header) return;                 // items before the first header stay visible
        g.header.classList.add('nav-section-toggle');
        if (!g.header.querySelector('.nav-sec-chev')) {
            var chev = document.createElement('i');
            chev.className = 'fas fa-chevron-down nav-sec-chev';
            g.header.appendChild(chev);
        }
        var setOpen = function (open) {
            g.header.classList.toggle('open', open);
            g.items.forEach(function (i) { i.style.display = open ? '' : 'none'; });
        };
        setOpen(mobile ? (g === activeGroup) : true);
        g.header.addEventListener('click', function () {
            setOpen(!g.header.classList.contains('open'));
        });
    });
    if (bestLink) { try { bestLink.scrollIntoView({ block: 'center' }); } catch (e) {} }

    buildBottomNav(activeGroup ? activeGroup.items : []);
}

function buildBottomNav(items) {
    var bar = document.getElementById('bottomNav');
    if (!bar) return;
    var html = '<a href="/" class="bn-item"><i class="fas fa-home"></i><span>Home</span></a>';
    items.slice(0, 4).forEach(function (li) {
        var a = li.querySelector('a.nav-link[href]');
        if (!a) return;
        var icon = a.querySelector('i');
        var label = a.querySelector('span');
        var href = a.getAttribute('href');
        var active = a.classList.contains('active') || href === window.location.pathname;
        html += '<a href="' + href + '" class="bn-item' + (active ? ' active' : '') + '">'
              + (icon ? icon.outerHTML : '') + '<span>' + (label ? label.textContent : '') + '</span></a>';
    });
    html += '<button type="button" class="bn-item" id="bnMore"><i class="fas fa-bars"></i><span>Menu</span></button>';
    bar.innerHTML = html;
    var more = document.getElementById('bnMore');
    if (more) more.addEventListener('click', openSidebar);
}

// =============================================================================
// INITIALIZATION
// =============================================================================
document.addEventListener('DOMContentLoaded', function() {
    // Theme
    setTheme(getPreferredTheme());

    // Hide write controls on view-only pages (and again after each soft-nav swap,
    // since the page body is replaced without a full reload).
    hideWriteControls();
    window.addEventListener('spa:loaded', function () { try { hideWriteControls(); } catch (e) {} });

    // Mobile menu
    const menuBtn = document.getElementById('mobileMenuBtn');
    if (menuBtn) menuBtn.addEventListener('click', openSidebar);

    // Accordion sidebar + mobile bottom nav (scoped to the current section)
    initSidebarNav();
    
    // Sidebar toggle
    const sidebarToggle = document.getElementById('sidebarToggle');
    if (sidebarToggle) sidebarToggle.addEventListener('click', closeSidebar);
    
    // Sidebar overlay
    const overlay = document.getElementById('sidebarOverlay');
    if (overlay) overlay.addEventListener('click', closeSidebar);
    
    // Theme picker
    initThemePicker();
    
    // Close sidebar on nav link click (mobile)
    document.querySelectorAll('.sidebar .nav-link').forEach(link => {
        link.addEventListener('click', function() {
            if (window.innerWidth < 1024 && !this.closest('.has-submenu')) {
                closeSidebar();
            }
        });
    });
    
    // Submenus
    initSubmenus();
    
    // Add Contact Button
    const addContactBtn = document.getElementById('addContactBtn');
    if (addContactBtn) {
        addContactBtn.addEventListener('click', addNewContact);
    }
    
    // Flash messages
    initFlashMessages();
    
    // Attendance checkboxes
    document.querySelectorAll('input[name="present[]"]').forEach(cb => {
        cb.addEventListener('change', updateAttendanceCount);
    });
    
    // Student checkboxes
    document.querySelectorAll('.student-checkbox').forEach(cb => {
        cb.addEventListener('change', updateSelectionCount);
    });
    
    // Select all checkbox
    const selectAll = document.getElementById('selectAll');
    if (selectAll) {
        selectAll.addEventListener('change', function() {
            toggleSelectAll(this);
        });
    }
    
    // Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeSidebar();
            closeAllModals();
        }
    });
    
    // Modal click outside
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', function(e) {
            if (e.target === this) {
                this.classList.remove('active');
                document.body.style.overflow = '';
            }
        });
    });
});

// System theme change listener — only when the user has no explicit choice.
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
    if (!isAuthed() && !localStorage.getItem('theme')) {
        setTheme(e.matches ? 'dark' : 'light');
    }
});

// =============================================================================
// CLIENT ERROR REPORTING — surface device-side JS errors in the Error Log
// =============================================================================
// Throttled + deduped so a noisy loop can't flood the server. CSRF-exempt
// diagnostic endpoint; failures here are swallowed (never error on erroring).
(function () {
    var sent = 0, MAX = 8, seen = {};
    function report(message, url, stack) {
        try {
            if (sent >= MAX) return;
            var key = (message || '') + '|' + (url || '');
            if (seen[key]) return;
            seen[key] = 1; sent++;
            fetch('/client-error', {
                method: 'POST', credentials: 'same-origin', keepalive: true,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: String(message || 'error').slice(0, 500),
                                       url: url || location.href,
                                       stack: String(stack || '').slice(0, 4000) })
            }).catch(function () {});
        } catch (e) {}
    }
    window.addEventListener('error', function (e) {
        if (e && e.message) report(e.message, location.href, e.error && e.error.stack);
    });
    window.addEventListener('unhandledrejection', function (e) {
        var r = e && e.reason;
        report((r && (r.message || r)) || 'Unhandled promise rejection', location.href, r && r.stack);
    });
    // Let React error boundaries (and any code) report explicitly.
    window.reportClientError = report;
})();

// =============================================================================
// NOTIFICATIONS — header bell (in-app notifications)
// =============================================================================
(function () {
    var btn = document.getElementById('notifBtn');
    var menu = document.getElementById('notifMenu');
    var list = document.getElementById('notifList');
    var badge = document.getElementById('notifBadge');
    if (!btn || !menu || !list) return;

    function csrf() {
        var m = document.querySelector('meta[name="csrf-token"]');
        return m ? m.getAttribute('content') : '';
    }
    function esc(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }

    function render(data) {
        var n = (data && data.count) || 0;
        if (n > 0) { badge.textContent = n > 99 ? '99+' : n; badge.hidden = false; }
        else { badge.hidden = true; }
        var items = (data && data.items) || [];
        if (!items.length) { list.innerHTML = '<div class="notif-empty">No notifications</div>'; return; }
        list.innerHTML = items.map(function (it) {
            return '<a class="notif-item' + (it.is_read ? '' : ' unread') + '" data-id="' + it.id +
                (it.url ? '" href="' + esc(it.url) : '') + '">' +
                '<div class="nt">' + esc(it.title) + '</div>' +
                (it.body ? '<div class="nb">' + esc(it.body) + '</div>' : '') +
                '<div class="nw">' + esc(it.when) + '</div></a>';
        }).join('');
    }

    function load() {
        fetch('/api/notifications', { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (d) { if (d) render(d); })
            .catch(function () {});
    }
    function markRead(id) {
        fetch('/api/notifications/' + id + '/read', { method: 'POST', credentials: 'same-origin',
            headers: { 'X-CSRFToken': csrf(), 'X-Requested-With': 'fetch' } }).catch(function () {});
    }

    btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var open = menu.classList.toggle('open');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open) load();
    });
    document.addEventListener('click', function (e) {
        if (!menu.contains(e.target) && e.target !== btn) menu.classList.remove('open');
    });
    list.addEventListener('click', function (e) {
        var a = e.target.closest('.notif-item'); if (!a) return;
        var id = a.getAttribute('data-id');
        if (id) markRead(id);
        a.classList.remove('unread');
        if (!a.getAttribute('href')) e.preventDefault();   // no link → just mark read
    });
    var readAll = document.getElementById('notifReadAll');
    if (readAll) readAll.addEventListener('click', function () {
        fetch('/api/notifications/read-all', { method: 'POST', credentials: 'same-origin',
            headers: { 'X-CSRFToken': csrf(), 'X-Requested-With': 'fetch' } })
            .then(function () { load(); }).catch(function () {});
    });

    load();                                  // initial count on page load
    setInterval(load, 120000);               // refresh every 2 min
})();
