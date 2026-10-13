function initPosTerminal() {
    if (typeof IS_CONSULTANT !== 'undefined' && IS_CONSULTANT) {
        const lbl = document.getElementById('checkout-btn-label')
        if (lbl) lbl.textContent = 'Hisob / Buyurtma'
        const title = document.getElementById('cash-modal-title')
        if (title) title.textContent = 'Buyurtma (tasdiqlashga)'
        const sub = document.getElementById('cash-modal-subtitle')
        if (sub) sub.textContent = 'Mijoz ma’lumotlari va hisob-kitob'
        const payBlock = document.getElementById('cash-pay-block')
        if (payBlock) payBlock.classList.add('hidden')
        const placeLbl = document.getElementById('place-order-btn-label')
        if (placeLbl) placeLbl.textContent = 'Tasdiqlashga yuborish'
        const placeBtn = document.getElementById('place-order-btn')
        if (placeBtn) {
            placeBtn.classList.remove('bg-blue-600', 'hover:bg-blue-700', 'active:bg-blue-800')
            placeBtn.classList.add('bg-amber-600', 'hover:bg-amber-700', 'active:bg-amber-800')
        }
    }

    const checkoutBtn = document.getElementById('checkout-btn')
    const inventoryGrid = document.getElementById('inventory-grid')

    if (inventoryGrid && !inventoryGrid.dataset.posBound) {
        inventoryGrid.dataset.posBound = '1'
        inventoryGrid.addEventListener('click', (e) => {
            const card = e.target.closest('.product-card')
            if (!card || !inventoryGrid.contains(card)) return
            e.preventDefault()
            selectProductFromCard(card)
        })
    }

    if (checkoutBtn && !checkoutBtn.dataset.posBound) {
        checkoutBtn.dataset.posBound = '1'
        checkoutBtn.addEventListener('click', () => {
            if (cart.length === 0) return
            openCheckoutModal('CASH')
        })
    }

    const holdBtn = document.getElementById('hold-order-btn')
    if (holdBtn && !holdBtn.dataset.posBound) {
        holdBtn.dataset.posBound = '1'
        holdBtn.addEventListener('click', () => holdCurrentOrder())
    }

    if (typeof syncCartStockFromGrid === 'function') syncCartStockFromGrid()
    renderCart()
    renderHeldOrders()
    consumePendingTerminalScan()

    const cashInput = document.getElementById('cash-received-input')
    if (cashInput && !cashInput.dataset.posBound) {
        cashInput.dataset.posBound = '1'
        cashInput.addEventListener('input', () => {
            if (typeof onCashReceivedInput === 'function') onCashReceivedInput()
            else calculateChange()
        })
    }

    const uzsBtn = document.getElementById('cash-currency-uzs')
    const usdBtn = document.getElementById('cash-currency-usd')
    if (uzsBtn && !uzsBtn.dataset.posBound) {
        uzsBtn.dataset.posBound = '1'
        uzsBtn.addEventListener('click', () => setCheckoutCurrency('UZS'))
    }
    if (usdBtn && !usdBtn.dataset.posBound) {
        usdBtn.dataset.posBound = '1'
        usdBtn.addEventListener('click', () => setCheckoutCurrency('USD'))
    }

    const placeOrderBtn = document.getElementById('place-order-btn')
    if (placeOrderBtn && !placeOrderBtn.dataset.posBound) {
        placeOrderBtn.dataset.posBound = '1'
        placeOrderBtn.addEventListener('click', () => {
            const typeEl = document.getElementById('cash-cust-type')
            const partnerHid = document.getElementById('cash-partner-id')
            let phoneVal = (document.getElementById('cash-cust-phone').value || '').trim()
            if (phoneVal === '+998' || phoneVal === '998') phoneVal = ''
            const customerData = {
                name: (document.getElementById('cash-cust-name').value || '').trim(),
                phone: phoneVal,
                email: '',
                address: (document.getElementById('cash-cust-address').value || '').trim(),
                customer_type: (typeEl && typeEl.value) || 'regular',
                partner_id: (partnerHid && partnerHid.value) || null,
            }

            const total = getCheckoutTotal()
            if (typeof IS_CONSULTANT !== 'undefined' && IS_CONSULTANT) {
                submitQuoteOrder(getCheckoutCart(), total, customerData)
                return
            }

            const cashRaw = (document.getElementById('cash-received-input').value || '').trim()
            const cashReceived = cashRaw === '' ? total : (parseFloat(cashRaw) || 0)
            const changeGiven = Math.max(0, cashReceived - total)

            if (cashReceived < total && (!customerData.name || !customerData.phone)) {
                alert('Qarz uchun mijoz ismi va telefon majburiy')
                return
            }

            processCashPayment(getCheckoutCart(), total, cashReceived, changeGiven, customerData)
        })
    }

    const phoneEl = document.getElementById('cash-cust-phone')
    if (phoneEl && !phoneEl.dataset.loyaltyBound) {
        phoneEl.dataset.loyaltyBound = '1'
        let t = null
        phoneEl.addEventListener('input', () => {
            clearTimeout(t)
            t = setTimeout(() => {
                if (typeof lookupCustomerByPhone === 'function') lookupCustomerByPhone()
            }, 400)
        })
        phoneEl.addEventListener('blur', () => {
            if (typeof lookupCustomerByPhone === 'function') lookupCustomerByPhone()
        })
    }
}

function consumePendingTerminalScan() {
    try {
        const key = (window.GlobalScanner && window.GlobalScanner.STORAGE_KEY) || 'pendingScanAction'
        const raw = sessionStorage.getItem(key)
        if (!raw) return
        const data = JSON.parse(raw)
        if (!data || data.type !== 'terminal' || !data.barcode) return
        sessionStorage.removeItem(key)

        if (data.product && data.product.id && typeof addItemToCart === 'function') {
            addItemToCart({
                id: data.product.id,
                name: data.product.name,
                price: parseFloat(data.product.price),
                currency: data.product.currency || 'UZS',
                qty: 1,
                img: data.product.image || '',
                stock: data.product.stock,
            })
        } else if (typeof processScan === 'function') {
            processScan(data.barcode)
        }
    } catch (e) {
        console.error(e)
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPosTerminal)
} else {
    initPosTerminal()
}
