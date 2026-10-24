let checkoutCurrency = 'UZS'

function normalizeCurrency(value) {
    const cur = String(value || 'UZS').trim().toUpperCase()
    return cur === 'USD' ? 'USD' : 'UZS'
}

function getVatPercent() {
    const n = parseFloat(typeof vatPercent !== 'undefined' ? vatPercent : 12)
    if (isNaN(n) || n < 0) return 0
    return Math.min(100, n)
}

function isVatEnabled() {
    return typeof vatEnabled === 'undefined' ? true : !!vatEnabled
}

function calcTax(subtotal) {
    if (!isVatEnabled()) return 0
    return (parseFloat(subtotal) || 0) * (getVatPercent() / 100)
}

function getCartCurrency() {
    if (!cart.length) return normalizeCurrency(checkoutCurrency)
    return normalizeCurrency(cart[0].currency)
}

const FRACTIONAL_UNITS = new Set(['m', 'kg', 'l', 'm2'])

function normalizeUnit(value) {
    const u = String(value || 'ta').trim().toLowerCase()
    return u || 'ta'
}

function isFractionalUnit(unit) {
    return FRACTIONAL_UNITS.has(normalizeUnit(unit))
}

function unitStep(unit) {
    return isFractionalUnit(unit) ? 0.1 : 1
}

function formatQty(qty, unit) {
    const n = parseFloat(qty)
    if (isNaN(n)) return '0'
    if (isFractionalUnit(unit)) {
        const rounded = Math.round(n * 1000) / 1000
        return String(rounded)
    }
    return String(Math.max(1, Math.round(n)))
}

function parseQtyValue(value, unit) {
    const n = parseFloat(String(value || '').replace(',', '.'))
    if (isNaN(n) || n <= 0) return null
    if (isFractionalUnit(unit)) {
        return Math.round(n * 1000) / 1000
    }
    return Math.max(1, Math.round(n))
}

function parseStockLimit(value) {
    if (value === null || value === undefined || value === '') return null
    const n = parseFloat(String(value).replace(',', '.'))
    return isNaN(n) ? null : Math.max(0, Math.round(n * 1000) / 1000)
}

function stockLimitMessage(stock, unit) {
    const u = normalizeUnit(unit)
    if (stock <= 0) return 'Mahsulot omborda tugagan'
    return `Omborda faqat ${formatQty(stock, u)} ${u} bor`
}

function syncCartStockFromGrid() {
    if (!Array.isArray(cart) || !cart.length) return
    const grid = document.getElementById('inventory-grid')
    if (!grid) return
    let changed = false
    cart.forEach((item) => {
        const card = grid.querySelector(`.product-card[data-id="${item.id}"]`)
        if (!card) return
        const stock = parseStockLimit(card.getAttribute('data-stock'))
        if (stock === null) return
        if (parseStockLimit(item.stock) !== stock) {
            item.stock = stock
            changed = true
        }
        const unit = normalizeUnit(item.unit)
        const qty = parseQtyValue(item.qty, unit) || unitStep(unit)
        if (stock > 0 && qty > stock) {
            item.qty = stock
            changed = true
        }
    })
    if (changed && typeof cartKey !== 'undefined') {
        localStorage.setItem(cartKey, JSON.stringify(cart))
    }
}

function selectProductFromCard(card) {
    if (!card || card.disabled) return

    const stock = parseStockLimit(card.getAttribute('data-stock'))
    const unit = normalizeUnit(card.getAttribute('data-unit'))
    if (stock !== null && stock <= 0) {
        alert(stockLimitMessage(stock, unit))
        return
    }

    const listPriceRaw = card.getAttribute('data-list-price')
    const salePct = parseFloat(card.getAttribute('data-sale-percent') || '0') || 0
    addItemToCart({
        id: parseInt(card.getAttribute('data-id'), 10),
        name: card.getAttribute('data-name') || '',
        price: parseFloat(card.getAttribute('data-price')),
        listPrice: listPriceRaw != null && listPriceRaw !== '' ? parseFloat(listPriceRaw) : undefined,
        saleDiscountPercent: salePct,
        currency: normalizeCurrency(card.getAttribute('data-currency')),
        unit: unit,
        qty: isFractionalUnit(unit) ? 1 : 1,
        img: card.getAttribute('data-image') || '',
        stock: stock,
    })
}

function getCartTotalsByCurrency() {
    const totals = { UZS: 0, USD: 0 }
    cart.forEach((item) => {
        const cur = normalizeCurrency(item.currency)
        const unit = normalizeUnit(item.unit)
        const qty = parseQtyValue(item.qty, unit) || unitStep(unit)
        totals[cur] += (parseFloat(item.price) || 0) * qty
    })
    return totals
}

function isPosMobileLayout() {
    return window.matchMedia('(max-width: 1023px)').matches
}

function syncMobileCartBar() {
    const countEl = document.getElementById('pos-mobile-count')
    const totalEl = document.getElementById('pos-mobile-total')
    const payBtn = document.getElementById('pos-mobile-pay')
    const openBtn = document.getElementById('pos-mobile-open')
    const count = (cart || []).reduce((n, item) => {
        const unit = normalizeUnit(item.unit)
        return n + (parseQtyValue(item.qty, unit) || 0)
    }, 0)
    const countLabel = Number.isInteger(count) ? String(count) : String(Math.round(count * 1000) / 1000)
    if (countEl) countEl.textContent = countLabel
    if (payBtn) payBtn.disabled = count === 0
    if (openBtn) openBtn.setAttribute('aria-expanded', document.body.classList.contains('pos-cart-open') ? 'true' : 'false')

    const totals = typeof getCartTotalsByCurrency === 'function'
        ? getCartTotalsByCurrency()
        : (currentTotalsByCurrency || { UZS: 0, USD: 0 })
    const uzs = (totals.UZS || 0) + (typeof calcTax === 'function' ? calcTax(totals.UZS || 0) : 0)
    const usd = (totals.USD || 0) + (typeof calcTax === 'function' ? calcTax(totals.USD || 0) : 0)
    let label = '0'
    if (uzs > 0 && usd > 0) label = `${formatMoney(uzs, 'UZS')} + ${formatMoney(usd, 'USD')}`
    else if (usd > 0) label = formatMoney(usd, 'USD')
    else label = formatMoney(uzs, 'UZS')
    if (totalEl) totalEl.textContent = label
}

