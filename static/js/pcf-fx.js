/* PCF — micro-interações do design system (sem dependências).
   - [data-reveal]           revela ao entrar na viewport (fade + rise)
   - [data-count="1234"]     conta de 0 até o número quando aparece
   - .pcf-spotlight / .pcf-glow-card   seguem o mouse (--mx / --my)
   Respeita prefers-reduced-motion. */
(function () {
  'use strict';

  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var hasIO = 'IntersectionObserver' in window;

  /* ---------- 1. Reveal on scroll ----------
     ATENÇÃO ao mexer aqui: este bloco ESCONDE conteúdo por JS e conta com o
     observador para mostrá-lo de volta. Qualquer caminho em que o observador
     não dispare deixa a página em branco de forma permanente — foi o que
     aconteceu com a lista de editais: com `threshold: 0.12`, um card alto
     (133 linhas, vários milhares de pixels) nunca conseguia ter 12% da sua
     área visível de uma vez, o gatilho não disparava, e a tabela sumia depois
     do primeiro instante. Daí `threshold: 0` (basta um pixel aparecer) e as
     duas redes de segurança abaixo. */
  var revealEls = document.querySelectorAll('[data-reveal]');
  if (revealEls.length) {
    var mostrar = function (el) {
      el.style.opacity = '1';
      el.style.transform = 'none';
    };
    var mostrarTodos = function () {
      revealEls.forEach(mostrar);
    };

    if (reduce || !hasIO) {
      mostrarTodos();
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
          mostrar(e.target);
          io.unobserve(e.target);
        });
      }, { threshold: 0, rootMargin: '0px 0px -4% 0px' });
      revealEls.forEach(function (el) { io.observe(el); });

      // Rede 1: imprimir não rola a página, então o que ainda não apareceu
      // sairia em branco no papel e no PDF.
      if (window.addEventListener) window.addEventListener('beforeprint', mostrarTodos);

      // Rede 2: se em 4s ainda houver bloco escondido dentro da janela, algo
      // deu errado no observador. Some com a animação, nunca com o conteúdo.
      window.setTimeout(function () {
        revealEls.forEach(function (el) {
          if (el.style.opacity !== '0') return;
          var r = el.getBoundingClientRect();
          if (r.top < window.innerHeight && r.bottom > 0) mostrar(el);
        });
      }, 4000);
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
