/**
 * PosyHub Student Management System
 * Complete JavaScript - Mobile First
 */

// =============================================================================
// SHARED HTML-ESCAPING HELPERS
// One canonical escaper for any place that builds an HTML string from DB/user
// data (names, comments, etc.) and assigns it via innerHTML. Escapes the five
// dangerous characters INCLUDING quotes, so values are also safe inside a
// double- or single-quoted attribute. Exposed on window so inline template
// scripts (which load after app.js) can reuse it instead of redefining a
// weaker local esc().
// =============================================================================
(function () {
    var MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    window.escapeHtml = function (s) {
        return (s == null ? '' : String(s)).replace(/[&<>"']/g, function (c) { return MAP[c]; });
    };
    // Return a URL only if it is a safe scheme (relative path, ?query, #hash, or
    // http/https); anything else (e.g. javascript:) collapses to '#'. Use before
    // dropping a data-supplied URL into an href/src.
    window.safeUrl = function (u) {
        u = (u == null ? '' : String(u)).trim();
        if (/^(\/|\?|#|https?:\/\/)/i.test(u) && !/^\s*javascript:/i.test(u)) return u;
        return '#';
    };
})();

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

// A11y: many filter/form <select>s have a visible .form-label that isn't
// programmatically associated, so screen readers announce them with no name
// (axe "select-name"). Copy the nearest label text into aria-label. Runs on load,
// after each SPA swap, and via a MutationObserver so React re-renders stay covered.
function labelSelects(root) {
    var scope = root || document;
    scope.querySelectorAll('select.form-control:not([aria-label]):not([aria-labelledby])').forEach(function (sel) {
        if (sel.id && document.querySelector('label[for="' + sel.id + '"]')) return;
        var group = sel.closest('.form-group');
        var lbl = group ? group.querySelector('.form-label, label') : null;
        if (!lbl) {
            var prev = sel.previousElementSibling;
            if (prev && prev.matches && prev.matches('label, .form-label')) lbl = prev;
        }
        var txt = lbl ? lbl.textContent.replace(/[*]/g, '').trim() : '';
        if (txt) sel.setAttribute('aria-label', txt);
    });
}
function initSelectLabels() {
    labelSelects(document);
    window.addEventListener('spa:loaded', function () { try { labelSelects(document); } catch (e) {} });
    var host = document.querySelector('.page-content');
    if (host && window.MutationObserver) {
        var t;
        new MutationObserver(function () { clearTimeout(t); t = setTimeout(function () { labelSelects(host); }, 150); })
            .observe(host, { childList: true, subtree: true });
    }
}

// Live client-side search over a rendered list. Binds every
// Live lists. input[data-live-search="containerId"] filters that container's
// [data-search] rows by text (lowercase haystack; every word must match).
// Filter controls [data-lf="containerId"] narrow the same rows instantly, by
// their data-lf-rule:
//   "min:<attr>" / "max:<attr>"  numeric row attribute data-<attr> >= / <= value
//   "subject" / "grade"          row data-results = "subject::grade|…" — with
//                                both set, one result must match both (as the
//                                server filters do)
// A filter that the server already applied (its name is in the URL) can only
// be widened by the server, so changing it reloads the form instead; client
// changes are mirrored into the URL so a refresh keeps them. Capped lists
// expand while anything is active; data-live-count shows "n of N".
function initLiveSearch() {
    var ids = {};
    var els = document.querySelectorAll('input[data-live-search], [data-lf]');
    for (var i = 0; i < els.length; i++) {
        ids[els[i].getAttribute('data-live-search') || els[i].getAttribute('data-lf')] = true;
    }
    Object.keys(ids).forEach(bindLiveList);
}

function bindLiveList(id) {
    var container = document.getElementById(id);
    var search = document.querySelector('input[data-live-search="' + id + '"]');
    var filters = Array.prototype.slice.call(document.querySelectorAll('[data-lf="' + id + '"]'));
    if (!container) {
        // No list on this view (e.g. a summary tab): filters still apply, via the server.
        filters.forEach(function (f) {
            var t = null, isText = f.tagName === 'INPUT';
            f.addEventListener(isText ? 'input' : 'change', function () {
                if (!f.form) return;
                clearTimeout(t);
                t = setTimeout(function () { f.form.submit(); }, isText ? 700 : 0);
            });
        });
        return;
    }
    var countId = (search && search.getAttribute('data-live-count')) || container.getAttribute('data-live-count');
    var countEl = countId ? document.getElementById(countId) : null;
    var caps = container.querySelectorAll('.cap-list');
    var url = new URL(window.location.href);
    // data-lf-client: a filter only the browser applies (the server ignores
    // it) — restore it from the URL after a refresh instead.
    filters.forEach(function (f) {
        if (f.hasAttribute('data-lf-client') && f.name && url.searchParams.get(f.name)) f.value = url.searchParams.get(f.name);
    });
    var serverSide = filters.some(function (f) {
        return !f.hasAttribute('data-lf-client') && f.name && (url.searchParams.get(f.name) || '') !== '';
    });

    function val(f) { return (f.value || '').trim(); }

    function apply() {
        var q = search ? (search.value || '').trim().toLowerCase() : '';
        var tokens = q ? q.split(/\s+/) : [];
        var subj = '', grade = '', nums = [];
        if (!serverSide) {
            filters.forEach(function (f) {
                var rule = f.getAttribute('data-lf-rule') || '', v = val(f);
                if (!v) return;
                if (rule === 'subject') subj = v.toLowerCase();
                else if (rule === 'grade') grade = v.toLowerCase();
                else if (/^(min|max):/.test(rule) && !isNaN(parseFloat(v))) {
                    nums.push([rule.slice(0, 3), rule.slice(4), parseFloat(v)]);
                }
            });
        }
        var items = container.querySelectorAll('[data-search]');
        // Some lists render each row twice (phone cards + desktop table); count
        // only the layout that is on screen.
        var counted = 0, shown = 0;
        for (var k = 0; k < items.length; k++) {
            var it = items[k], hay = it.getAttribute('data-search') || '', ok = true;
            for (var t = 0; ok && t < tokens.length; t++) ok = hay.indexOf(tokens[t]) !== -1;
            for (var n = 0; ok && n < nums.length; n++) {
                var x = parseFloat(it.getAttribute('data-' + nums[n][1]));
                if (isNaN(x)) x = 0;
                ok = nums[n][0] === 'min' ? x >= nums[n][2] : x <= nums[n][2];
            }
            if (ok && (subj || grade)) {
                var res = (it.getAttribute('data-results') || '').toLowerCase().split('|');
                ok = res.some(function (r) {
                    var p = r.split('::');
                    return (!subj || p[0] === subj) && (!grade || p[1] === grade);
                });
            }
            it.style.display = ok ? '' : 'none';
            var onScreen = !it.parentElement || it.parentElement.getClientRects().length > 0;
            if (onScreen) { counted++; if (ok) shown++; }
        }
        var active = !!q || (!serverSide && (subj || grade || nums.length));
        for (var c = 0; c < caps.length; c++) caps[c].classList.toggle('expanded', !!active);
        if (countEl) countEl.textContent = active ? (shown + ' of ' + counted) : '';
    }

    function remember() {
        var u = new URL(window.location.href);
        filters.forEach(function (f) { if (f.name) { if (val(f)) u.searchParams.set(f.name, val(f)); else u.searchParams.delete(f.name); } });
        try { window.history.replaceState(window.history.state, '', u.toString()); } catch (e) { /* ignore */ }
    }

    var timer = null;
    function reload(delay) {
        var form = filters[0] && filters[0].form;
        if (!form) return;
        clearTimeout(timer);
        timer = setTimeout(function () { form.submit(); }, delay);
    }

    if (search) search.addEventListener('input', apply);
    filters.forEach(function (f) {
        var isText = f.tagName === 'INPUT';
        f.addEventListener(isText ? 'input' : 'change', function () {
            if (serverSide) { reload(isText ? 700 : 0); return; }
            apply(); remember();
        });
    });
    // Enter in a filter box never needs a round-trip in client mode.
    filters.concat(search ? [search] : []).forEach(function (f) {
        if (!f.form) return;
        f.addEventListener('keydown', function (e) {
            if (e.key !== 'Enter') return;
            if (serverSide) { e.preventDefault(); reload(0); } else e.preventDefault();
        });
    });
    if ((search && (search.value || '').trim()) || filters.some(function (f) { return val(f); })) apply();
}

// Show/hide each cap-list's "Show all" toggle based on whether the list really
// overflows its cap on the current device. The button controlling a cap-list is
// the sibling [data-cap-toggle] immediately after it (or one whose selector
// targets it). If a cap-list overflows but has no button, inject a generic one
// so no capped content is ever unreachable.
function capListToggleFor(list) {
    var sib = list.nextElementSibling;
    if (sib && sib.getAttribute && sib.getAttribute('data-cap-toggle') !== null) return sib;
    // Or a button elsewhere targeting this list by selector/id.
    if (list.id) {
        var byId = document.querySelector('[data-cap-toggle="#' + list.id + '"]');
        if (byId) return byId;
    }
    return null;
}

function initCapLists() {
    var lists = document.querySelectorAll('.cap-list');
    for (var i = 0; i < lists.length; i++) {
        var list = lists[i];
        var btn = capListToggleFor(list);
        // Never fight an expanded list or an active live-search reveal.
        var expanded = list.classList.contains('expanded');
        var overflowing = list.scrollHeight > list.clientHeight + 4;
        if (!btn) {
            if (overflowing && !expanded) {
                btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'btn btn-secondary btn-sm cap-toggle';
                btn.setAttribute('data-cap-toggle', '');
                btn.setAttribute('data-more', 'Show all');
                btn.setAttribute('data-less', 'Show fewer');
                btn.innerHTML = '<i class="fas fa-chevron-down" aria-hidden="true"></i> <span class="cap-label">Show all</span>';
                list.parentNode.insertBefore(btn, list.nextSibling);
            }
            continue;
        }
        // A rendered button: reveal only when the list overflows (or is already
        // expanded, so the user can collapse it again).
        btn.style.display = (overflowing || expanded) ? '' : 'none';
    }
}

// Account dropdown (consolidates install / clear-cache / logout / identity).
function initProfileMenu() {
    var btn = document.getElementById('profileBtn');
    var menu = document.getElementById('profileMenu');
    if (!btn || !menu) return;
    btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var open = menu.classList.toggle('open');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    document.addEventListener('click', function (e) {
        if (!menu.contains(e.target) && e.target !== btn && !btn.contains(e.target)) {
            menu.classList.remove('open');
            btn.setAttribute('aria-expanded', 'false');
        }
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { menu.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); }
    });
}

// On small screens the inline search bar is hidden; this toggles it open as a
// full-width row under the header (focusing the field) instead of losing search.
function initMobileSearch() {
    var btn = document.getElementById('mobileSearchBtn');
    var header = document.querySelector('.top-header');
    var form = document.querySelector('.header-search');
    if (!btn || !header || !form) return;
    btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var open = header.classList.toggle('search-open');
        if (open) { var inp = form.querySelector('input'); if (inp) inp.focus(); }
    });
}

// A print/export link's URL is otherwise identical on every click (same
// batch, same params), so the server's own no-store headers only stop a NEW
// response from being cached going forward -- they can't invalidate an entry
// the browser already cached under that exact URL from before a route
// started sending those headers. Any <a data-cache-bust> gets a fresh
// timestamp query param stamped on right before the browser follows it, so
// it's a URL that's never been cached under, sidestepping that regardless of
// which layer (HTTP cache, service worker, PDF viewer) was holding onto it.
// Delegated on document (not bound per-element) so it keeps working after a
// soft-nav page swap without needing to be re-initialized.
function initCacheBustLinks() {
    document.addEventListener('click', function (e) {
        var a = e.target.closest && e.target.closest('a[data-cache-bust]');
        if (!a) return;
        var url = new URL(a.href, window.location.origin);
        url.searchParams.set('_cb', Date.now());
        a.href = url.toString();
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
// Themed, promise-based confirm driven by the shell's #confirmModal — the vanilla
// counterpart to React's confirm(). Resolves true/false; falls back to the native
// dialog only when the modal markup isn't on the page (e.g. standalone/print views).
var _confirmResolve = null;
function themedConfirm(message) {
    return new Promise(function (resolve) {
        var modal = document.getElementById('confirmModal');
        var msg = document.getElementById('confirmMessage');
        if (!modal || !msg) { resolve(window.confirm(message)); return; }
        msg.textContent = message || 'Are you sure?';
        _confirmResolve = resolve;
        openModal('confirmModal');
        var ok = document.getElementById('confirmBtn');
        if (ok) { try { ok.focus(); } catch (e) {} }
    });
}
function _settleConfirm(val) {
    if (!_confirmResolve) return;
    var r = _confirmResolve; _confirmResolve = null;
    closeModal('confirmModal');
    r(val);
}
function initConfirmModal() {
    var modal = document.getElementById('confirmModal');
    if (!modal) return;
    var ok = document.getElementById('confirmBtn');
    if (ok) ok.addEventListener('click', function () { _settleConfirm(true); });
    // Cancel / ✕ (data-call=closeModal) and backdrop click resolve to false.
    modal.addEventListener('click', function (e) {
        if (e.target === modal || (e.target.closest && e.target.closest('[data-call="closeModal"]'))) {
            _settleConfirm(false);
        }
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && _confirmResolve) _settleConfirm(false);
    });
}
window.themedConfirm = themedConfirm;

function confirmDelete(message) {
    return themedConfirm(message || 'Are you sure you want to delete this? This action cannot be undone.');
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
// ACTIVE MENU ITEM
// =============================================================================
// Highlight the menu item for the page you're on — including pages you reach by
// drilling down from it (a student profile from All Students, a student's exam
// report from Exam Analytics…). Order:
//   1. an item the server already marked active (its own rules);
//   2. an item whose link is exactly this page;
//   3. the item whose link this page sits under, by whole path segments
//      (/students/94/edit → /students), longest first;
//   4. otherwise the item you came from (remembered per tab), when you got here
//      by following a link inside the app.
var NAV_KEY = 'navActiveHref';
function navPath(a) {
    try { var u = new URL(a.href, window.location.origin); return u.origin === window.location.origin ? u.pathname.replace(/\/+$/, '') || '/' : null; }
    catch (e) { return null; }
}
function markActiveNav(list) {
    list = list || document.querySelector('.sidebar-nav > ul');
    if (!list) return null;
    var links = Array.prototype.filter.call(list.querySelectorAll('a.nav-link[href]'), function (a) {
        var h = a.getAttribute('href'); return h && h !== '#' && h.indexOf('javascript:') !== 0;
    });
    links.forEach(function (a) { if (a.dataset.autoActive) { a.classList.remove('active'); a.removeAttribute('aria-current'); delete a.dataset.autoActive; } });
    var pick = links.filter(function (a) { return a.classList.contains('active') && !a.closest('.has-submenu > .nav-link'); })[0] || null;
    var path = window.location.pathname.replace(/\/+$/, '') || '/';
    if (!pick) pick = links.filter(function (a) { return navPath(a) === path; })[0] || null;
    if (!pick) {
        var bestLen = -1;
        links.forEach(function (a) {
            var p = navPath(a);
            if (!p || p === '/') return;
            if (path.indexOf(p + '/') === 0 && p.length > bestLen) { pick = a; bestLen = p.length; }
        });
    }
    if (!pick) {
        var remembered = null;
        try { remembered = sessionStorage.getItem(NAV_KEY); } catch (e) {}
        var cameFromApp = document.referrer && document.referrer.indexOf(window.location.origin) === 0;
        if (remembered && (cameFromApp || window.history.length > 1)) {
            pick = links.filter(function (a) { return a.getAttribute('href') === remembered; })[0] || null;
        }
    }
    if (pick) {
        if (!pick.classList.contains('active')) { pick.classList.add('active'); pick.dataset.autoActive = '1'; }
        pick.setAttribute('aria-current', 'page');
        try { sessionStorage.setItem(NAV_KEY, pick.getAttribute('href')); } catch (e) {}
    }
    return pick;
}
// Clicking a menu item makes it the remembered one straight away.
document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('.sidebar-nav a.nav-link[href]');
    if (!a) return;
    var h = a.getAttribute('href');
    if (h && h !== '#') { try { sessionStorage.setItem(NAV_KEY, h); } catch (err) {} }
}, true);
// Sections that change the address without a reload (their own routers).
(function () {
    function again() { setTimeout(function () { try { markActiveNav(); } catch (e) {} }, 0); }
    ['pushState', 'replaceState'].forEach(function (m) {
        var orig = window.history[m];
        if (typeof orig !== 'function') return;
        window.history[m] = function () { var r = orig.apply(this, arguments); again(); return r; };
    });
    window.addEventListener('popstate', again);
})();

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

    var bestLink = markActiveNav(list);
    var activeLi = bestLink ? bestLink.closest('li') : null;
    var activeGroup = null;
    groups.forEach(function (g) { if (activeLi && g.items.indexOf(activeLi) >= 0) activeGroup = g; });

    var mobile = window.innerWidth < 1024;
    var STORE = 'navSections';
    function readState() { try { return JSON.parse(localStorage.getItem(STORE) || '{}'); } catch (e) { return {}; } }
    function writeState(s) { try { localStorage.setItem(STORE, JSON.stringify(s)); } catch (e) {} }
    var saved = readState();

    groups.forEach(function (g) {
        if (!g.header) return;                 // items before the first header stay visible
        var key = (g.header.textContent || '').trim();
        g.header.classList.add('nav-section-toggle');
        // Keep the <li> a valid list item (role=button on an <li> breaks list
        // semantics / WCAG); it's still keyboard-operable via tabindex + the
        // keydown handler below, and announces state via aria-expanded.
        g.header.setAttribute('tabindex', '0');
        if (!g.header.querySelector('.nav-sec-chev')) {
            var chev = document.createElement('i');
            chev.className = 'fas fa-chevron-down nav-sec-chev';
            chev.setAttribute('aria-hidden', 'true');
            g.header.appendChild(chev);
        }
        var setOpen = function (open, persist) {
            g.header.classList.toggle('open', open);
            g.header.setAttribute('aria-expanded', open ? 'true' : 'false');
            g.items.forEach(function (i) { i.style.display = open ? '' : 'none'; });
            if (persist && !mobile) { var s = readState(); s[key] = open; writeState(s); }
        };
        // Mobile: only the active section open. Desktop: active section always open,
        // otherwise honour the user's saved choice (default expanded).
        var initOpen = mobile ? (g === activeGroup)
                     : (g === activeGroup ? true : (key in saved ? saved[key] !== false : true));
        setOpen(initOpen, false);
        var toggle = function () { setOpen(!g.header.classList.contains('open'), true); };
        g.header.addEventListener('click', toggle);
        g.header.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
        });
    });
    if (bestLink) { try { bestLink.scrollIntoView({ block: 'center' }); } catch (e) {} }

    buildSidebarFilter(groups);
    buildBottomNav(activeGroup ? activeGroup.items : []);
}

