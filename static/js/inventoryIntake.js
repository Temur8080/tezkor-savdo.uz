(function () {
    const barcodeInput = document.getElementById('barcode-input')
    const branchSelect = document.getElementById('intake-branch')
    const productPanel = document.getElementById('product-panel')
    const qtyInput = document.getElementById('qty-input')
    const noteInput = document.getElementById('note-input')
    const addBtn = document.getElementById('add-stock-btn')
    const quickMode = document.getElementById('quick-mode')
    const statusMsg = document.getElementById('status-msg')
    const logBox = document.getElementById('intake-log')
    const undoBtn = document.getElementById('undo-btn')
    const clearLogBtn = document.getElementById('clear-log-btn')
    const qtyMinus = document.getElementById('qty-minus')
    const qtyPlus = document.getElementById('qty-plus')
    const lowStockBadge = document.getElementById('low-stock-badge')
    const newItemBadge = document.getElementById('new-item-badge')
    const modeBadge = document.getElementById('mode-badge')
    const productNameInput = document.getElementById('product-name-input')
    const categorySelect = document.getElementById('category-select')
    const supplierSelect = document.getElementById('supplier-select')
    const entryCurrency = document.getElementById('entry-currency')
    const storeCurrency = document.getElementById('store-currency')
    const costPriceInput = document.getElementById('cost-price-input')
    const basePriceInput = document.getElementById('base-price-input')
    const minStockInput = document.getElementById('min-stock-input')
    const warrantyDaysInput = document.getElementById('warranty-days-input')
    const replacementDaysInput = document.getElementById('replacement-days-input')
    const serviceWarrantyInput = document.getElementById('service-warranty-input')
    const usdRateInput = document.getElementById('usd-rate')
    const imageInput = document.getElementById('image-input')
    const productImage = document.getElementById('product-image')
    const costConverted = document.getElementById('cost-converted')
    const sellConverted = document.getElementById('sell-converted')
    const convertHint = document.getElementById('convert-hint')
    const addCategoryBtn = document.getElementById('add-category-btn')
    const saveRateBtn = document.getElementById('save-rate-btn')
    const newProductBtn = document.getElementById('new-product-btn')

    let currentProduct = null
    let isNewProduct = false
    let pendingImageFile = null
    let intakeLog = []
    let scanning = false
    let lastScanAt = 0
    let lastScanCode = ''
    let currentBarcode = ''

    const STORAGE_KEY = 'ombor_kirim_log_v3'

    function csrfToken() {
        const el = document.querySelector('[name=csrfmiddlewaretoken]')
        return el ? el.value : ''
    }

    function branchId() {
        return branchSelect ? branchSelect.value : ''
    }

    function storageKey() {
        return `${STORAGE_KEY}_${branchId() || 'none'}`
    }

    function num(v) {
        const n = parseFloat(String(v || '').replace(',', '.'))
        return Number.isFinite(n) ? n : 0
    }

    function rate() {
        return Math.max(0.0001, num(usdRateInput.value) || 12500)
    }

    function convert(amount, from, to) {
        const a = num(amount)
        if (from === to) return a
        if (from === 'USD' && to === 'UZS') return a * rate()
        if (from === 'UZS' && to === 'USD') return a / rate()
        return a
    }

    function fmtMoney(value, currency) {
        const a = num(value)
        if (currency === 'USD') {
            return '$' + a.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
        }
        return Math.round(a).toLocaleString('ru-RU') + ' so‘m'
    }

    function updateConversionHints() {
        const entry = entryCurrency.value
        const store = storeCurrency.value
        const cost = num(costPriceInput.value)
        const sell = num(basePriceInput.value)
        const alt = entry === 'USD' ? 'UZS' : 'USD'

        costConverted.textContent = cost
            ? `≈ ${fmtMoney(convert(cost, entry, alt), alt)} · saqlanadi: ${fmtMoney(convert(cost, entry, store), store)}`
            : ''
        sellConverted.textContent = sell
            ? `≈ ${fmtMoney(convert(sell, entry, alt), alt)} · saqlanadi: ${fmtMoney(convert(sell, entry, store), store)}`
            : ''

        if (entry === store) {
            convertHint.textContent = `Narxlar ${entry === 'USD' ? 'dollar' : 'so‘m'}da kiritiladi va shu valyutada saqlanadi. Kurs: 1 USD = ${rate().toLocaleString('ru-RU')} so‘m.`
        } else if (entry === 'USD' && store === 'UZS') {
            convertHint.textContent = `Dollarda kiritilgan tannarx/sotish narxi so‘mga o‘girilib saqlanadi (× ${rate().toLocaleString('ru-RU')}).`
        } else {
            convertHint.textContent = `So‘mda kiritilgan narxlar dollarga o‘girilib saqlanadi (÷ ${rate().toLocaleString('ru-RU')}).`
        }
    }

    function loadLog() {
        try {
            const raw = localStorage.getItem(storageKey())
            intakeLog = raw ? JSON.parse(raw) : []
            if (!Array.isArray(intakeLog)) intakeLog = []
        } catch (e) {
            intakeLog = []
        }
        renderLog()
        updateStats()
        updateUndoBtn()
    }

    function saveLog() {
        try {
            localStorage.setItem(storageKey(), JSON.stringify(intakeLog.slice(0, 50)))
        } catch (e) {  }
    }

    function setStatus(text, kind) {
        statusMsg.textContent = text || ''
        const base = 'text-sm font-medium min-h-[1.5rem] px-3 py-2 rounded-md border '
        if (kind === 'ok') statusMsg.className = base + 'bg-green-50 text-green-700 border-green-100'
        else if (kind === 'err') statusMsg.className = base + 'bg-red-50 text-red-700 border-red-100'
        else if (kind === 'info') statusMsg.className = base + 'bg-blue-50 text-blue-700 border-blue-100'
        else statusMsg.className = base + 'bg-gray-50 text-gray-600 border-gray-100'
    }

    function playTone(ok) {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)()
            const osc = ctx.createOscillator()
            const gain = ctx.createGain()
            osc.connect(gain)
            gain.connect(ctx.destination)
            osc.frequency.value = ok ? 880 : 220
            gain.gain.value = 0.04
            osc.start()
            setTimeout(() => { osc.stop(); ctx.close() }, ok ? 90 : 180)
        } catch (e) {  }
    }

    function setImagePreview(url) {
        if (url) {
            productImage.innerHTML = `<img src="${url}" alt="" class="h-full w-full object-cover">`
        } else {
            productImage.innerHTML = '<span class="text-sm text-gray-400">Rasm</span>'
        }
    }

    function selectCategory(name) {
        if (!name) return
        let found = false
        Array.from(categorySelect.options).forEach((opt) => {
            if (opt.value === name) found = true
        })
        if (!found) {
            const opt = document.createElement('option')
            opt.value = name
            opt.textContent = name
            categorySelect.appendChild(opt)
        }
        categorySelect.value = name
    }

    function showNewProductForm(barcode) {
        isNewProduct = true
        currentProduct = null
        currentBarcode = barcode
        pendingImageFile = null
        productPanel.classList.remove('hidden')
        modeBadge.textContent = 'Yangi mahsulot'
        modeBadge.className = 'px-2 py-1 text-xs font-semibold text-purple-800 bg-purple-100 rounded-full'
        lowStockBadge.classList.add('hidden')
        newItemBadge.classList.remove('hidden')
        newItemBadge.textContent = 'Katalogda yo‘q'

        productNameInput.value = ''
        costPriceInput.value = ''
        basePriceInput.value = ''
        minStockInput.value = 3
        if (warrantyDaysInput) warrantyDaysInput.value = 365
        if (replacementDaysInput) replacementDaysInput.value = 7
        if (serviceWarrantyInput) serviceWarrantyInput.value = 90
        qtyInput.value = 1
        if (noteInput) noteInput.value = ''
        entryCurrency.value = 'USD'
        storeCurrency.value = 'UZS'
        setImagePreview(null)
        document.getElementById('product-meta').textContent =
            `Shtrix-kod: ${barcode} · Yangi yozuv yaratiladi`

        updateConversionHints()
        productNameInput.focus()
    }

    function showExistingProduct(data) {
        isNewProduct = false
        currentProduct = data
        currentBarcode = data.barcode
        pendingImageFile = null
        productPanel.classList.remove('hidden')

        modeBadge.textContent = 'Mavjud mahsulot'
        modeBadge.className = 'px-2 py-1 text-xs font-semibold text-blue-800 bg-blue-100 rounded-full'
        lowStockBadge.classList.toggle('hidden', !data.is_low_stock)
        newItemBadge.classList.toggle('hidden', !!data.in_branch)
        newItemBadge.textContent = 'Filialda yangi'

        productNameInput.value = data.name || ''
        selectCategory(data.category)
        if (data.supplier_id && supplierSelect) {
            supplierSelect.value = String(data.supplier_id)
        }
        storeCurrency.value = data.currency || 'UZS'
        entryCurrency.value = data.currency || 'UZS'
        costPriceInput.value = data.cost_price != null ? data.cost_price : ''
        basePriceInput.value = data.price != null ? data.price : ''
        minStockInput.value = data.min_stock_level != null ? data.min_stock_level : 3
        if (warrantyDaysInput) warrantyDaysInput.value = data.warranty_days != null ? data.warranty_days : 365
        if (replacementDaysInput) replacementDaysInput.value = data.replacement_days != null ? data.replacement_days : 7
        if (serviceWarrantyInput) serviceWarrantyInput.value = data.service_warranty_days != null ? data.service_warranty_days : 90
        qtyInput.value = 1
        if (noteInput) noteInput.value = ''
        setImagePreview(data.image || null)

        document.getElementById('product-meta').textContent =
            `Shtrix-kod: ${data.barcode} · Joriy qoldiq: ${data.stock} · ${data.branch_name}`

        updateConversionHints()
        if (!(quickMode && quickMode.checked)) {
            qtyInput.focus()
            qtyInput.select()
        }
    }

    function updateStats() {
        const positive = intakeLog.filter((i) => (i.qty_added || 0) > 0)
        const totalQty = positive.reduce((sum, i) => sum + (i.qty_added || 0), 0)
        const skus = new Set(positive.map((i) => i.barcode)).size
        document.getElementById('stat-count').textContent = String(positive.length)
        document.getElementById('stat-qty').textContent = String(totalQty)
        document.getElementById('stat-skus').textContent = String(skus)
    }

    function updateUndoBtn() {
        const last = intakeLog[0]
        undoBtn.disabled = !(last && last.qty_added > 0 && !last.undone)
    }

    function escapeHtml(str) {
        return String(str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
    }

    function renderLog() {
        if (!intakeLog.length) {
            logBox.innerHTML = '<p class="text-gray-400 text-sm text-center py-10">Hali kirim yo‘q</p>'
            updateStats()
            updateUndoBtn()
            return
        }

        logBox.innerHTML = intakeLog.map((item) => {
            const positive = (item.qty_added || 0) > 0
            const qtyClass = positive ? 'text-green-700' : 'text-orange-700'
            const qtyText = positive ? `+${item.qty_added}` : String(item.qty_added)
            const prices = (item.cost_price || item.price)
                ? `<p class="text-xs text-gray-500 mt-1">Tannarx: ${escapeHtml(item.cost_price || '—')} / Sotish: ${escapeHtml(item.price || '—')} ${escapeHtml(item.currency || '')}</p>`
                : ''
            const note = item.note ? `<p class="text-xs text-gray-500 mt-1">${escapeHtml(item.note)}</p>` : ''
            const undone = item.undone
                ? '<span class="ml-2 px-2 py-0.5 text-[10px] font-semibold text-orange-800 bg-orange-100 rounded-full">BEKOR</span>'
                : ''
            return `
                <div class="px-4 py-3 hover:bg-gray-50 ${item.undone ? 'opacity-50' : ''}">
                    <div class="flex justify-between gap-2">
                        <p class="font-semibold text-sm text-gray-900">${escapeHtml(item.name)}${undone}</p>
                        <span class="${qtyClass} font-bold text-sm">${qtyText}</span>
                    </div>
                    <p class="text-xs text-gray-500 mt-1">
                        ${escapeHtml(item.barcode)} · Qoldiq: ${item.stock}
                        ${item.time ? ' · ' + item.time : ''}
                    </p>
                    ${prices}
                    ${note}
                </div>
            `
        }).join('')

        updateStats()
        updateUndoBtn()
    }

    function adjustQty(delta) {
        const current = parseInt(qtyInput.value, 10) || 1
        qtyInput.value = Math.max(1, current + delta)
        qtyInput.focus()
        qtyInput.select()
    }

    async function lookupBarcode(barcode) {
        if (!barcode || scanning) return

        const now = Date.now()
        if (barcode === lastScanCode && now - lastScanAt < 600) return
        lastScanCode = barcode
        lastScanAt = now

        scanning = true
        setStatus('Qidirilmoqda...', 'info')

        try {
            const url = `/inventory_lookup/?barcode=${encodeURIComponent(barcode)}&branch_id=${encodeURIComponent(branchId())}`
            const response = await fetch(url, { credentials: 'same-origin' })
            const data = await response.json()

            if (response.status === 404 && data.barcode) {
                showNewProductForm(data.barcode)
                setStatus(data.message || 'Yangi mahsulot — ma’lumotlarni to‘ldiring', 'info')
                playTone(false)
                return
            }

            if (!response.ok) {
                currentProduct = null
                productPanel.classList.add('hidden')
                setStatus(data.error || 'Mahsulot topilmadi', 'err')
                playTone(false)
                barcodeInput.focus()
                return
            }

            showExistingProduct(data)
            setStatus('Mahsulot topildi — narx/miqdorni tekshirib qo‘shing', 'ok')

            if (quickMode && quickMode.checked && !isNewProduct) {
                await saveProductAndStock()
            }
        } catch (err) {
            console.error(err)
            setStatus('Tarmoq xatosi', 'err')
            playTone(false)
        } finally {
            scanning = false
            barcodeInput.value = ''
            if (quickMode && quickMode.checked) barcodeInput.focus()
        }
    }

    async function saveProductAndStock() {
        const barcode = currentBarcode || (currentProduct && currentProduct.barcode)
        if (!barcode) {
            setStatus('Avval shtrix-kodni skanerlang', 'err')
            return null
        }

        const name = (productNameInput.value || '').trim()
        if (!name) {
            setStatus('Mahsulot nomi majburiy', 'err')
            productNameInput.focus()
            return null
        }

        const qty = parseInt(qtyInput.value, 10) || 0
        if (qty < 1) {
            setStatus('Miqdor kamida 1 bo‘lishi kerak', 'err')
            return null
        }

        if (!categorySelect.value) {
            setStatus('Kategoriya tanlang', 'err')
            return null
        }

        if (!supplierSelect.value) {
            setStatus('Yetkazib beruvchini tanlang', 'err')
            return null
        }

        const form = new FormData()
        form.append('barcode', barcode)
        form.append('product_name', name)
        form.append('category', categorySelect.value)
        form.append('supplier_id', supplierSelect.value)
        form.append('entry_currency', entryCurrency.value)
        form.append('store_currency', storeCurrency.value)
        form.append('cost_price', costPriceInput.value || '0')
        form.append('base_price', basePriceInput.value || '0')
        form.append('min_stock_level', minStockInput.value || '3')
        form.append('warranty_days', warrantyDaysInput ? warrantyDaysInput.value || '365' : '365')
        form.append('replacement_days', replacementDaysInput ? replacementDaysInput.value || '7' : '7')
        form.append('service_warranty_days', serviceWarrantyInput ? serviceWarrantyInput.value || '90' : '90')
        form.append('qty', String(qty))
        form.append('note', noteInput ? noteInput.value.trim() : '')
        form.append('branch_id', branchId())
        form.append('usd_rate', String(rate()))
        form.append('save_rate', '1')
        if (pendingImageFile) form.append('image', pendingImageFile)

        try {
            const response = await fetch('/inventory_product_save/', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'X-CSRFToken': csrfToken() },
                body: form,
            })
            const data = await response.json()
            if (!response.ok || !data.success) {
                setStatus(data.error || 'Saqlash amalga oshmadi', 'err')
                playTone(false)
                return null
            }

            isNewProduct = false
            currentProduct = {
                barcode: data.barcode,
                name: data.name,
                stock: data.stock,
                cost_price: data.cost_price,
                price: data.price,
                currency: data.currency,
                category: data.category,
                image: data.image,
                branch_name: data.branch_name,
                in_branch: true,
                is_low_stock: data.is_low_stock,
                min_stock_level: data.min_stock_level,
            }
            showExistingProduct(Object.assign({}, currentProduct, {
                supplier_id: supplierSelect.value,
            }))

            intakeLog.unshift(data)
            if (intakeLog.length > 50) intakeLog.pop()
            saveLog()
            renderLog()

            setStatus(data.message + (data.converted_hint ? ' · ' + data.converted_hint : ''), 'ok')
            playTone(true)
            qtyInput.value = 1
            if (noteInput) noteInput.value = ''
            pendingImageFile = null
            barcodeInput.focus()
            return data
        } catch (err) {
            console.error(err)
            setStatus('Tarmoq xatosi', 'err')
            playTone(false)
            return null
        }
    }

    async function stockInUndo(qty, options) {
        options = options || {}
        const payload = {
            barcode: options.barcode,
            qty: qty,
            branch_id: branchId(),
            note: options.note || 'Bekor qilindi',
            undo: true,
        }
        try {
            const response = await fetch('/inventory_stock_in/', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken(),
                },
                body: JSON.stringify(payload),
            })
            const data = await response.json()
            if (!response.ok || !data.success) {
                setStatus(data.error || 'Bekor qilib bo‘lmadi', 'err')
                playTone(false)
                return null
            }
            return data
        } catch (err) {
            setStatus('Tarmoq xatosi', 'err')
            return null
        }
    }

    async function undoLast() {
        const last = intakeLog[0]
        if (!last || last.qty_added <= 0 || last.undone) {
            setStatus('Bekor qilish uchun kirim yo‘q', 'err')
            return
        }
        const data = await stockInUndo(last.qty_added, { barcode: last.barcode })
        if (!data) return
        last.undone = true
        intakeLog.unshift({ ...data, name: last.name })
        if (intakeLog.length > 50) intakeLog.pop()
        saveLog()
        renderLog()
        setStatus(data.message, 'ok')
    }

    async function addCategory() {
        const name = prompt('Yangi kategoriya nomi:')
        if (!name || !name.trim()) return
        try {
            const response = await fetch('/inventory_add_category/', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken(),
                },
                body: JSON.stringify({ name: name.trim() }),
            })
            const data = await response.json()
            if (!response.ok || !data.success) {
                setStatus(data.error || 'Kategoriya qo‘shilmadi', 'err')
                return
            }
            categorySelect.innerHTML = ''
            ;(data.categories || []).forEach((c) => {
                const opt = document.createElement('option')
                opt.value = c
                opt.textContent = c
                categorySelect.appendChild(opt)
            })
            selectCategory(data.name)
            setStatus(data.message, 'ok')
        } catch (e) {
            setStatus('Tarmoq xatosi', 'err')
        }
    }

    async function saveRate() {
        try {
            const response = await fetch('/inventory_save_rate/', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken(),
                },
                body: JSON.stringify({ usd_rate: rate() }),
            })
            const data = await response.json()
            if (!response.ok || !data.success) {
                setStatus(data.error || 'Kurs saqlanmadi', 'err')
                return
            }
            usdRateInput.value = data.usd_rate
            updateConversionHints()
            setStatus(data.message, 'ok')
        } catch (e) {
            setStatus('Tarmoq xatosi', 'err')
        }
    }

    barcodeInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault()
            const code = barcodeInput.value.trim()
            if (code) lookupBarcode(code)
        }
    })

    ;[qtyInput, productNameInput, costPriceInput, basePriceInput, noteInput].forEach((el) => {
        if (!el) return
        el.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault()
                saveProductAndStock()
            }
        })
    })

    qtyInput.addEventListener('keydown', (e) => {
        if (e.key === '+' || e.key === '=') { e.preventDefault(); adjustQty(1) }
        else if (e.key === '-') { e.preventDefault(); adjustQty(-1) }
    })

    addBtn.addEventListener('click', () => saveProductAndStock())
    qtyMinus.addEventListener('click', () => adjustQty(-1))
    qtyPlus.addEventListener('click', () => adjustQty(1))
    undoBtn.addEventListener('click', () => undoLast())
    addCategoryBtn.addEventListener('click', () => addCategory())
    saveRateBtn.addEventListener('click', () => saveRate())
    newProductBtn.addEventListener('click', () => {
        const code = (barcodeInput.value || currentBarcode || '').trim()
        if (!code) {
            setStatus('Avval shtrix-kod kiriting', 'err')
            barcodeInput.focus()
            return
        }
        showNewProductForm(code)
        setStatus('Yangi mahsulot formasini to‘ldiring', 'info')
    })

    clearLogBtn.addEventListener('click', () => {
        if (!intakeLog.length) return
        if (!confirm('Oxirgi kirimlar ro‘yxatini tozalaysizmi? (ombor qoldig‘iga ta’sir qilmaydi)')) return
        intakeLog = []
        saveLog()
        renderLog()
        setStatus('Ro‘yxat tozalandi', 'info')
    })

    ;[entryCurrency, storeCurrency, costPriceInput, basePriceInput, usdRateInput].forEach((el) => {
        el.addEventListener('input', updateConversionHints)
        el.addEventListener('change', updateConversionHints)
    })

    imageInput.addEventListener('change', () => {
        const file = imageInput.files && imageInput.files[0]
        pendingImageFile = file || null
        if (file) {
            const url = URL.createObjectURL(file)
            setImagePreview(url)
        }
    })

    if (branchSelect && branchSelect.tagName === 'SELECT') {
        branchSelect.addEventListener('change', () => {
            currentProduct = null
            isNewProduct = false
            productPanel.classList.add('hidden')
            loadLog()
            setStatus('Filial o‘zgardi — qayta skanerlang', 'info')
            barcodeInput.focus()
        })
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            currentProduct = null
            isNewProduct = false
            currentBarcode = ''
            pendingImageFile = null
            productPanel.classList.add('hidden')
            barcodeInput.value = ''
            setStatus('Tozalandi — skanerlashga tayyor', 'info')
            barcodeInput.focus()
        }
    })

    try {
        const savedQuick = localStorage.getItem('ombor_kirim_quick')
        if (savedQuick === '1') quickMode.checked = true
    } catch (e) {}

    quickMode.addEventListener('change', () => {
        try {
            localStorage.setItem('ombor_kirim_quick', quickMode.checked ? '1' : '0')
        } catch (e) {}
        barcodeInput.focus()
    })

    updateConversionHints()
    loadLog()
    barcodeInput.focus()

    window.intakeLookupBarcode = lookupBarcode

    try {
        const key = (window.GlobalScanner && window.GlobalScanner.STORAGE_KEY) || 'pendingScanAction'
        const raw = sessionStorage.getItem(key)
        if (raw) {
            const data = JSON.parse(raw)
            if (data && data.type === 'ombor' && data.barcode) {
                sessionStorage.removeItem(key)
                setTimeout(() => lookupBarcode(data.barcode), 80)
            }
        }
    } catch (e) {
        console.error(e)
    }
})()
