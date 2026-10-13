window.CURRENCY_UZS = 'UZS'
window.CURRENCY_USD = 'USD'

function formatNumberUZ(value, decimals) {
    const n = Number(value)
    if (!Number.isFinite(n)) return '0'

    const useDecimals = decimals !== undefined
        ? decimals
        : (Math.abs(n % 1) > 0.000001 ? 2 : 0)

    const fixed = useDecimals > 0 ? Math.abs(n).toFixed(useDecimals) : String(Math.round(Math.abs(n)))
    const parts = fixed.split('.')
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
    const sign = n < 0 ? '-' : ''
    return sign + (parts.length > 1 ? parts[0] + '.' + parts[1] : parts[0])
}

function formatMoney(value, currency) {
    const cur = (currency || window.CURRENCY_UZS).toUpperCase()
    const decimals = cur === 'USD' ? 2 : 0
    const number = formatNumberUZ(value, decimals)
    if (cur === 'USD') return '$' + number
    return number + ' so‘m'
}