function setMobileCartOpen(open) {
    const panel = document.getElementById('pos-cart-panel')
    const backdrop = document.getElementById('pos-cart-backdrop')
    const openBtn = document.getElementById('pos-mobile-open')
    if (!panel) return
    if (!isPosMobileLayout()) {
        panel.classList.remove('translate-y-[110%]', 'pos-cart-open')
        if (backdrop) {
            backdrop.classList.add('opacity-0', 'pointer-events-none')
            backdrop.setAttribute('aria-hidden', 'true')
        }
        document.body.classList.remove('pos-cart-open')
        if (openBtn) openBtn.setAttribute('aria-expanded', 'false')
        return
    }
    if (open) {
        panel.classList.remove('translate-y-[110%]')
        panel.classList.add('pos-cart-open')
        if (backdrop) {
            backdrop.classList.remove('opacity-0', 'pointer-events-none')
            backdrop.setAttribute('aria-hidden', 'false')
        }
        document.body.classList.add('pos-cart-open')
        if (openBtn) openBtn.setAttribute('aria-expanded', 'true')
    } else {
        panel.classList.add('translate-y-[110%]')
        panel.classList.remove('pos-cart-open')
        if (backdrop) {
            backdrop.classList.add('opacity-0', 'pointer-events-none')
            backdrop.setAttribute('aria-hidden', 'true')
        }
        document.body.classList.remove('pos-cart-open')
        if (openBtn) openBtn.setAttribute('aria-expanded', 'false')
    }
}

function renderCart(){
    const cartContainer = document.getElementById('cart-items')
    const totalContainer = document.getElementById('total-container')

    if (!cartContainer) return

    cartContainer.innerHTML = ''
    if (totalContainer) totalContainer.innerHTML = ''
    currentGrandTotal = 0
    currentTotalsByCurrency = { UZS: 0, USD: 0 }

    if (cart.length === 0){
        cartContainer.innerHTML = "<p class=\"text-sky-600/70 text-center text-sm py-10\">Savat bo‘sh</p>";
        if (totalContainer) totalContainer.innerHTML = ''
        currentGrandTotal = 0
        renderHeldOrders()
        syncMobileCartBar()
        return;
    }

    cart.forEach(item => {
        item.currency = normalizeCurrency(item.currency)
        item.unit = normalizeUnit(item.unit)
        const step = unitStep(item.unit)
        let qty = parseQtyValue(item.qty, item.unit) || step
        const stock = parseStockLimit(item.stock)
        if (stock !== null && qty > stock) {
            qty = Math.max(step, stock)
            item.qty = qty
        } else {
            item.qty = qty
        }
        const atStockLimit = stock !== null && qty >= stock
        if (item.originalPrice == null || item.originalPrice === '') {
            item.originalPrice = parseFloat(item.price) || 0
        }
        let subTotal = item.price * qty
        const adjustedBadge = item.priceAdjusted
            ? '<span class="ml-1 inline-flex px-1.5 py-0.5 rounded text-[9px] font-bold bg-violet-100 text-violet-800">o‘zgartirilgan</span>'
            : ''
        const salePct = parseFloat(item.saleDiscountPercent || 0) || 0
        const listP = parseFloat(item.originalPrice)
        const unitP = parseFloat(item.price) || 0
        const saleBadge = (!item.priceAdjusted && salePct > 0)
            ? `<span class="ml-1 inline-flex px-1.5 py-0.5 rounded text-[9px] font-bold bg-rose-100 text-rose-800">−${Math.round(salePct)}%</span>`
            : ''
        const priceLine = (!item.priceAdjusted && listP > unitP)
            ? `<span class="line-through text-sky-400 mr-1">${formatMoney(listP, item.currency)}</span>${formatMoney(unitP, item.currency)}`
            : formatMoney(unitP, item.currency)
        const imgHtml = item.img
            ? `<img src="${item.img}" class="h-12 w-12 object-cover rounded-md border border-sky-200 bg-white">`
            : `<div class="h-12 w-12 rounded-md border border-sky-200 bg-white flex items-center justify-center text-xs text-sky-400 font-semibold">N/A</div>`
        const qtyStepAttr = isFractionalUnit(item.unit) ? '0.001' : '1'
        const qtyMinAttr = isFractionalUnit(item.unit) ? '0.001' : '1'

        cartContainer.innerHTML += `
                    <div class="flex items-center gap-3 bg-white/90 p-2.5 rounded-xl border border-sky-200 shadow-sm">
                        ${imgHtml}
                        <div class="flex-grow min-w-0">
                            <h4 class="font-semibold text-sm text-sky-950 truncate">${item.name}${adjustedBadge}${saleBadge}</h4>
                            <p class="text-xs text-sky-700/70">${priceLine} / ${item.unit}${stock !== null ? ` · max ${formatQty(stock, item.unit)} ${item.unit}` : ''}</p>
                            <div class="flex items-center gap-1.5 mt-1.5">
                                <button type="button" onclick="changeCartQty(${item.id}, -1)"
                                        class="w-9 h-10 rounded-lg border border-sky-200 bg-sky-50 text-sky-800 text-lg font-bold hover:bg-sky-100 touch-manipulation shrink-0">-</button>
                                <input type="number" inputmode="decimal"
                                       value="${formatQty(qty, item.unit)}"
                                       min="${qtyMinAttr}" step="${qtyStepAttr}"
                                       ${stock !== null ? `max="${stock}"` : ''}
                                       onchange="setCartQty(${item.id}, this.value)"
                                       onkeydown="if(event.key==='Enter'){event.preventDefault();this.blur();}"
                                       class="w-16 h-10 px-1 text-center rounded-lg border border-sky-300 text-sky-950 font-semibold text-sm bg-white focus:ring-2 focus:ring-sky-400 outline-none"
                                       aria-label="Miqdor (${item.unit})" title="Miqdorni yozing (${item.unit})">
                                <span class="text-xs font-semibold text-sky-700 shrink-0">${item.unit}</span>
                                <button type="button" onclick="changeCartQty(${item.id}, 1)"
                                        class="w-9 h-10 rounded-lg border border-sky-200 bg-sky-50 text-sky-800 text-lg font-bold hover:bg-sky-100 touch-manipulation disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                                        ${atStockLimit ? 'disabled' : ''}>+</button>
                            </div>
                        </div>
                        <div class="self-stretch flex flex-col items-end justify-between shrink-0">
                            <p class="font-bold text-sm text-sky-900">${formatMoney(subTotal, item.currency)}</p>
                            <div class="flex items-center gap-1">
                                <button type="button" onclick="editCartItemPrice(${item.id})"
                                        class="w-10 h-10 inline-flex items-center justify-center rounded-lg text-sky-700 hover:text-sky-900 hover:bg-sky-100 transition-colors touch-manipulation"
                                        title="Narxni tahrirlash" aria-label="Narxni tahrirlash">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                        <path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125" />
                                    </svg>
                                </button>
                                <button type="button" onclick="removeFromCart(${item.id})"
                                        class="w-10 h-10 inline-flex items-center justify-center rounded-lg text-red-600 hover:text-red-700 hover:bg-red-50 transition-colors text-2xl font-black leading-none touch-manipulation"
                                        title="O‘chirish" aria-label="O‘chirish">
                                    &times;
                                </button>
                            </div>
                        </div>
                    </div>
                    `
    })

    currentTotalsByCurrency = getCartTotalsByCurrency()
    const activeCurrency = normalizeCurrency(checkoutCurrency || getCartCurrency())
    const subtotal = currentTotalsByCurrency[activeCurrency] || 0
    const tax = calcTax(subtotal)
    currentGrandTotal = subtotal + tax

    if (totalContainer) {
        const uzsSub = currentTotalsByCurrency.UZS || 0
        const usdSub = currentTotalsByCurrency.USD || 0
        const uzsTax = calcTax(uzsSub)
        const usdTax = calcTax(usdSub)
        const uzsTotal = uzsSub + uzsTax
        const usdTotal = usdSub + usdTax
        const pct = getVatPercent()
        const enabled = isVatEnabled()

        let html = '<div class="space-y-1.5">'
        if (uzsSub > 0) {
            html += `
                <div class="flex justify-between items-baseline gap-2">
                    <span class="text-xs font-semibold text-sky-700/80">Jami so‘m</span>
                    <span class="text-sm font-semibold text-sky-900">${formatMoney(uzsSub, 'UZS')}</span>
                </div>
                <div class="flex justify-between items-baseline gap-2">
                    <span class="text-xs font-semibold text-sky-700/80">QQS${enabled ? ` (${pct}%)` : ' (o‘chiq)'}</span>
                    <span class="text-sm font-semibold text-sky-800">${formatMoney(uzsTax, 'UZS')}</span>
                </div>
                <div class="flex justify-between items-baseline gap-2 pt-1 border-t border-sky-200">
                    <span class="text-xs font-bold text-sky-900">Umumiy so‘m</span>
                    <span class="text-base font-bold text-sky-950" id="total-display">${formatMoney(uzsTotal, 'UZS')}</span>
                </div>`
        }
        if (usdSub > 0) {
            html += `
                <div class="flex justify-between items-baseline gap-2 ${uzsSub > 0 ? 'pt-2 mt-1 border-t border-sky-200/70' : ''}">
                    <span class="text-xs font-semibold text-sky-700/80">Jami dollar</span>
                    <span class="text-sm font-semibold text-emerald-800">${formatMoney(usdSub, 'USD')}</span>
                </div>
                <div class="flex justify-between items-baseline gap-2">
                    <span class="text-xs font-semibold text-sky-700/80">QQS${enabled ? ` (${pct}%)` : ' (o‘chiq)'}</span>
                    <span class="text-sm font-semibold text-emerald-700">${formatMoney(usdTax, 'USD')}</span>
                </div>
                <div class="flex justify-between items-baseline gap-2 pt-1 border-t border-sky-200">
                    <span class="text-xs font-bold text-sky-900">Umumiy dollar</span>
                    <span class="text-base font-bold text-emerald-800" ${!uzsSub ? 'id="total-display"' : ''}>${formatMoney(usdTotal, 'USD')}</span>
                </div>`
        }
        html += '</div>'
        totalContainer.innerHTML = html
    }

    renderHeldOrders()
    syncMobileCartBar()
}

