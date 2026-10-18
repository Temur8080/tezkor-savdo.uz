function initMobileCartControls() {
    document.body.classList.add('pos-page')

    const openBtn = document.getElementById('pos-mobile-open')
    const payBtn = document.getElementById('pos-mobile-pay')
    const closeBtn = document.getElementById('pos-cart-close')
    const backdrop = document.getElementById('pos-cart-backdrop')
    const checkoutBtn = document.getElementById('checkout-btn')

    if (openBtn && !openBtn.dataset.posBound) {
        openBtn.dataset.posBound = '1'
        openBtn.addEventListener('click', () => {
            if (typeof setMobileCartOpen === 'function') setMobileCartOpen(true)
        })
    }

    if (closeBtn && !closeBtn.dataset.posBound) {
        closeBtn.dataset.posBound = '1'
        closeBtn.addEventListener('click', () => {
            if (typeof setMobileCartOpen === 'function') setMobileCartOpen(false)
        })
    }

    if (backdrop && !backdrop.dataset.posBound) {
        backdrop.dataset.posBound = '1'
        backdrop.addEventListener('click', () => {
            if (typeof setMobileCartOpen === 'function') setMobileCartOpen(false)
        })
    }

    if (payBtn && !payBtn.dataset.posBound) {
        payBtn.dataset.posBound = '1'
        payBtn.addEventListener('click', () => {
            if (!cart.length) return
            if (typeof setMobileCartOpen === 'function') setMobileCartOpen(false)
            if (checkoutBtn) checkoutBtn.click()
            else if (typeof openCheckoutModal === 'function') openCheckoutModal('CASH')
        })
    }

    if (!window.__posMobileResizeBound) {
        window.__posMobileResizeBound = true
        let resizeT = null
        window.addEventListener('resize', () => {
            clearTimeout(resizeT)
            resizeT = setTimeout(() => {
                if (typeof isPosMobileLayout === 'function' && !isPosMobileLayout()) {
                    if (typeof setMobileCartOpen === 'function') setMobileCartOpen(false)
                } else if (typeof syncMobileCartBar === 'function') {
                    syncMobileCartBar()
                }
            }, 120)
        })
        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape') return
            if (!document.body.classList.contains('pos-cart-open')) return
            if (document.body.classList.contains('checkout-modal-open')) return
            if (typeof setMobileCartOpen === 'function') setMobileCartOpen(false)
        })
    }

    if (typeof isPosMobileLayout === 'function' && !isPosMobileLayout()) {
        if (typeof setMobileCartOpen === 'function') setMobileCartOpen(false)
    } else if (typeof syncMobileCartBar === 'function') {
        syncMobileCartBar()
    }
}

function initPosTerminal() {
    initMobileCartControls()

    if (typeof IS_CONSULTANT !== 'undefined' && IS_CONSULTANT) {
        const lbl = document.getElementById('checkout-btn-label')
        if (lbl) lbl.textContent = 'Hisob / Buyurtma'
        const mobilePay = document.getElementById('pos-mobile-pay')
        if (mobilePay) mobilePay.textContent = 'Hisob'
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

    const reserveBtn = document.getElementById('reserve-order-btn')
    if (reserveBtn && !reserveBtn.dataset.posBound) {
        reserveBtn.dataset.posBound = '1'
        reserveBtn.addEventListener('click', () => reserveCurrentOrder())
    }

    const reserveBadge = document.getElementById('reserve-count-badge')
    if (reserveBadge && !reserveBadge.dataset.posBound) {
        reserveBadge.dataset.posBound = '1'
        reserveBadge.addEventListener('click', (e) => {
            e.preventDefault()
            e.stopPropagation()
            if (typeof toggleReservedOrdersDropdown === 'function') toggleReservedOrdersDropdown()
        })
    }

    document.addEventListener('click', (e) => {
        const wrap = document.getElementById('reserve-btn-wrap')
        const dropdown = document.getElementById('reserved-orders-dropdown')
        if (!wrap || !dropdown || dropdown.classList.contains('hidden')) return
        if (!wrap.contains(e.target)) dropdown.classList.add('hidden')
    })

    if (typeof syncCartStockFromGrid === 'function') syncCartStockFromGrid()
    renderCart()
    renderHeldOrders()
    const reservedReady = (typeof loadReservedOrders === 'function')
        ? loadReservedOrders()
        : Promise.resolve()
    Promise.resolve(reservedReady).then(() => {
        const params = new URLSearchParams(window.location.search || '')
        const reservationId = params.get('reservation')
        if (reservationId && typeof openReservationToCart === 'function') {
            openReservationToCart(reservationId).then(() => {
                const url = new URL(window.location.href)
                url.searchParams.delete('reservation')
                window.history.replaceState({}, '', url.pathname + url.search)
            })
        }
    })
    consumePendingTerminalScan()

    const cashInput = document.getElementById('cash-received-input')
    if (cashInput && !cashInput.dataset.posBound) {
        cashInput.dataset.posBound = '1'
        cashInput.addEventListener('input', () => {
            if (typeof onCashReceivedInput === 'function') onCashReceivedInput()
            else calculateChange()
        })
    }

    const exactBtn = document.getElementById('cash-exact-btn')
    if (exactBtn && !exactBtn.dataset.posBound) {
        exactBtn.dataset.posBound = '1'
        exactBtn.addEventListener('click', () => {
            if (typeof setExactCashAmount === 'function') setExactCashAmount()
        })
    }

    const quickWrap = document.getElementById('cash-quick-amounts')
    if (quickWrap && !quickWrap.dataset.posBound) {
        quickWrap.dataset.posBound = '1'
        quickWrap.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-cash-amount]')
            if (!btn || !quickWrap.contains(btn)) return
            if (typeof setCashReceivedAmount === 'function') {
                setCashReceivedAmount(btn.getAttribute('data-cash-amount'))
            }
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
                listPrice: data.product.list_price != null ? parseFloat(data.product.list_price) : undefined,
                saleDiscountPercent: parseFloat(data.product.sale_discount_percent || 0) || 0,
                currency: data.product.currency || 'UZS',
                unit: data.product.unit || 'ta',
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
