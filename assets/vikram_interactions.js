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
                    var mobileTab = document.getElementById('mobile-vikram-fab') || document.getElementById('mobile-vikram-tab');
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
        if (e.target && (e.target.closest('#vikram-trigger') || e.target.closest('#mobile-vikram-fab') || e.target.closest('#mobile-vikram-tab'))) {
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

    // 4. Client-side Vikram Watchdog (BUG-091 Safety Net Layer 2)
    // If the server never delivers resolve_message (proxy timeout, mobile drop, SIGKILL),
    // the dcc.Interval watchdog also never fires (it's server-driven).
    // This pure JS watchdog catches that last-resort case and clears the loader directly
    // from the browser DOM, re-enabling the input so the user is not permanently locked out.
    var _vikramQueryStart = null;
    var _CLIENT_WATCHDOG_MS = 55000;  // 55s: backend 45s + proxy grace + client round-trip

    function _clientWatchdogCheck() {
        if (!_vikramQueryStart) return;
        var elapsed = Date.now() - _vikramQueryStart;
        if (elapsed < _CLIENT_WATCHDOG_MS) return;

        var loader = document.querySelector('#vikram-chat .vikram-status');
        if (!loader) {
            // Loader already gone — query resolved normally.
            _vikramQueryStart = null;
            return;
        }

        console.warn('[VIKRAM CLIENT WATCHDOG] Loader still present after ' + Math.round(elapsed / 1000) + 's. Self-healing UI.');

        // Remove the stranded loader bubble
        if (loader.parentElement) loader.parentElement.remove();

        // Re-enable the input and send button
        var input = document.getElementById('vikram-input');
        var sendBtn = document.getElementById('vikram-send');
        if (input) {
            input.disabled = false;
            input.placeholder = 'Ask Vikram anything…';
        }
        if (sendBtn) sendBtn.disabled = false;

        // Append a timeout notice to the chat
        var chat = document.getElementById('vikram-chat');
        if (chat) {
            var notice = document.createElement('div');
            notice.className = 'self-start max-w-[95%] bg-white/5 border border-outline-variant/60 text-on-surface rounded-xl rounded-bl-sm px-4 py-3 text-sm font-body-md leading-relaxed';
            notice.innerHTML = '⚠️ <em>Vikram did not respond within 55s — the server or network stalled. Your input is re-enabled. Please try asking again.</em>';
            chat.appendChild(notice);
            chat.scrollTop = chat.scrollHeight;
        }

        _vikramQueryStart = null;
    }

    // Detect when a query is submitted (the loader bubble appears in #vikram-chat)
    var _chatForWatchdog = null;
    function _attachChatWatchdogObserver() {
        _chatForWatchdog = document.getElementById('vikram-chat');
        if (!_chatForWatchdog || _chatForWatchdog.dataset.watchdogObserved) return;
        _chatForWatchdog.dataset.watchdogObserved = 'true';

        var wdObserver = new MutationObserver(function (mutations) {
            for (var i = 0; i < mutations.length; i++) {
                for (var j = 0; j < mutations[i].addedNodes.length; j++) {
                    var node = mutations[i].addedNodes[j];
                    if (node && node.querySelector && node.querySelector('.vikram-status')) {
                        // A loader bubble was just added — start the client watchdog.
                        _vikramQueryStart = Date.now();
                    }
                }
                // If all .vikram-status elements are gone, the query resolved — reset.
                if (!_chatForWatchdog.querySelector('.vikram-status')) {
                    _vikramQueryStart = null;
                }
            }
        });
        wdObserver.observe(_chatForWatchdog, { childList: true, subtree: true });
    }

    setInterval(_clientWatchdogCheck, 2000);  // poll every 2s (low overhead)

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _attachChatWatchdogObserver);
    } else {
        _attachChatWatchdogObserver();
    }
    document.addEventListener('click', function () { _attachChatWatchdogObserver(); });
})();