function editCartItemPrice(id) {
    const item = cart.find((i) => i.id === id)
    if (!item) return
    item.unit = normalizeUnit(item.unit)
    const qty = parseQtyValue(item.qty, item.unit) || unitStep(item.unit)
    const cur = normalizeCurrency(item.currency)
    const currentLine = (parseFloat(item.price) || 0) * qty
    const raw = prompt(
        `«${item.name}» uchun yangi jami summa (${cur === 'USD' ? 'USD' : 'so‘m'}, ${formatQty(qty, item.unit)} ${item.unit}):`,
        String(currentLine)
    )
    if (raw === null) return
    const cleaned = String(raw).replace(/\s/g, '').replace(',', '.')
    const lineTotal = parseFloat(cleaned)
    if (!isFinite(lineTotal) || lineTotal < 0) {
        alert('Noto‘g‘ri summa')
        return
    }
    if (item.originalPrice === undefined || item.originalPrice === null) {
        item.originalPrice = parseFloat(item.price) || 0
    }
    item.price = Math.round((lineTotal / qty) * 100) / 100
    item.priceAdjusted = true
    localStorage.setItem(cartKey, JSON.stringify(cart))
    renderCart()
}

function addItemToCart(scannedItem) {
    if (!scannedItem || !scannedItem.id || isNaN(scannedItem.price)){
        console.error("Scanned Item is invalid");
        return
    }

    cart.forEach((item) => {
        item.currency = normalizeCurrency(item.currency)
        item.unit = normalizeUnit(item.unit)
    })

    const itemCurrency = normalizeCurrency(scannedItem.currency)
    const itemUnit = normalizeUnit(scannedItem.unit)
    const step = unitStep(itemUnit)
    const qtyToAdd = parseQtyValue(scannedItem.qty, itemUnit) || step
    const itemExist = cart.find(item => item.id === scannedItem.id)
    const stock = parseStockLimit(
        scannedItem.stock !== undefined && scannedItem.stock !== null
            ? scannedItem.stock
            : (itemExist ? itemExist.stock : null)
    )

    if (stock !== null && stock <= 0) {
        alert(stockLimitMessage(stock, itemUnit))
        return
    }

    if (itemExist) {
        const currentQty = parseQtyValue(itemExist.qty, itemExist.unit || itemUnit) || 0
        if (stock !== null) itemExist.stock = stock
        if (!itemExist.unit) itemExist.unit = itemUnit
        const limit = parseStockLimit(itemExist.stock)
        if (limit !== null && currentQty + qtyToAdd > limit) {
            if (currentQty >= limit) {
                alert(stockLimitMessage(limit, itemExist.unit))
                return
            }
            itemExist.qty = limit
            itemExist.currency = itemCurrency
            alert(stockLimitMessage(limit, itemExist.unit))
        } else {
            itemExist.qty = Math.round((currentQty + qtyToAdd) * 1000) / 1000
            itemExist.currency = itemCurrency
        }
    } else {
        const unitPrice = parseFloat(scannedItem.price)
        const listPrice = parseFloat(
            scannedItem.listPrice != null ? scannedItem.listPrice
                : (scannedItem.list_price != null ? scannedItem.list_price : unitPrice)
        )
        const pushQty = (stock !== null && qtyToAdd > stock) ? stock : qtyToAdd
        if (stock !== null && qtyToAdd > stock) {
            alert(stockLimitMessage(stock, itemUnit))
        }
        cart.push({
            ...scannedItem,
            unit: itemUnit,
            qty: pushQty,
            price: unitPrice,
            originalPrice: !isNaN(listPrice) ? listPrice : unitPrice,
            priceAdjusted: false,
            saleDiscountPercent: parseFloat(scannedItem.saleDiscountPercent || scannedItem.sale_discount_percent || 0) || 0,
            currency: itemCurrency,
            stock: stock,
        })
    }

    if (!cart.some((item) => normalizeCurrency(item.currency) === normalizeCurrency(checkoutCurrency))) {
        checkoutCurrency = itemCurrency
    }

    localStorage.setItem(cartKey, JSON.stringify(cart))
    renderCart()
}

function saveHeldOrders() {
    localStorage.setItem(heldOrdersKey, JSON.stringify(heldOrders))
}

