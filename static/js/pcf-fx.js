/* PCF — micro-interações do design system (sem dependências).
   - [data-reveal]           revela ao entrar na viewport (fade + rise)
   - [data-count="1234"]     conta de 0 até o número quando aparece
   - .pcf-spotlight / .pcf-glow-card   seguem o mouse (--mx / --my)
   Respeita prefers-reduced-motion. */
(function () {
  'use strict';

  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var hasIO = 'IntersectionObserver' in window;

  /* ---------- 1. Reveal on scroll ---------- */
  var revealEls = document.querySelectorAll('[data-reveal]');
  if (revealEls.length) {
    if (reduce || !hasIO) {
      revealEls.forEach(function (el) { el.style.opacity = '1'; el.style.transform = 'none'; });
    } else {
      revealEls.forEach(function (el) {
        el.style.opacity = '0';
        el.style.transform = 'translateY(18px)';
        el.style.transition = 'opacity .6s cubic-bezier(.2,.7,.3,1), transform .6s cubic-bezier(.2,.7,.3,1)';
        el.style.transitionDelay = (el.getAttribute('data-reveal-delay') || '0') + 'ms';
      });
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (!e.isIntersecting) return;
          e.target.style.opacity = '1';
          e.target.style.transform = 'none';
          io.unobserve(e.target);
        });
      }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });
      revealEls.forEach(function (el) { io.observe(el); });
    }
  }

  /* ---------- 2. Contadores animados ---------- */
  function formatNum(n, decimals, prefix, suffix) {
    var s = decimals > 0 ? n.toFixed(decimals).replace('.', ',') : String(Math.round(n));
    if (decimals === 0) s = s.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return (prefix || '') + s + (suffix || '');
  }

  function runCount(el) {
    var target = parseFloat(String(el.getAttribute('data-count')).replace(',', '.'));
    if (isNaN(target)) return;
    var decimals = parseInt(el.getAttribute('data-count-decimals') || '0', 10);
    var prefix = el.getAttribute('data-count-prefix') || '';
    var suffix = el.getAttribute('data-count-suffix') || '';
    var dur = parseInt(el.getAttribute('data-count-duration') || '1400', 10);

    if (reduce) { el.textContent = formatNum(target, decimals, prefix, suffix); return; }

    var start = null;
    function step(ts) {
      if (start === null) start = ts;
      var p = Math.min(1, (ts - start) / dur);
      var eased = 1 - Math.pow(1 - p, 3);           // easeOutCubic
      el.textContent = formatNum(target * eased, decimals, prefix, suffix);
      if (p < 1) requestAnimationFrame(step);
      else el.textContent = formatNum(target, decimals, prefix, suffix);
    }
    requestAnimationFrame(step);
  }

  var countEls = document.querySelectorAll('[data-count]');
  if (countEls.length) {
    if (!hasIO) {
      countEls.forEach(runCount);
    } else {
      var ioC = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (!e.isIntersecting) return;
          runCount(e.target);
          ioC.unobserve(e.target);
        });
      }, { threshold: 0.4 });
      countEls.forEach(function (el) { ioC.observe(el); });
    }
  }

  /* ---------- 3. Spotlight / glow seguindo o mouse ---------- */
  if (!reduce && window.matchMedia && window.matchMedia('(hover: hover)').matches) {
    document.addEventListener('pointermove', function (ev) {
      var el = ev.target instanceof Element ? ev.target.closest('.pcf-spotlight, .pcf-glow-card') : null;
      if (!el) return;
      var r = el.getBoundingClientRect();
      el.style.setProperty('--mx', (ev.clientX - r.left) + 'px');
      el.style.setProperty('--my', (ev.clientY - r.top) + 'px');
    }, { passive: true });
  }
})();
