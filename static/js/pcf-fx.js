/* PCF — micro-interações do design system (sem dependências).
   - data-reveal: revela o elemento (fade+rise) quando entra na viewport.
   Respeita prefers-reduced-motion. */
(function () {
  'use strict';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var els = document.querySelectorAll('[data-reveal]');
  if (!els.length) return;

  if (reduce || !('IntersectionObserver' in window)) {
    els.forEach(function (el) { el.style.opacity = '1'; el.style.transform = 'none'; });
    return;
  }

  els.forEach(function (el) {
    el.style.opacity = '0';
    el.style.transform = 'translateY(18px)';
    el.style.transition = 'opacity .6s ease, transform .6s ease';
    el.style.transitionDelay = (el.getAttribute('data-reveal-delay') || '0') + 'ms';
  });

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) {
        e.target.style.opacity = '1';
        e.target.style.transform = 'none';
        io.unobserve(e.target);
      }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });

  els.forEach(function (el) { io.observe(el); });
})();