function holdCurrentOrder() {
    if (!cart.length) {
        alert('Zahiralash uchun savatda mahsulot bo‘lishi kerak')
        return
    }

    const label = prompt('Zahira nomi / mijoz (ixtiyoriy):', 'Mijoz ' + (heldOrders.length + 1))
    if (label === null) return

    const held = {
        id: Date.now(),
        label: (label || '').trim() || ('Mijoz ' + (heldOrders.length + 1)),
        cart: JSON.parse(JSON.stringify(cart)),
        createdAt: new Date().toISOString(),
    }

    heldOrders.unshift(held)
    saveHeldOrders()

    cart.length = 0
    localStorage.removeItem(cartKey)
    checkoutCurrency = 'UZS'
    renderCart()
    renderHeldOrders()
}

async function reserveCurrentOrder() {
    if (!cart.length) {
        alert('Bronlash uchun savatda mahsulot bo‘lishi kerak')
        return
    }
    const name = prompt('Mijoz nomi (majburiy):', '')
    if (name === null) return
    const customerName = (name || '').trim()
    if (!customerName) {
        alert('Bronlash uchun mijoz nomi majburiy')
        return
    }
    const phone = (prompt('Telefon (ixtiyoriy):', '') || '').trim()
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
    if (!csrfToken) {
        alert('CSRF token topilmadi — sahifani yangilang')
        return
    }
    const btn = document.getElementById('reserve-order-btn')
    if (btn) btn.disabled = true
    try {
        const response = await fetch('/checkout/reserve/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify({
                cart: cart.map((item) => ({
                    id: item.id,
                    qty: item.qty,
                    price: item.price,
                    currency: normalizeCurrency(item.currency),
                    name: item.name,
                })),
                customerName,
                phone,
                currency: getCartCurrency(),
            }),
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok || !data.success) {
            alert(data.message || 'Bronlash muvaffaqiyatsiz')
            return
        }
        cart.length = 0
        localStorage.removeItem(cartKey)
        checkoutCurrency = 'UZS'
        renderCart()
        await loadReservedOrders()
        alert(data.message || 'Mahsulotlar bronlandi')
    } catch (err) {
        alert('Bronlashda xatolik: ' + (err.message || err))
    } finally {
        if (btn) btn.disabled = false
    }
}

async function loadReservedOrders() {
    const badge = document.getElementById('reserve-count-badge')
    const list = document.getElementById('reserved-orders-list')
    if (!badge && !list) return
    try {
        const response = await fetch('/api/reservations/active/')
        const data = await response.json().catch(() => ({}))
        window._activeReservations = Array.isArray(data.reservations) ? data.reservations : []
        renderReservedOrders()
    } catch (err) {
        window._activeReservations = []
        renderReservedOrders()
    }
}

function toggleReservedOrdersDropdown(forceOpen) {
    const dropdown = document.getElementById('reserved-orders-dropdown')
    if (!dropdown) return
    const rows = window._activeReservations || []
    if (!rows.length) {
        dropdown.classList.add('hidden')
        return
    }
    const open = typeof forceOpen === 'boolean' ? forceOpen : dropdown.classList.contains('hidden')
    dropdown.classList.toggle('hidden', !open)
}

async function cancelReservation(reservationId, event) {
    if (event) {
        event.preventDefault()
        event.stopPropagation()
    }
    if (!confirm('Bron bekor qilinsinmi? Ombordagi ushlab turilgan qoldiq qaytariladi.')) return
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
    try {
        const response = await fetch(`/reservations/${reservationId}/cancel/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok || !data.success) {
            alert(data.message || 'Bron bekor qilinmadi')
            return
        }
        await loadReservedOrders()
        if (typeof syncCartStockFromGrid === 'function') syncCartStockFromGrid()
    } catch (err) {
        alert('Xatolik: ' + (err.message || err))
    }
}

async function openReservationToCart(reservationId) {
    if (cart.length) {
        const ok = confirm(
            'Hozirgi savat o‘chirilib, bron savatga yuklanadi. Davom etasizmi?'
        )
        if (!ok) return
    }
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
    try {
        const response = await fetch(`/reservations/${reservationId}/to_cart/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        })
        const data = await response.json().catch(() => ({}))
        if (!response.ok || !data.success) {
            alert(data.message || 'Bron savatga yuklanmadi')
            return
        }
        const lines = Array.isArray(data.cart) ? data.cart : []
        cart = lines.map((item) => ({
            id: item.id,
            name: item.name,
            price: parseFloat(item.price) || 0,
            originalPrice: parseFloat(item.originalPrice != null ? item.originalPrice : item.price) || 0,
            priceAdjusted: !!item.priceAdjusted,
            currency: normalizeCurrency(item.currency),
            qty: parseInt(item.qty, 10) || 1,
            img: item.img || '',
            stock: parseInt(item.stock, 10) || (parseInt(item.qty, 10) || 1),
        }))
        localStorage.setItem(cartKey, JSON.stringify(cart))
        checkoutCurrency = getCartCurrency()
        renderCart()
        toggleReservedOrdersDropdown(false)
        await loadReservedOrders()
        if (typeof syncCartStockFromGrid === 'function') syncCartStockFromGrid()
    } catch (err) {
        alert('Xatolik: ' + (err.message || err))
    }
}

function formatReserveMoney(amount, currency) {
    const cur = normalizeCurrency(currency)
    const n = Number(amount) || 0
    if (cur === 'USD') return '$' + n.toFixed(2)
    return Math.round(n).toLocaleString('uz-UZ') + ' so‘m'
}

