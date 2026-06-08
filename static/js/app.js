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
// INITIALIZATION
// =============================================================================
document.addEventListener('DOMContentLoaded', function() {
    // Theme
    setTheme(getPreferredTheme());

    // Hide write controls on view-only pages
    hideWriteControls();
    
    // Mobile menu
    const menuBtn = document.getElementById('mobileMenuBtn');
    if (menuBtn) menuBtn.addEventListener('click', openSidebar);
    
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