// A client-side quick-filter at the top of the sidebar — narrows the 70+ nav
// items by label as you type, revealing matches even inside collapsed sections.
function buildSidebarFilter(groups) {
    var nav = document.querySelector('.sidebar-nav');
    if (!nav || document.getElementById('navFilter')) return;
    var wrap = document.createElement('div');
    wrap.className = 'nav-filter';
    wrap.innerHTML = '<i class="fas fa-magnifying-glass" aria-hidden="true"></i>'
        + '<input type="search" id="navFilter" placeholder="Filter menu…" aria-label="Filter navigation">';
    nav.insertBefore(wrap, nav.firstChild);
    var input = wrap.querySelector('input');
    input.addEventListener('input', function () {
        var q = input.value.trim().toLowerCase();
        groups.forEach(function (g) {
            var anyVisible = false;
            g.items.forEach(function (li) {
                var a = li.querySelector('a.nav-link');
                var label = a ? (a.textContent || '').toLowerCase() : '';
                if (!q) {
                    var open = !g.header || g.header.classList.contains('open');
                    li.style.display = open ? '' : 'none';
                } else {
                    var show = label.indexOf(q) >= 0;
                    li.style.display = show ? '' : 'none';
                    if (show) anyVisible = true;
                }
            });
            if (g.header) g.header.style.display = (!q || anyVisible) ? '' : 'none';
        });
    });
}