function renderReservedOrders() {
    const badge = document.getElementById('reserve-count-badge')
    const list = document.getElementById('reserved-orders-list')
    const dropdown = document.getElementById('reserved-orders-dropdown')
    const rows = window._activeReservations || []

    if (badge) {
        if (rows.length) {
            badge.textContent = String(rows.length)
            badge.classList.remove('hidden')
        } else {
            badge.textContent = '0'
            badge.classList.add('hidden')
            if (dropdown) dropdown.classList.add('hidden')
        }
    }

    if (!list) return
    if (!rows.length) {
        list.innerHTML = '<p class="text-xs text-gray-500 px-2 py-3 text-center">Faol bron yo‘q</p>'
        return
    }

    list.innerHTML = rows.map((row) => {
        const names = (row.items || []).slice(0, 2).map((i) => i.name).filter(Boolean).join(', ')
        const more = (row.items || []).length > 2 ? ` +${(row.items || []).length - 2}` : ''
        const time = row.created_at
            ? new Date(row.created_at).toLocaleString('uz-UZ', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
            : ''
        return `
            <div class="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-2 shadow-sm">
                <button type="button" onclick="openReservationToCart(${row.id})"
                        class="flex-grow text-left min-w-0 touch-manipulation">
                    <p class="font-semibold text-sm text-amber-950 truncate">${escapeHtml(row.customer_name)}</p>
                    <p class="text-[10px] text-amber-800 truncate">${row.unit_count || 0} dona · ${escapeHtml(formatReserveMoney(row.total_amount, row.currency))}${time ? ' · ' + time : ''}</p>
                    ${names ? `<p class="text-[10px] text-amber-700/80 truncate mt-0.5">${escapeHtml(names)}${more}</p>` : ''}
                </button>
                <button type="button" onclick="cancelReservation(${row.id}, event)"
                        class="shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-md border border-red-200 text-red-600 bg-white hover:bg-red-600 hover:text-white transition touch-manipulation"
                        title="Bekor qilish" aria-label="Bekor qilish">&times;</button>
            </div>
        `
    }).join('')
}

function restoreHeldOrder(heldId) {
    const held = heldOrders.find((h) => String(h.id) === String(heldId))
    if (!held) return

    if (cart.length) {
        const ok = confirm(
            'Hozirgi savatni zahiralab, tanlangan buyurtmani ochishni xohlaysizmi?\n' +
            '(Bekor qilsangiz — hozirgi savat o‘chiriladi)'
        )
        if (ok) {
            heldOrders.unshift({
                id: Date.now(),
                label: 'Vaqtinchalik savat',
                cart: JSON.parse(JSON.stringify(cart)),
                createdAt: new Date().toISOString(),
            })
        }
    }

    cart = JSON.parse(JSON.stringify(held.cart || []))
    cart.forEach((item) => { item.currency = normalizeCurrency(item.currency) })
    heldOrders = heldOrders.filter((h) => String(h.id) !== String(heldId))
    saveHeldOrders()
    localStorage.setItem(cartKey, JSON.stringify(cart))
    checkoutCurrency = getCartCurrency()
    renderCart()
    renderHeldOrders()
}

function deleteHeldOrder(heldId) {
    const held = heldOrders.find((h) => String(h.id) === String(heldId))
    const label = held ? held.label : 'buyurtma'
    if (!confirm(`«${label}» zahirasini o‘chirasizmi?`)) return

    heldOrders = heldOrders.filter((h) => String(h.id) !== String(heldId))
    saveHeldOrders()
    renderHeldOrders()
}

function heldOrderTotals(held) {
    const totals = { UZS: 0, USD: 0 }
    ;(held.cart || []).forEach((item) => {
        const cur = normalizeCurrency(item.currency)
        const qty = parseInt(item.qty, 10) || 1
        const price = parseFloat(item.price) || 0
        totals[cur] += price * qty
    })
    return totals
}

function formatHeldTotal(totals) {
    const parts = []
    if (totals.UZS > 0) parts.push(Math.round(totals.UZS).toLocaleString('uz-UZ') + ' so‘m')
    if (totals.USD > 0) parts.push('$' + totals.USD.toFixed(2))
    return parts.join(' · ') || '0 so‘m'
}

function escapeHtml(text) {
    return String(text || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
}

function renderHeldOrders() {
    const panel = document.getElementById('held-orders-panel')
    const list = document.getElementById('held-orders-list')
    const countEl = document.getElementById('held-orders-count')
    if (!panel || !list) return

    if (!heldOrders.length) {
        panel.classList.add('hidden')
        list.innerHTML = ''
        if (countEl) countEl.textContent = ''
        return
    }

    panel.classList.remove('hidden')
    if (countEl) countEl.textContent = String(heldOrders.length)

    list.innerHTML = heldOrders.map((held) => {
        const count = (held.cart || []).reduce((sum, item) => sum + (parseInt(item.qty, 10) || 1), 0)
        const time = held.createdAt
            ? new Date(held.createdAt).toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' })
            : ''
        const totalLabel = formatHeldTotal(heldOrderTotals(held))
        const names = (held.cart || []).slice(0, 2).map((i) => i.name).filter(Boolean).join(', ')
        const more = (held.cart || []).length > 2 ? ` +${(held.cart || []).length - 2}` : ''
        return `
            <div class="flex items-center gap-2 bg-white/90 border border-sky-300 rounded-lg px-3 py-2.5 shadow-sm">
                <button type="button" onclick="restoreHeldOrder(${held.id})"
                        class="flex-grow text-left min-w-0 touch-manipulation">
                    <p class="font-semibold text-sm text-sky-950 truncate">${escapeHtml(held.label)}</p>
                    <p class="text-[10px] text-sky-700 truncate">${count} dona · ${escapeHtml(totalLabel)}${time ? ' · ' + time : ''}</p>
                    ${names ? `<p class="text-[10px] text-sky-600/80 truncate mt-0.5">${escapeHtml(names)}${more}</p>` : ''}
                </button>
                <button type="button" onclick="deleteHeldOrder(${held.id})"
                        class="shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-md border border-red-200 text-red-600 bg-red-50 hover:bg-red-600 hover:text-white transition touch-manipulation"
                        title="O‘chirish" aria-label="O‘chirish">&times;</button>
            </div>
        `
    }).join('')
}

function changeCartQty(id, delta) {
    const item = cart.find(i => i.id === id)
    if (!item) return

    item.unit = normalizeUnit(item.unit)
    const step = unitStep(item.unit)
    const current = parseQtyValue(item.qty, item.unit) || step
    const next = Math.round((current + delta * step) * 1000) / 1000
    const minQty = isFractionalUnit(item.unit) ? 0.001 : 1
    if (next < minQty) {
        removeFromCart(id)
        return
    }

    const stock = parseStockLimit(item.stock)
    if (delta > 0 && stock !== null && next > stock) {
        alert(stockLimitMessage(stock, item.unit))
        return
    }

    item.qty = next
    localStorage.setItem(cartKey, JSON.stringify(cart))
    renderCart()
}

function setCartQty(id, value) {
    const item = cart.find(i => i.id === id)
    if (!item) return

    item.unit = normalizeUnit(item.unit)
    let next = parseQtyValue(value, item.unit)
    if (next === null) {
        removeFromCart(id)
        return
    }

    const stock = parseStockLimit(item.stock)
    if (stock !== null && next > stock) {
        next = stock
        alert(stockLimitMessage(stock, item.unit))
    }

    item.qty = next
    localStorage.setItem(cartKey, JSON.stringify(cart))
    renderCart()
}

function removeFromCart(id){
    cart = cart.filter(item => item.id !== id)

    localStorage.setItem(cartKey, JSON.stringify(cart))

    renderCart();
}

function syncCashCurrencyUI() {
    const cur = checkoutCurrency || getCartCurrency()
    const currencies = [...new Set(cart.map((item) => normalizeCurrency(item.currency)))]
    const picker = document.getElementById('cash-currency-picker')
    if (picker) {
        if (currencies.length > 1) picker.classList.remove('hidden')
        else picker.classList.add('hidden')
    }
    const label = document.getElementById('cash-currency-label')
    const uzsBtn = document.getElementById('cash-currency-uzs')
    const usdBtn = document.getElementById('cash-currency-usd')
    if (label) label.textContent = cur === 'USD' ? '$' : 'so‘m'
    if (uzsBtn && usdBtn) {
        const on = 'flex-1 py-2.5 rounded-lg text-sm font-semibold bg-blue-600 text-white touch-manipulation'
        const off = 'flex-1 py-2.5 rounded-lg text-sm font-semibold bg-gray-100 text-gray-600 touch-manipulation'
        if (cur === 'USD') {
            usdBtn.className = on
            uzsBtn.className = off
        } else {
            uzsBtn.className = on
            usdBtn.className = off
        }
    }
    syncCheckoutPriceDisplays()
    calculateChange()
}

function syncCheckoutPriceDisplays() {
    const cur = checkoutCurrency || getCartCurrency()
    const totalText = formatMoney(currentGrandTotal, cur)
    ;['cash-modal-price', 'cash-modal-price-mobile', 'cash-modal-price-foot'].forEach((id) => {
        const el = document.getElementById(id)
        if (el) el.textContent = totalText
    })
    const checkoutCart = typeof getCheckoutCart === 'function' ? getCheckoutCart() : []
    const count = checkoutCart.reduce((n, item) => n + (parseInt(item.qty, 10) || 1), 0)
    const countEl = document.getElementById('cash-modal-items-count')
    if (countEl) countEl.textContent = `${count} ta`
    const itemsSummary = document.getElementById('cash-items-summary')
    if (itemsSummary) itemsSummary.textContent = `${checkoutCart.length} tur · ${count} ta`
}

function renderCheckoutCartRows(targetIds) {
    const checkoutCart = getCheckoutCart()
    const cartRows = checkoutCart.map((item) => `
                <div class="flex flex-row items-center justify-between border-b border-gray-100 p-2 gap-3">
                    <div class="text-left flex-grow min-w-0">
                        <p class="text-sm font-bold text-gray-900 truncate">${item.name}</p>
                        <p class="text-xs text-gray-500">Miqdor: ${item.qty}</p>
                        <p class="text-xs font-bold text-blue-700">${formatMoney(item.price * item.qty, item.currency)}</p>
                    </div>
                    <div class="flex-shrink-0">
                        ${item.img
                            ? `<img src="${item.img}" class="h-12 w-12 object-cover rounded-md border border-gray-200">`
                            : `<div class="h-12 w-12 rounded-md bg-gray-50 border border-gray-200 flex items-center justify-center text-xs text-gray-400 font-semibold">N/A</div>`}
                    </div>
                </div>
                `).join('')
    ;(targetIds || ['cash-modal-image', 'cash-modal-image-mobile']).forEach((id) => {
        const el = document.getElementById(id)
        if (el) el.innerHTML = cartRows || '<p class="text-sm text-gray-400 text-center py-4">Bo‘sh</p>'
    })
}

function getQuickCashSuggestions(total, currency) {
    const cur = normalizeCurrency(currency)
    const t = Math.max(0, parseFloat(total) || 0)
    if (t <= 0) return []
    const roundUp = (n, step) => Math.ceil(n / step) * step
    const vals = new Set([t])
    if (cur === 'USD') {
        ;[1, 5, 10, 20, 50, 100].forEach((step) => {
            const v = roundUp(t, step)
            if (v > t) vals.add(v)
        })
    } else {
        ;[1000, 5000, 10000, 50000, 100000].forEach((step) => {
            const v = roundUp(t, step)
            if (v > t) vals.add(v)
        })
    }
    return [...vals].sort((a, b) => a - b).slice(0, 4)
}

function renderQuickCashAmounts() {
    const wrap = document.getElementById('cash-quick-amounts')
    if (!wrap) return
    const cur = checkoutCurrency || getCartCurrency()
    const suggestions = getQuickCashSuggestions(currentGrandTotal, cur)
    wrap.innerHTML = suggestions.map((amount) => {
        const label = cur === 'USD'
            ? (Number.isInteger(amount) ? String(amount) : String(Math.round(amount * 100) / 100))
            : String(Math.round(amount)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
        return `<button type="button" data-cash-amount="${amount}" class="touch-manipulation">${label}</button>`
    }).join('')
}

function setCashReceivedAmount(amount) {
    const input = document.getElementById('cash-received-input')
    if (!input) return
    const n = parseFloat(amount)
    if (!isFinite(n) || n < 0) return
    input.value = String(n)
    if (typeof onCashReceivedInput === 'function') onCashReceivedInput()
    else calculateChange()
}

function setExactCashAmount() {
    setCashReceivedAmount(currentGrandTotal || getCheckoutTotal())
}

function getCheckoutCart() {
    const cur = normalizeCurrency(checkoutCurrency || getCartCurrency())
    return cart.filter((item) => normalizeCurrency(item.currency) === cur)
}

let checkoutDiscountPercent = 0
let checkoutMarkupPercent = 0
let loyaltyDiscountPercent = 0
let secretDiscountActive = false
let secretMarkupActive = false

function syncCheckoutDiscountPercent() {
    const secretPct = secretDiscountActive
        ? Math.min(100, Math.max(0, parseFloat(typeof SECRET_DISCOUNT_PERCENT !== 'undefined' ? SECRET_DISCOUNT_PERCENT : 0) || 0))
        : 0
    const loyaltyPct = Math.min(100, Math.max(0, parseFloat(loyaltyDiscountPercent) || 0))
    checkoutDiscountPercent = secretMarkupActive ? 0 : Math.max(loyaltyPct, secretPct)
    checkoutMarkupPercent = secretMarkupActive
        ? Math.min(1000, Math.max(0, parseFloat(typeof SECRET_MARKUP_PERCENT !== 'undefined' ? SECRET_MARKUP_PERCENT : 0) || 0))
        : 0
}

function getActiveSecretCode() {
    if (secretMarkupActive) {
        return (typeof SECRET_MARKUP_CODE !== 'undefined' ? SECRET_MARKUP_CODE : '') || ''
    }
    if (secretDiscountActive) {
        return (typeof SECRET_DISCOUNT_CODE !== 'undefined' ? SECRET_DISCOUNT_CODE : '') || ''
    }
    return ''
}

function normalizeSecretCode(value) {
    return String(value || '').trim().toLocaleLowerCase('uz-UZ')
}

function parseCashAmount(raw) {
    const text = String(raw || '').trim().replace(/\s/g, '').replace(',', '.')
    if (!/^\d+(\.\d+)?$/.test(text)) return null
    const amount = parseFloat(text)
    return isFinite(amount) ? amount : null
}

function tryApplySecretDiscountFromCashInput() {
    const input = document.getElementById('cash-received-input')
    if (!input) return false
    const raw = normalizeSecretCode(input.value)
    if (!raw) return false

    const markupCode = normalizeSecretCode(typeof SECRET_MARKUP_CODE !== 'undefined' ? SECRET_MARKUP_CODE : '')
    const discountCode = normalizeSecretCode(typeof SECRET_DISCOUNT_CODE !== 'undefined' ? SECRET_DISCOUNT_CODE : '')

    if (markupCode && raw === markupCode) {
        secretMarkupActive = true
        secretDiscountActive = false
        syncCheckoutDiscountPercent()
        input.value = ''
        refreshCheckoutTotalsUI()
        return true
    }
    if (discountCode && raw === discountCode) {
        secretDiscountActive = true
        secretMarkupActive = false
        syncCheckoutDiscountPercent()
        input.value = ''
        refreshCheckoutTotalsUI()
        return true
    }
    return false
}

function onCashReceivedInput() {
    if (tryApplySecretDiscountFromCashInput()) return
    calculateChange()
}

function getCheckoutListSubtotal() {
    const items = getCheckoutCart()
    return items.reduce((sum, item) => {
        return sum + (parseFloat(item.price) || 0) * (parseInt(item.qty, 10) || 1)
    }, 0)
}

function getCheckoutNetSubtotal() {
    const list = getCheckoutListSubtotal()
    const markupPct = Math.min(1000, Math.max(0, parseFloat(checkoutMarkupPercent) || 0))
    if (markupPct > 0) {
        return Math.round(list * (100 + markupPct)) / 100
    }
    const pct = Math.min(100, Math.max(0, parseFloat(checkoutDiscountPercent) || 0))
    return Math.round(list * (100 - pct)) / 100
}

function getCheckoutTotal() {
    const subtotal = getCheckoutNetSubtotal()
    return subtotal + calcTax(subtotal)
}

function refreshCheckoutTotalsUI() {
    const cur = checkoutCurrency || getCartCurrency()
    currentGrandTotal = getCheckoutTotal()
    const list = getCheckoutListSubtotal()
    const net = getCheckoutNetSubtotal()
    const save = Math.max(0, list - net)
    const markup = Math.max(0, net - list)
    syncCheckoutPriceDisplays()
    const listRow = document.getElementById('cash-list-row')
    const saveRow = document.getElementById('cash-save-row')
    const listEl = document.getElementById('cash-list-price')
    const saveEl = document.getElementById('cash-save-amount')
    const saveLabel = document.getElementById('cash-save-label')
    const discountPct = Math.min(100, Math.max(0, parseFloat(checkoutDiscountPercent) || 0))
    const markupPct = Math.min(1000, Math.max(0, parseFloat(checkoutMarkupPercent) || 0))
    if (save > 0.001 || markup > 0.001) {
        if (listRow) listRow.classList.remove('hidden')
        if (saveRow) saveRow.classList.remove('hidden')
        if (listEl) listEl.textContent = formatMoney(list + calcTax(list), cur)
        if (markup > 0.001) {
            if (saveEl) saveEl.textContent = '+' + formatMoney(markup, cur)
            if (saveLabel) {
                const pctText = Number.isInteger(markupPct) ? String(markupPct) : String(Math.round(markupPct * 100) / 100)
                saveLabel.textContent = markupPct > 0 ? ('Ustama ' + pctText + '%') : 'Ustama'
            }
        } else {
            if (saveEl) saveEl.textContent = '−' + formatMoney(save, cur)
            if (saveLabel) {
                const pctText = Number.isInteger(discountPct) ? String(discountPct) : String(Math.round(discountPct * 100) / 100)
                saveLabel.textContent = discountPct > 0 ? ('Chegirma ' + pctText + '%') : 'Chegirma'
            }
        }
    } else {
        if (listRow) listRow.classList.add('hidden')
        if (saveRow) saveRow.classList.add('hidden')
        if (saveLabel) saveLabel.textContent = 'Chegirma'
    }
    renderQuickCashAmounts()
    calculateChange()
}

async function lookupCustomerByPhone() {
    const phoneEl = document.getElementById('cash-cust-phone')
    const hint = document.getElementById('cash-cust-lookup-hint')
    if (!phoneEl) return
    const phone = (phoneEl.value || '').trim()
    if (phone.length < 5) {
        if (hint) {
            hint.classList.add('hidden')
            hint.textContent = ''
        }
        loyaltyDiscountPercent = 0
        syncCheckoutDiscountPercent()
        const typeEl = document.getElementById('cash-cust-type')
        if (typeEl) typeEl.value = 'regular'
        refreshCheckoutTotalsUI()
        return
    }
    try {
        const res = await fetch('/api/customers/lookup/?phone=' + encodeURIComponent(phone))
        const data = await res.json()
        if (!data.found || !data.customer) {
            if (hint) {
                hint.textContent = ''
                hint.classList.add('hidden')
            }
            loyaltyDiscountPercent = 0
            syncCheckoutDiscountPercent()
            const typeEl = document.getElementById('cash-cust-type')
            if (typeEl) typeEl.value = 'regular'
            refreshCheckoutTotalsUI()
            return
        }
        const c = data.customer
        const nameEl = document.getElementById('cash-cust-name')
        const addrEl = document.getElementById('cash-cust-address')
        const typeEl = document.getElementById('cash-cust-type')
        if (nameEl) nameEl.value = c.name || ''
        if (addrEl) addrEl.value = c.address || ''
        if (typeEl) typeEl.value = c.customer_type || 'regular'
        loyaltyDiscountPercent = parseFloat(c.discount_percent) || 0
        syncCheckoutDiscountPercent()
        if (hint) {
            if (c.customer_type && c.customer_type !== 'regular') {
                const pct = checkoutDiscountPercent
                hint.textContent = (c.customer_type_label || 'Mijoz') + (pct > 0 ? ` · chegirma −${pct}%` : '')
                hint.className = 'mt-1 text-[11px] font-semibold text-emerald-600'
                hint.classList.remove('hidden')
            } else {
                hint.textContent = 'Mijoz topildi'
                hint.className = 'mt-1 text-[11px] text-gray-500'
                hint.classList.remove('hidden')
            }
        }
        refreshCheckoutTotalsUI()
    } catch (e) {
        console.error(e)
    }
}

function setCheckoutCurrency(currency) {
    checkoutCurrency = normalizeCurrency(currency)
    currentGrandTotal = getCheckoutTotal()
    renderCart()
    syncCashCurrencyUI()
    if (typeof refreshCheckoutTotalsUI === 'function') refreshCheckoutTotalsUI()

    const modal = document.getElementById('modal-container')
    if (modal && !modal.classList.contains('hidden') && typeof renderCheckoutCartRows === 'function') {
        renderCheckoutCartRows()
    }
}

function openCheckoutModal(type){
    let modalContainer = document.getElementById('modal-container');
    let cashModal = document.getElementById("cash-modal");

    const currencies = [...new Set(cart.map((item) => normalizeCurrency(item.currency)))]
    if (!checkoutCurrency || !currencies.includes(normalizeCurrency(checkoutCurrency))) {
        checkoutCurrency = currencies[0] || 'UZS'
    }

    const checkoutCart = getCheckoutCart()
    if (!checkoutCart.length) {
        alert('Tanlangan valyutada mahsulot yo‘q')
        return
    }

    loyaltyDiscountPercent = 0
    secretDiscountActive = false
    secretMarkupActive = false
    syncCheckoutDiscountPercent()
    const typeEl = document.getElementById('cash-cust-type')
    if (typeEl) typeEl.value = 'regular'
    const partnerHid = document.getElementById('cash-partner-id')
    if (partnerHid) partnerHid.value = ''
    const hint = document.getElementById('cash-cust-lookup-hint')
    if (hint) {
        hint.textContent = ''
        hint.classList.add('hidden')
    }

    const phoneEl = document.getElementById('cash-cust-phone')
    if (phoneEl && !(phoneEl.value || '').trim()) phoneEl.value = '+998'
    const nameEl = document.getElementById('cash-cust-name')
    if (nameEl) nameEl.value = ''
    const addrEl = document.getElementById('cash-cust-address')
    if (addrEl) addrEl.value = ''

    currentGrandTotal = getCheckoutTotal()

    if (typeof setMobileCartOpen === 'function') setMobileCartOpen(false)

    const custDetails = document.getElementById('cash-customer-details')
    const itemsDetails = document.getElementById('cash-items-details')
    const isMobile = window.matchMedia('(max-width: 767px)').matches
    if (custDetails) custDetails.open = !isMobile
    if (itemsDetails) itemsDetails.open = false

    modalContainer.classList.remove('hidden');
    cashModal.classList.remove('hidden');
    document.body.classList.add('checkout-modal-open')
    renderCheckoutCartRows()
    syncCashCurrencyUI()
    refreshCheckoutTotalsUI()
    renderQuickCashAmounts()

    const cashInput = document.getElementById('cash-received-input')
    if (cashInput) {
        cashInput.value = ''
        if (isMobile) {
            setTimeout(() => {
                try { cashInput.focus({ preventScroll: true }) } catch (e) { cashInput.focus() }
            }, 180)
        }
    }
}

function closeCheckoutModal(){
    document.getElementById('modal-container').classList.add('hidden');
    document.body.classList.remove('checkout-modal-open')

    const cashRecieved = document.getElementById("cash-received");
    if (cashRecieved) {
        cashRecieved.value = ''
    }
    const cashInput = document.getElementById('cash-received-input')
    if (cashInput) cashInput.value = ''
    loyaltyDiscountPercent = 0
    secretDiscountActive = false
    secretMarkupActive = false
    syncCheckoutDiscountPercent()
}

function calculateChange(){
    const inputCash = document.getElementById('cash-received-input')
    const changeToDisplay = document.getElementById('change-display')
    const changeFoot = document.getElementById('change-display-foot')
    const changeLabel = document.getElementById('change-label')
    const debtHint = document.getElementById('debt-hint')
    if (!inputCash || !changeToDisplay) return

    const raw = (inputCash.value || '').trim()
    const cur = checkoutCurrency || getCartCurrency()
    const setFoot = (text, color) => {
        if (!changeFoot) return
        changeFoot.textContent = text
        changeFoot.style.color = color || ''
    }

    if (raw === '') {
        if (changeLabel) changeLabel.textContent = 'Qaytim'
        changeToDisplay.textContent = formatMoney(0, cur)
        changeToDisplay.style.color = '#059669'
        setFoot('', '')
        if (debtHint) debtHint.classList.add('hidden')
        return
    }

    const cashRecieved = parseCashAmount(raw)
    if (cashRecieved === null) {
        if (changeLabel) changeLabel.textContent = 'Chegirma'
        changeToDisplay.textContent = 'kod'
        changeToDisplay.style.color = '#059669'
        setFoot('Maxfiy kod — bu qarz emas', '#059669')
        if (debtHint) debtHint.classList.add('hidden')
        return
    }
    const change = cashRecieved - currentGrandTotal

    if (change < 0) {
        if (changeLabel) changeLabel.textContent = 'Qarz'
        const debtText = formatMoney(Math.abs(change), cur)
        changeToDisplay.textContent = debtText
        changeToDisplay.style.color = '#d97706'
        setFoot('Qarz: ' + debtText, '#d97706')
        if (debtHint) debtHint.classList.remove('hidden')
        const custDetails = document.getElementById('cash-customer-details')
        if (custDetails && window.matchMedia('(max-width: 767px)').matches) custDetails.open = true
    } else {
        if (changeLabel) changeLabel.textContent = 'Qaytim'
        const changeText = formatMoney(change, cur)
        changeToDisplay.textContent = changeText
        changeToDisplay.style.color = '#059669'
        setFoot(change > 0 ? ('Qaytim: ' + changeText) : 'Aniq', '#059669')
        if (debtHint) debtHint.classList.add('hidden')
    }
}

function printOrderReceipt(orderId) {
    if (!orderId) return
    const url = `/accounts/${orderId}/emp_receipt/?autoprint=1`
    const w = window.open(url, 'pos_receipt', 'noopener,width=480,height=720')
    if (!w) return

    setTimeout(() => {
        try {
            if (!w.closed) w.focus()
        } catch (e) {  }
    }, 300)
}

function removePaidCurrencyFromCart(paidCurrency) {
    const cur = normalizeCurrency(paidCurrency)
    cart = cart.filter((item) => normalizeCurrency(item.currency) !== cur)
    if (cart.length) {
        localStorage.setItem(cartKey, JSON.stringify(cart))
        checkoutCurrency = getCartCurrency()
    } else {
        localStorage.removeItem(cartKey)
        checkoutCurrency = 'UZS'
    }
}


async function submitQuoteOrder(paymentCart, totalAmount, customerData) {
    const payCart = paymentCart && paymentCart.length ? paymentCart : getCheckoutCart()
    const payTotal = totalAmount || getCheckoutTotal()
    const payCurrency = normalizeCurrency(checkoutCurrency || getCartCurrency())
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value
    try {
        const response = await fetch('/checkout/quote/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify({
                cart: payCart,
                totalAmount: payTotal,
                customerData: customerData,
                currency: payCurrency,
                secretCode: getActiveSecretCode(),
            }),
        })
        const data = await response.json()
        if (data.success) {
            removePaidCurrencyFromCart(payCurrency)
            renderCart()
            closeCheckoutModal()
            alert(data.message || 'Buyurtma menejerga yuborildi')
            printOrderReceipt(data.order_id)
        } else {
            alert('Xatolik: ' + (data.message || 'Noma’lum'))
        }
    } catch (error) {
        console.error(error)
        alert('Tarmoq xatosi')
    }
}

async function processCashPayment(paymentCart, totalAmount, cashReceived, changeGiven, customerData){
    const payCart = paymentCart && paymentCart.length ? paymentCart : getCheckoutCart()
    const payTotal = totalAmount || getCheckoutTotal()
    const payCurrency = normalizeCurrency(checkoutCurrency || getCartCurrency())

    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value

    try{
        const response = await fetch('/checkout/cash/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                cart: payCart,
                totalAmount: payTotal,
                cashReceived: cashReceived,
                changeGiven: changeGiven,
                customerData: customerData,
                paymentMethod: 'CASH',
                currency: payCurrency,
                secretCode: getActiveSecretCode(),
            })
        })

        const data = await response.json()

        if (data.success) {
            removePaidCurrencyFromCart(payCurrency)
            renderCart()
            closeCheckoutModal()
            if (data.debt_id) {
                alert(data.message || 'Qarz qarzdorlar ro‘yxatiga yozildi')
            }
            printOrderReceipt(data.order_id)
        } else {
            alert("Xatolik: " + data.message)
        }

    } catch (error) {
        console.error(error)
    }
}
