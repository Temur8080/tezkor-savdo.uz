async function processScan(code) {
    const barcodeValue = String(code || '').trim()
    if (!barcodeValue) return

    const url = `/scan_product/?barcode=${encodeURIComponent(barcodeValue)}`

    try {
        const response = await fetch(url, { credentials: 'same-origin' });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}))
            alert(err.error || 'Mahsulot topilmadi')
            return
        }

        const data = await response.json();
        addItemToCart({
            id: data.id,
            name: data.name,
            price: parseFloat(data.price),
            currency: data.currency || 'UZS',
            unit: data.unit || 'ta',
            qty: 1,
            img: data.image || '',
            stock: data.stock,
        })
    } catch (e) {
        console.error(e)
        alert('Skaner xatosi')
    }
}
