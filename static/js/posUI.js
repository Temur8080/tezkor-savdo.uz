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

function selectProductFromCard(card) {
    if (!card || card.disabled) return

    const stock = parseInt(card.getAttribute('data-stock'), 10) || 0
    if (stock <= 0) {
        alert('Mahsulot omborda tugagan')
        return
    }

    addItemToCart({
        id: parseInt(card.getAttribute('data-id'), 10),
        name: card.getAttribute('data-name') || '',
        price: parseFloat(card.getAttribute('data-price')),
        currency: normalizeCurrency(card.getAttribute('data-currency')),
        qty: 1,
        img: card.getAttribute('data-image') || '',
        stock: stock,
    })
}

function getCartTotalsByCurrency() {
    const totals = { UZS: 0, USD: 0 }
    cart.forEach((item) => {
        const cur = normalizeCurrency(item.currency)
        const qty = Math.max(1, parseInt(item.qty, 10) || 1)
        totals[cur] += (parseFloat(item.price) || 0) * qty
    })
    return totals
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
        return;
    }

    cart.forEach(item => {
        item.currency = normalizeCurrency(item.currency)
        const qty = Math.max(1, parseInt(item.qty, 10) || 1)
        item.qty = qty
        let subTotal = item.price * qty
        const imgHtml = item.img
            ? `<img src="${item.img}" class="h-11 w-11 object-cover rounded-md border border-sky-200 bg-white">`
            : `<div class="h-11 w-11 rounded-md border border-sky-200 bg-white flex items-center justify-center text-xs text-sky-400 font-semibold">N/A</div>`

        cartContainer.innerHTML += `
                    <div class="flex items-center gap-3 bg-white/90 p-2.5 rounded-md border border-sky-200 shadow-sm">
                        ${imgHtml}
                        <div class="flex-grow min-w-0">
                            <h4 class="font-semibold text-sm text-sky-950 truncate">${item.name}</h4>
                            <p class="text-xs text-sky-700/70">${formatMoney(item.price, item.currency)} · ${item.currency === 'USD' ? 'USD' : 'UZS'}</p>
                            <div class="flex items-center gap-1.5 mt-1.5">
                                <button type="button" onclick="changeCartQty(${item.id}, -1)"
                                        class="w-7 h-7 rounded-md border border-sky-200 bg-sky-50 text-sky-800 text-sm font-bold hover:bg-sky-100">-</button>
                                <span class="min-w-[2rem] h-7 px-2 inline-flex items-center justify-center rounded-md border border-sky-200 text-sky-950 font-semibold text-sm bg-white select-none">${qty}</span>
                                <button type="button" onclick="changeCartQty(${item.id}, 1)"
                                        class="w-7 h-7 rounded-md border border-sky-200 bg-sky-50 text-sky-800 text-sm font-bold hover:bg-sky-100">+</button>
                            </div>
                        </div>
                        <div class="self-stretch flex flex-col items-end justify-between shrink-0">
                            <p class="font-bold text-sm text-sky-900">${formatMoney(subTotal, item.currency)}</p>
                            <button type="button" onclick="removeFromCart(${item.id})"
                                    class="w-7 h-7 inline-flex items-center justify-center rounded-md text-red-600 hover:text-red-700 hover:bg-red-50 transition-colors text-2xl font-black leading-none"
                                    title="O‘chirish" aria-label="O‘chirish">
                                &times;
                            </button>
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
}

function addItemToCart(scannedItem) {
    if (!scannedItem || !scannedItem.id || isNaN(scannedItem.price)){
        console.error("Scanned Item is invalid");
        return
    }

    cart.forEach((item) => {
        item.currency = normalizeCurrency(item.currency)
    })

    const itemCurrency = normalizeCurrency(scannedItem.currency)
    const qtyToAdd = Math.max(1, parseInt(scannedItem.qty, 10) || 1)
    const itemExist = cart.find(item => item.id === scannedItem.id);

    if (itemExist){
        itemExist.qty = (parseInt(itemExist.qty, 10) || 0) + qtyToAdd
        itemExist.currency = itemCurrency
    } else {
        cart.push({
            ...scannedItem,
            qty: qtyToAdd,
            price: parseFloat(scannedItem.price),
            currency: itemCurrency,
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
    heldOrders = heldOrders.filter((h) => String(h.id) !== String(heldId))
    saveHeldOrders()
    renderHeldOrders()
}

function renderHeldOrders() {
    const panel = document.getElementById('held-orders-panel')
    const list = document.getElementById('held-orders-list')
    if (!panel || !list) return

    if (!heldOrders.length) {
        panel.classList.add('hidden')
        list.innerHTML = ''
        return
    }

    panel.classList.remove('hidden')
    list.innerHTML = heldOrders.map((held) => {
        const count = (held.cart || []).reduce((sum, item) => sum + (parseInt(item.qty, 10) || 1), 0)
        const time = held.createdAt ? new Date(held.createdAt).toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' }) : ''
        return `
            <div class="flex items-center gap-2 bg-white/80 border border-sky-300 rounded-md px-3 py-2">
                <button type="button" onclick="restoreHeldOrder(${held.id})"
                        class="flex-grow text-left min-w-0">
                    <p class="font-semibold text-sm text-sky-950 truncate">${held.label}</p>
                    <p class="text-[10px] text-sky-700">${count} ta mahsulot · ${time}</p>
                </button>
                <button type="button" onclick="deleteHeldOrder(${held.id})"
                        class="text-red-600 hover:text-red-700 font-black px-2" title="O‘chirish">&times;</button>
            </div>
        `
    }).join('')
}

function changeCartQty(id, delta) {
    const item = cart.find(i => i.id === id)
    if (!item) return

    const next = (parseInt(item.qty, 10) || 1) + delta
    if (next < 1) {
        removeFromCart(id)
        return
    }

    item.qty = next
    localStorage.setItem(cartKey, JSON.stringify(cart))
    renderCart()
}

function setCartQty(id, value) {
    const item = cart.find(i => i.id === id)
    if (!item) return

    const next = parseInt(value, 10)
    if (!next || next < 1) {
        removeFromCart(id)
        return
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
        if (cur === 'USD') {
            usdBtn.className = 'flex-1 py-2 rounded-md text-sm font-semibold bg-blue-600 text-white'
            uzsBtn.className = 'flex-1 py-2 rounded-md text-sm font-semibold bg-gray-100 text-gray-600'
        } else {
            uzsBtn.className = 'flex-1 py-2 rounded-md text-sm font-semibold bg-blue-600 text-white'
            usdBtn.className = 'flex-1 py-2 rounded-md text-sm font-semibold bg-gray-100 text-gray-600'
        }
    }
    const priceEl = document.getElementById('cash-modal-price')
    if (priceEl) priceEl.textContent = formatMoney(currentGrandTotal, cur)
    calculateChange()
}

function getCheckoutCart() {
    const cur = normalizeCurrency(checkoutCurrency || getCartCurrency())
    return cart.filter((item) => normalizeCurrency(item.currency) === cur)
}

let checkoutDiscountPercent = 0
let loyaltyDiscountPercent = 0
let secretDiscountActive = false

function syncCheckoutDiscountPercent() {
    const secretPct = secretDiscountActive
        ? Math.min(100, Math.max(0, parseFloat(typeof SECRET_DISCOUNT_PERCENT !== 'undefined' ? SECRET_DISCOUNT_PERCENT : 0) || 0))
        : 0
    const loyaltyPct = Math.min(100, Math.max(0, parseFloat(loyaltyDiscountPercent) || 0))
    checkoutDiscountPercent = Math.max(loyaltyPct, secretPct)
}

function tryApplySecretDiscountFromCashInput() {
    const input = document.getElementById('cash-received-input')
    if (!input) return false
    const expected = (typeof SECRET_DISCOUNT_CODE !== 'undefined' ? SECRET_DISCOUNT_CODE : '') || ''
    if (!expected) return false
    const raw = (input.value || '').trim()
    if (raw !== expected) return false
    secretDiscountActive = true
    syncCheckoutDiscountPercent()
    input.value = ''
    refreshCheckoutTotalsUI()
    return true
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
    const priceEl = document.getElementById('cash-modal-price')
    if (priceEl) priceEl.textContent = formatMoney(currentGrandTotal, cur)
    const listRow = document.getElementById('cash-list-row')
    const saveRow = document.getElementById('cash-save-row')
    const listEl = document.getElementById('cash-list-price')
    const saveEl = document.getElementById('cash-save-amount')
    const saveLabel = document.getElementById('cash-save-label')
    const pct = Math.min(100, Math.max(0, parseFloat(checkoutDiscountPercent) || 0))
    if (save > 0.001) {
        if (listRow) listRow.classList.remove('hidden')
        if (saveRow) saveRow.classList.remove('hidden')
        if (listEl) listEl.textContent = formatMoney(list + calcTax(list), cur)
        if (saveEl) saveEl.textContent = '−' + formatMoney(save, cur)
        if (saveLabel) {
            const pctText = Number.isInteger(pct) ? String(pct) : String(Math.round(pct * 100) / 100)
            saveLabel.textContent = pct > 0 ? ('Chegirma ' + pctText + '%') : 'Chegirma'
        }
    } else {
        if (listRow) listRow.classList.add('hidden')
        if (saveRow) saveRow.classList.add('hidden')
        if (saveLabel) saveLabel.textContent = 'Chegirma'
    }
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
    if (modal && !modal.classList.contains('hidden')) {
        const checkoutCart = getCheckoutCart()
        const cartRows = checkoutCart.map(item => `
                <div class="flex flex-row items-center justify-between border-b border-gray-100 p-2 gap-4">
                    <div class="text-left flex-grow">
                        <p class="text-sm font-bold text-gray-900">${item.name}</p>
                        <p class="text-xs text-gray-500">Miqdor: ${item.qty}</p>
                        <p class="text-xs font-bold text-blue-700">${formatMoney(item.price * item.qty, item.currency)}</p>
                    </div>
                    <div class="flex-shrink-0">
                        ${item.img
                            ? `<img src="${item.img}" class="h-14 w-14 object-cover rounded-md border border-gray-200">`
                            : `<div class="h-14 w-14 rounded-md bg-gray-50 border border-gray-200 flex items-center justify-center text-xs text-gray-400 font-semibold">N/A</div>`}
                    </div>
                </div>
        `).join('')
        const cashModalImage = document.getElementById('cash-modal-image')
        if (cashModalImage) cashModalImage.innerHTML = cartRows
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

    currentGrandTotal = getCheckoutTotal()

    const cartRows = checkoutCart.map(item => {
        return `
                <div class="flex flex-row items-center justify-between border-b border-gray-100 p-2 gap-4">
                    <div class="text-left flex-grow">
                        <p class="text-sm font-bold text-gray-900">${item.name}</p>
                        <p class="text-xs text-gray-500">Miqdor: ${item.qty}</p>
                        <p class="text-xs font-bold text-blue-700">${formatMoney(item.price * item.qty, item.currency)}</p>
                    </div>
                    <div class="flex-shrink-0">
                        ${item.img
                            ? `<img src="${item.img}" class="h-14 w-14 object-cover rounded-md border border-gray-200">`
                            : `<div class="h-14 w-14 rounded-md bg-gray-50 border border-gray-200 flex items-center justify-center text-xs text-gray-400 font-semibold">N/A</div>`}
                    </div>
                </div>
                `
    }).join("")

    let cashModalImage = document.getElementById("cash-modal-image");

    modalContainer.classList.remove('hidden');
    cashModal.classList.remove('hidden');
    if (cashModalImage) cashModalImage.innerHTML = cartRows
    syncCashCurrencyUI()
    refreshCheckoutTotalsUI()
}

function closeCheckoutModal(){
    document.getElementById('modal-container').classList.add('hidden');

    const cashRecieved = document.getElementById("cash-received");
    if (cashRecieved) {
        cashRecieved.value = ''
    }
    const cashInput = document.getElementById('cash-received-input')
    if (cashInput) cashInput.value = ''
    loyaltyDiscountPercent = 0
    secretDiscountActive = false
    syncCheckoutDiscountPercent()
}

function calculateChange(){
    const inputCash = document.getElementById('cash-received-input')
    const changeToDisplay = document.getElementById('change-display')
    const changeLabel = document.getElementById('change-label')
    const debtHint = document.getElementById('debt-hint')
    if (!inputCash || !changeToDisplay) return

    const raw = (inputCash.value || '').trim()
    const cur = checkoutCurrency || getCartCurrency()

    if (raw === '') {
        if (changeLabel) changeLabel.textContent = 'Qaytariladigan qoldiq'
        changeToDisplay.textContent = formatMoney(0, cur)
        changeToDisplay.style.color = '#4ade80'
        if (debtHint) debtHint.classList.add('hidden')
        return
    }

    const cashRecieved = parseFloat(raw) || 0
    const change = cashRecieved - currentGrandTotal

    if (change < 0) {
        if (changeLabel) changeLabel.textContent = 'Qarz (qoldiq)'
        changeToDisplay.textContent = formatMoney(Math.abs(change), cur)
        changeToDisplay.style.color = '#fbbf24'
        if (debtHint) debtHint.classList.remove('hidden')
    } else {
        if (changeLabel) changeLabel.textContent = 'Qaytariladigan qoldiq'
        changeToDisplay.textContent = formatMoney(change, cur)
        changeToDisplay.style.color = '#4ade80'
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
                secretCode: secretDiscountActive
                    ? ((typeof SECRET_DISCOUNT_CODE !== 'undefined' ? SECRET_DISCOUNT_CODE : '') || '')
                    : '',
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
                secretCode: secretDiscountActive
                    ? ((typeof SECRET_DISCOUNT_CODE !== 'undefined' ? SECRET_DISCOUNT_CODE : '') || '')
                    : '',
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
