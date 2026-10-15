/**
 * Ro‘yxat sahifasida ko‘rinadigan qatorlar sonini ekran balandligiga moslaydi.
 * URL ga ?per_page=N qo‘yadi (bir marta, loopsiz).
 */
(function () {
  var MIN = 7
  var MAX = 50
  var ROW_FALLBACK = 52
  var BOTTOM_RESERVE = 88

  function parsePerPage(raw) {
    var n = parseInt(raw, 10)
    return Number.isFinite(n) ? n : 0
  }

  function measureRowHeight() {
    var row = document.querySelector('.table-scroll tbody tr, .page-main table tbody tr')
    if (!row) return ROW_FALLBACK
    var h = row.getBoundingClientRect().height
    return h > 28 ? h : ROW_FALLBACK
  }

  function measureAvailable() {
    var anchor =
      document.querySelector('.table-scroll') ||
      document.querySelector('.page-main table') ||
      document.querySelector('.page-main')
    if (!anchor) return Math.max(280, window.innerHeight - 220)
    var top = anchor.getBoundingClientRect().top
    return Math.max(200, window.innerHeight - top - BOTTOM_RESERVE)
  }

  function desiredPerPage() {
    var fit = Math.floor(measureAvailable() / measureRowHeight())
    return Math.max(MIN, Math.min(MAX, fit || MIN))
  }

  function apply() {
    var params = new URLSearchParams(window.location.search)
    var current = parsePerPage(params.get('per_page'))
    var want = desiredPerPage()

    // Allaqachon mos bo‘lsa — hech narsa qilma
    if (current === want) return
    // Kichik farq (1 qator) — zoom titrashidan qochish
    if (current > 0 && Math.abs(current - want) < 2) return

    params.set('per_page', String(want))
    params.delete('page')
    var qs = params.toString()
    var next = window.location.pathname + (qs ? '?' + qs : '')
    if (next === window.location.pathname + window.location.search) return
    window.location.replace(next)
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply)
  } else {
    apply()
  }

  var resizeTimer = null
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(apply, 450)
  })
})()
