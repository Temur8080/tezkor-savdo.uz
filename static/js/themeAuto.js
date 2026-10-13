(function () {
  var cfg = window.TEZKOR_THEME || {};
  var DAY_START = Number(cfg.dayStart);
  var NIGHT_START = Number(cfg.nightStart);
  if (!Number.isFinite(DAY_START) || DAY_START < 0 || DAY_START > 23) DAY_START = 6;
  if (!Number.isFinite(NIGHT_START) || NIGHT_START < 0 || NIGHT_START > 23) NIGHT_START = 19;
  var MODE = (cfg.mode || 'system').toLowerCase();
  if (['system', 'day', 'night', 'auto'].indexOf(MODE) === -1) MODE = 'system';
  var KEY = 'tezkor-theme-mode';

  function hourNow() {
    return new Date().getHours();
  }

  function isNightByClock() {
    var h = hourNow();
    return h >= NIGHT_START || h < DAY_START;
  }

  function isNightBySystem() {
    try {
      return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    } catch (e) {
      return false;
    }
  }

  function shouldUseDark() {
    if (MODE === 'day') return false;
    if (MODE === 'night') return true;
    if (MODE === 'auto') return isNightByClock();
    return isNightBySystem();
  }

  function applyTheme() {
    var dark = shouldUseDark();
    var root = document.documentElement;
    root.classList.toggle('dark', dark);
    root.style.colorScheme = dark ? 'dark' : 'light';
    root.setAttribute('data-theme', dark ? 'night' : 'day');
    try {
      localStorage.setItem(KEY, dark ? 'night' : 'day');
    } catch (e) {}
    document.dispatchEvent(new CustomEvent('tezkor:theme', { detail: { dark: dark, mode: MODE } }));
  }

  applyTheme();

  if (MODE === 'auto' || MODE === 'system') {
    setInterval(applyTheme, 60 * 1000);
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'visible') applyTheme();
    });
  }

  if (MODE === 'system') {
    try {
      var mq = window.matchMedia('(prefers-color-scheme: dark)');
      if (mq.addEventListener) mq.addEventListener('change', applyTheme);
      else if (mq.addListener) mq.addListener(applyTheme);
    } catch (e) {}
  }

  window.TezkorTheme = {
    apply: applyTheme,
    isDark: function () {
      return document.documentElement.classList.contains('dark');
    },
    mode: function () {
      return MODE;
    },
  };
})();
