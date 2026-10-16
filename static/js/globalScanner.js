(function () {
    const SCAN_GAP_RESET_MS = 300
    const SCAN_MAX_AVG_INTERVAL_MS = 80
    const SCAN_MIN_LEN = 4
    const STORAGE_KEY = 'pendingScanAction'

    let buffer = ''
    let lastKeyTime = 0
    let intervals = []
    let busy = false
    let pendingBarcode = ''
    let pendingProduct = null

    function isLikelyScan() {
        if (buffer.length < SCAN_MIN_LEN) return false
        if (!intervals.length) return buffer.length >= 6
        const avg = intervals.reduce((a, b) => a + b, 0) / intervals.length
        return avg <= SCAN_MAX_AVG_INTERVAL_MS
    }

    function formatMoneyLocal(price, currency) {
        if (typeof formatMoney === 'function') {
            return formatMoney(price, currency)
        }
        const n = parseFloat(price)
        if (Number.isNaN(n)) return '—'
        const cur = currency || 'UZS'
        try {
            return new Intl.NumberFormat('uz-UZ').format(n) + ' ' + cur
        } catch (e) {
            return n + ' ' + cur
        }
    }

    function modalEl() {
        return document.getElementById('global-scan-modal')
    }

    function hideModal() {
        const m = modalEl()
        if (!m) return
        m.classList.add('hidden')
        m.setAttribute('aria-hidden', 'true')
        pendingBarcode = ''
        pendingProduct = null
    }

    function showModal(barcode, product) {
        const m = modalEl()
        if (!m) return

        pendingBarcode = barcode
        pendingProduct = product && product.found !== false ? product : null

        const img = document.getElementById('gscan-img')
        const nameEl = document.getElementById('gscan-name')
        const metaEl = document.getElementById('gscan-meta')
        const codeEl = document.getElementById('gscan-barcode')
        const badgeEl = document.getElementById('gscan-badge')

        if (codeEl) codeEl.textContent = barcode

        if (pendingProduct && pendingProduct.id) {
            if (nameEl) nameEl.textContent = pendingProduct.name || 'Mahsulot'
            const parts = []
            if (pendingProduct.price != null) {
                parts.push(formatMoneyLocal(pendingProduct.price, pendingProduct.currency))
            }
            if (pendingProduct.stock != null) {
                parts.push('Qoldiq: ' + pendingProduct.stock)
            }
            if (pendingProduct.branch_name) {
                parts.push(pendingProduct.branch_name)
            }
            if (metaEl) metaEl.textContent = parts.join(' · ') || 'Tizimda topildi'
            if (badgeEl) {
                badgeEl.textContent = 'Topildi'
                badgeEl.className = 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800'
            }
            if (img) {
                if (pendingProduct.image) {
                    img.src = pendingProduct.image
                    img.classList.remove('hidden')
                } else {
                    img.removeAttribute('src')
                    img.classList.add('hidden')
                }
            }
        } else {
            if (nameEl) nameEl.textContent = 'Mahsulot topilmadi'
            if (metaEl) {
                metaEl.textContent = (product && product.message)
                    ? product.message
                    : 'Ombor orqali yangi mahsulot sifatida kiritish mumkin'
            }
            if (badgeEl) {
                badgeEl.textContent = 'Katalogda yo‘q'
                badgeEl.className = 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800'
            }
            if (img) {
                img.removeAttribute('src')
                img.classList.add('hidden')
            }
        }

        m.classList.remove('hidden')
        m.setAttribute('aria-hidden', 'false')
    }

    async function handleGlobalScan(code) {
        const barcode = String(code || '').trim()
        if (!barcode || busy) return
        busy = true
        try {
            const url = `/product_scan_info/?barcode=${encodeURIComponent(barcode)}`
            const response = await fetch(url, { credentials: 'same-origin' })
            const data = await response.json().catch(() => ({ found: false, barcode }))
            showModal(barcode, data)
        } catch (e) {
            console.error(e)
            showModal(barcode, { found: false, barcode, message: 'Tarmoq xatosi — Ombor orqali davom eting' })
        } finally {
            busy = false
        }
    }

    function onPosPage() {
        return /\/pos_terminal\/?$/.test(window.location.pathname)
    }

    function onOmborPage() {
        return /\/inventory_intake\/?$/.test(window.location.pathname)
    }

    function savePending(type, barcode, product) {
        try {
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
                type,
                barcode,
                product: product || null,
                at: Date.now(),
            }))
        } catch (e) {  }
    }

    function addProductToTerminalCart(product, barcode) {
        if (product && product.id && typeof addItemToCart === 'function') {
            addItemToCart({
                id: product.id,
                name: product.name,
                price: parseFloat(product.price),
                currency: product.currency || 'UZS',
                unit: product.unit || 'ta',
                qty: 1,
                img: product.image || '',
                stock: product.stock,
            })
            return true
        }
        if (typeof processScan === 'function') {
            processScan(barcode)
            return true
        }
        return false
    }

    function startTerminal() {
        const barcode = pendingBarcode
        const product = pendingProduct
        hideModal()
        if (!barcode) return

        if (onPosPage()) {
            const ok = addProductToTerminalCart(product, barcode)
            if (!ok) {
                alert('Terminal ochiq emas yoki savat yuklanmadi')
            }
            return
        }

        savePending('terminal', barcode, product)
        window.location.href = '/pos_terminal/'
    }

    function startOmbor() {
        const barcode = pendingBarcode
        const product = pendingProduct
        hideModal()
        if (!barcode) return

        if (onOmborPage()) {
            if (typeof window.intakeLookupBarcode === 'function') {
                window.intakeLookupBarcode(barcode)
            } else {
                const input = document.getElementById('barcode-input')
                if (input) {
                    input.value = barcode
                    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
                }
            }
            return
        }

        savePending('ombor', barcode, product)
        window.location.href = '/inventory_intake/'
    }

    function stripScanFromInput(target, code) {
        if (!target || !code) return
        const tag = (target.tagName || '').toUpperCase()
        if (tag !== 'INPUT' && tag !== 'TEXTAREA') return
        try {
            const val = target.value || ''
            if (val === code || val.endsWith(code)) {
                target.value = val === code ? '' : val.slice(0, -code.length)
            }
        } catch (e) {  }
    }

    document.addEventListener('keydown', (e) => {
        if (typeof isStageOpen !== 'undefined' && isStageOpen) return
        if (e.ctrlKey || e.metaKey || e.altKey) return

        const modal = modalEl()
        if (modal && !modal.classList.contains('hidden')) {
            if (e.key === 'Escape') {
                e.preventDefault()
                hideModal()
            }
            return
        }

        const now = Date.now()
        const gap = now - lastKeyTime
        if (gap > SCAN_GAP_RESET_MS) {
            buffer = ''
            intervals = []
        } else if (buffer.length > 0 && gap > 0) {
            intervals.push(gap)
        }
        lastKeyTime = now

        if (e.key === 'Enter' || e.keyCode === 13) {
            if (buffer && isLikelyScan()) {
                const code = buffer
                buffer = ''
                intervals = []
                e.preventDefault()
                e.stopPropagation()
                stripScanFromInput(e.target, code)
                handleGlobalScan(code)
            } else {
                buffer = ''
                intervals = []
            }
            return
        }

        if (e.key && e.key.length === 1) {
            buffer += e.key
        }
    }, true)

    document.addEventListener('DOMContentLoaded', () => {
        const closeBtn = document.getElementById('gscan-close')
        const terminalBtn = document.getElementById('gscan-terminal')
        const omborBtn = document.getElementById('gscan-ombor')
        const backdrop = document.getElementById('global-scan-modal')

        if (closeBtn) closeBtn.addEventListener('click', hideModal)
        if (terminalBtn) terminalBtn.addEventListener('click', startTerminal)
        if (omborBtn) omborBtn.addEventListener('click', startOmbor)
        if (backdrop) {
            backdrop.addEventListener('click', (e) => {
                if (e.target === backdrop) hideModal()
            })
        }
    })

    window.GlobalScanner = {
        handle: handleGlobalScan,
        hide: hideModal,
        STORAGE_KEY,
    }
})()