function buildBottomNav(items) {
    var bar = document.getElementById('bottomNav');
    if (!bar) return;
    var home = window.location.pathname === '/';
    var html = '<a href="/" class="bn-item' + (home ? ' active' : '') + '"' + (home ? ' aria-current="page"' : '')
             + '><i class="fas fa-home"></i><span>Home</span></a>';
    // The section's own "Dashboard" link is the same page as Home — skip it so
    // the bar never shows two tabs for one screen.
    items.filter(function (li) {
        var a = li.querySelector('a.nav-link[href]');
        return a && a.getAttribute('href') !== '/';
    }).slice(0, 4).forEach(function (li) {
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

// Recompute the active section and rebuild the bottom nav for the current URL.
// Called after each SPA swap (the bottom nav is JS-built, so syncActive in
// spa-nav.js can't restyle it — it must be regenerated for the new page).
function refreshBottomNav() {
    var list = document.querySelector('.sidebar-nav > ul');
    if (!list) return;
    var groups = [], current = { header: null, items: [] };
    Array.prototype.forEach.call(list.children, function (li) {
        if (li.classList.contains('nav-section')) {
            if (current.header || current.items.length) groups.push(current);
            current = { header: li, items: [] };
        } else { current.items.push(li); }
    });
    if (current.header || current.items.length) groups.push(current);

    var bestLink = markActiveNav(list);
    var activeLi = bestLink ? bestLink.closest('li') : null;
    var activeGroup = null;
    groups.forEach(function (g) { if (activeLi && g.items.indexOf(activeLi) >= 0) activeGroup = g; });
    buildBottomNav(activeGroup ? activeGroup.items : []);
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
    // React screens mount/re-render asynchronously after load, so a one-shot pass
    // misses their buttons. Watch the read-only page body and re-hide (debounced).
    (function () {
        var ro = document.querySelector('.page-content[data-readonly]');
        if (!ro || !window.MutationObserver) return;
        var t;
        new MutationObserver(function () {
            clearTimeout(t);
            t = setTimeout(function () { try { hideWriteControls(); } catch (e) {} }, 120);
        }).observe(ro, { childList: true, subtree: true });
    })();
    // Rebuild the mobile bottom nav so its active item tracks the soft-navigated page.
    window.addEventListener('spa:loaded', function () { try { refreshBottomNav(); } catch (e) {} });

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

    // Profile dropdown + mobile search
    initProfileMenu();
    initMobileSearch();

    // Print/export download links (data-cache-bust) -- see its own comment
    initCacheBustLinks();

    // Themed confirm modal (vanilla data-confirm flows)
    initConfirmModal();

    // A11y: give unlabeled <select>s an accessible name from their visible label
    initSelectLabels();

    // Progressive disclosure: [data-cap-toggle] buttons reveal a capped list.
    document.addEventListener('click', function (e) {
        var btn = e.target.closest && e.target.closest('[data-cap-toggle]');
        if (!btn) return;
        var sel = btn.getAttribute('data-cap-toggle');
        var list = sel ? document.querySelector(sel) : btn.previousElementSibling;
        if (!list || !list.classList.contains('cap-list')) return;
        var expanded = list.classList.toggle('expanded');
        var lbl = btn.querySelector('.cap-label');
        if (lbl) lbl.textContent = expanded ? (btn.getAttribute('data-less') || 'Show less')
                                            : (btn.getAttribute('data-more') || 'Show all');
    });

    // A "Show all" button is only useful when the capped list actually clips its
    // content — and that depends on the device, not on a fixed row count. (A
    // filtered list of 10 fits on a wide desktop table but overflows the same cap
    // as tall mobile cards, where a count-based gate wrongly hid the button.)
    // So show the toggle exactly when the list overflows, and re-check on resize.
    initCapLists();
    setTimeout(initCapLists, 300);                 // re-check after fonts/badges settle
    window.addEventListener('load', initCapLists);
    var _capT;
    window.addEventListener('resize', function () {
        clearTimeout(_capT); _capT = setTimeout(initCapLists, 200);
    });

    // Live client-side search: an <input data-live-search="containerId"> instantly
    // filters that container's [data-search] elements (cards + rows) as the user
    // types — no round-trip. Any .cap-list inside is expanded while filtering so
    // matches beyond the fold show. data-live-count names a element to hold "N of M".
    initLiveSearch();

    // Close the sidebar (mobile) when any real navigation link is clicked.
    // Delegated so it also covers links inside an expanded submenu — those are
    // plain <a> elements (not .nav-link), which the old per-element binding
    // missed, so the drawer stayed open on a submenu pick (e.g. the Timetable
    // Generator menu). The submenu PARENT toggle (href="#"/.submenu-toggle) only
    // opens the submenu, so it must NOT close the drawer.
    const sidebarEl = document.querySelector('.sidebar');
    if (sidebarEl) {
        sidebarEl.addEventListener('click', function(e) {
            if (window.innerWidth >= 1024) return;
            const link = e.target.closest('a[href]');
            if (!link || !sidebarEl.contains(link)) return;
            const href = link.getAttribute('href');
            if (!href || href.charAt(0) === '#' || link.classList.contains('submenu-toggle')) return;
            closeSidebar();
        });
    }
    
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
// SESSION KEEPALIVE — keep an ACTIVELY-USED tab from idling out mid-task
// =============================================================================
// The server logs users out after SESSION_IDLE_MINUTES of no requests. Reading
// or printing a long page (e.g. a broadsheet) makes no server requests, so a
// later click on Download / Open would hit an expired session and bounce to
// login. Ping a tiny endpoint on real user activity (throttled, visible only)
// so active tabs stay alive; a walked-away tab (no activity) still idles out as
// intended, preserving the timeout's purpose. Best-effort — failures ignored.
(function () {
    var last = 0;
    var MIN_GAP = 3 * 60 * 1000;   // at most one ping per 3 minutes
    function ping() {
        if (document.visibilityState !== 'visible') return;
        var now = Date.now();
        if (now - last < MIN_GAP) return;
        last = now;
        fetch('/api/session/ping', {
            method: 'GET', credentials: 'same-origin',
            headers: { 'X-Requested-With': 'fetch' }
        }).catch(function () {});
    }
    ['mousemove', 'keydown', 'scroll', 'click', 'touchstart'].forEach(function (ev) {
        window.addEventListener(ev, ping, { passive: true });
    });
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') { last = 0; ping(); }
    });
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
    var esc = window.escapeHtml;

    function render(data) {
        var n = (data && data.count) || 0;
        if (n > 0) { badge.textContent = n > 99 ? '99+' : n; badge.hidden = false; }
        else { badge.hidden = true; }
        var items = (data && data.items) || [];
        if (!items.length) { list.innerHTML = '<div class="notif-empty">No notifications</div>'; return; }
        list.innerHTML = items.map(function (it) {
            return '<a class="notif-item' + (it.is_read ? '' : ' unread') + '" data-id="' + esc(it.id) +
                (it.url ? '" href="' + esc(window.safeUrl(it.url)) : '') + '">' +
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

/* Frosted top-header: add a hairline shadow once the page is scrolled (Phase 2
   shell polish). Works whether the window or .main-content is the scroller. */
(function () {
    var header = document.querySelector('.top-header');
    if (!header) return;
    var scroller = document.querySelector('.main-content') || window;
    var target = scroller === window ? document.documentElement : scroller;
    function onScroll() {
        var y = scroller === window ? (window.scrollY || target.scrollTop) : target.scrollTop;
        header.classList.toggle('is-scrolled', y > 4);
    }
    scroller.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
})();
