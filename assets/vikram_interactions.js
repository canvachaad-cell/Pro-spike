/**
 * Vikram AI Analyst Client Interactions
 * - Cmd+K / Ctrl+K keyboard shortcut toggle with auto-focus
 * - Escape key to close
 * - MutationObserver on #vikram-chat for automatic scroll-to-bottom
 */
(function () {
    'use strict';

    function focusInput() {
        setTimeout(function () {
            var input = document.getElementById('vikram-input');
            if (input) {
                input.focus();
                if (typeof input.select === 'function') {
                    input.select();
                }
            }
        }, 150);
    }

    function isPanelOpen() {
        var backdrop = document.getElementById('vikram-backdrop');
        if (backdrop && backdrop.classList.contains('open')) {
            return true;
        }
        var panel = document.getElementById('vikram-panel');
        if (panel && panel.style.transform && panel.style.transform.indexOf('translateX(0') !== -1) {
            return true;
        }
        return false;
    }

    // 1. Global Keyboard Shortcuts (⌘K, Ctrl+K, Escape)
    window.addEventListener('keydown', function (e) {
        var isK = (e.key === 'k' || e.key === 'K');
        var isCmdOrCtrl = e.metaKey || e.ctrlKey;

        if (isCmdOrCtrl && isK) {
            e.preventDefault();
            if (isPanelOpen()) {
                var closeBtn = document.getElementById('vikram-close');
                if (closeBtn) closeBtn.click();
            } else {
                var trigger = document.getElementById('vikram-trigger');
                if (trigger) {
                    trigger.click();
                    focusInput();
                } else {
                    // Mobile trigger fallback
                    var mobileTab = document.getElementById('mobile-vikram-tab');
                    if (mobileTab) {
                        mobileTab.click();
                        focusInput();
                    }
                }
            }
        } else if (e.key === 'Escape') {
            if (isPanelOpen()) {
                var closeBtn = document.getElementById('vikram-close');
                if (closeBtn) {
                    e.preventDefault();
                    closeBtn.click();
                }
            }
        }
    });

    // 2. Chat Auto-Scroll on new messages or thinking loader
    function attachChatScrollObserver() {
        var chat = document.getElementById('vikram-chat');
        if (!chat || chat.dataset.scrollObserved) return;
        chat.dataset.scrollObserved = 'true';

        var observer = new MutationObserver(function () {
            // Scroll down cleanly on message addition
            chat.scrollTop = chat.scrollHeight;
        });

        observer.observe(chat, { childList: true, subtree: true });
    }

    // Initialize observer when DOM is ready or when element appears
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', attachChatScrollObserver);
    } else {
        attachChatScrollObserver();
    }

    // Safety fallback: attach on first click or interaction if element was late-mounted by Dash
    document.addEventListener('click', function (e) {
        attachChatScrollObserver();
        if (e.target && (e.target.closest('#vikram-trigger') || e.target.closest('#mobile-vikram-tab'))) {
            focusInput();
        }
    });

    // 3. Dropdown A11y Sanitizer: ensure accessible label and prevent aria-hidden-focus violations in dcc.Dropdown
    function sanitizeAriaHiddenFocus() {
        var targets = document.querySelectorAll('.dash-dropdown-focus-target, .Select-input input');
        targets.forEach(function (el) {
            if (!el.getAttribute('aria-label')) {
                el.setAttribute('aria-label', 'Search stock');
            }
            var hiddenParent = el.closest('[aria-hidden="true"]');
            if (hiddenParent && hiddenParent !== el) {
                hiddenParent.removeAttribute('aria-hidden');
            }
            if (el.getAttribute('aria-hidden') === 'true') {
                el.removeAttribute('aria-hidden');
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', sanitizeAriaHiddenFocus);
    } else {
        sanitizeAriaHiddenFocus();
    }
    window.addEventListener('load', sanitizeAriaHiddenFocus);

    // Watch for dynamically rendered dropdowns on page navigation
    var bodyObserver = new MutationObserver(function () {
        sanitizeAriaHiddenFocus();
    });
    bodyObserver.observe(document.body || document.documentElement, { childList: true, subtree: true });
})();
