(function (global) {
    const PREFIX = '+998';

    function digitsOnly(s) {
        return String(s || '').replace(/\D/g, '');
    }

    function normalizePhone(raw) {
        let d = digitsOnly(raw);

        if (d.startsWith('998')) d = d.slice(3);

        if (d.startsWith('8') && d.length === 10) d = d.slice(1);

        d = d.slice(0, 9);
        return PREFIX + d;
    }

    function isPhoneInput(el) {
        if (!el || el.tagName !== 'INPUT') return false;
        if (el.type === 'hidden') return false;
        if (el.dataset && el.dataset.phoneUz === 'off') return false;
        const name = (el.getAttribute('name') || '').toLowerCase();
        const id = (el.id || '').toLowerCase();
        const ac = (el.getAttribute('autocomplete') || '').toLowerCase();
        const ph = (el.getAttribute('placeholder') || '').toLowerCase();
        if (el.type === 'tel' || ac === 'tel') return true;
        if (el.classList && el.classList.contains('phone-uz')) return true;
        if (name === 'phone' || name === 'phone_number' || name.endsWith('_phone')) return true;
        if (id.includes('phone') || id.includes('tel')) return true;
        if (ph.includes('+998') || ph.includes('telefon')) return true;
        return false;
    }

    function ensurePrefix(el) {
        if (!el) return;
        const cur = el.value || '';
        if (!cur.trim()) {
            el.value = PREFIX;
            return;
        }
        el.value = normalizePhone(cur);
    }

    function onFocus(e) {
        const el = e.target;
        ensurePrefix(el);

        try {
            const len = el.value.length;
            el.setSelectionRange(len, len);
        } catch (err) {  }
    }

    function onInput(e) {
        const el = e.target;
        const before = el.value;
        const norm = normalizePhone(before);
        if (before !== norm) {
            el.value = norm;
            try {
                const len = el.value.length;
                el.setSelectionRange(len, len);
            } catch (err) {  }
        }

        if (!el.value.startsWith(PREFIX)) {
            el.value = normalizePhone(el.value);
        }
    }

    function onBlur(e) {
        const el = e.target;

        ensurePrefix(el);
        if (el.value === PREFIX) {

            if (!el.required) el.value = '';
        }
    }

    function onKeyDown(e) {
        const el = e.target;

        if ((e.key === 'Backspace' || e.key === 'Delete') && el.selectionStart <= PREFIX.length) {
            if (el.selectionStart !== el.selectionEnd) return;
            if (e.key === 'Backspace' && el.selectionStart <= PREFIX.length) {
                e.preventDefault();
                try {
                    el.setSelectionRange(PREFIX.length, PREFIX.length);
                } catch (err) {  }
            }
        }
    }

    function bind(el) {
        if (!el || el.dataset.phoneUzBound === '1') return;
        if (!isPhoneInput(el)) return;
        el.dataset.phoneUzBound = '1';
        el.setAttribute('inputmode', 'tel');
        el.setAttribute('autocomplete', 'tel');
        if (!el.getAttribute('placeholder')) {
            el.setAttribute('placeholder', '+998 XX XXX XX XX');
        }
        el.addEventListener('focus', onFocus);
        el.addEventListener('input', onInput);
        el.addEventListener('blur', onBlur);
        el.addEventListener('keydown', onKeyDown);

        if (!(el.value || '').trim()) {

        } else {
            el.value = normalizePhone(el.value);
        }
    }

    function bindAll(root) {
        const scope = root || document;
        scope.querySelectorAll('input').forEach(bind);
    }

    function ensureAll(root) {
        const scope = root || document;
        scope.querySelectorAll('input').forEach((el) => {
            if (!isPhoneInput(el)) return;
            bind(el);
            if (!(el.value || '').trim() || el.value === PREFIX) {
                el.value = PREFIX;
            } else {
                el.value = normalizePhone(el.value);
            }
        });
    }

    const api = {
        PREFIX: PREFIX,
        normalize: normalizePhone,
        bind: bind,
        bindAll: bindAll,
        ensure: ensurePrefix,
        ensureAll: ensureAll,
    };

    global.PhoneUz = api;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => bindAll(document));
    } else {
        bindAll(document);
    }
})(window);
