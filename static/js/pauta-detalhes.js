document.addEventListener('DOMContentLoaded', function () {
  'use strict';

  document.querySelectorAll('[data-ciencias]').forEach(function (details) {
    var input = details.querySelector('[data-ciencia-search]');
    var list = details.querySelector('[data-ciencia-list]');
    var feedback = details.querySelector('[data-ciencia-feedback]');
    var more = details.querySelector('[data-ciencia-more]');
    var next = 1;
    var loaded = false;
    var controller;
    var timer;

    function load(page, append) {
      if (controller) controller.abort();
      controller = new AbortController();
      var current = controller;
      var url = new URL(details.dataset.url, window.location.origin);
      url.searchParams.set('q', input.value.trim().replace(/^@/, ''));
      url.searchParams.set('page', page);
      more.disabled = true;
      feedback.textContent = 'Carregando…';
      if (!append) list.replaceChildren();
      fetch(url, { credentials: 'same-origin', signal: current.signal }).then(function (response) {
        if (!response.ok) throw new Error('Não foi possível carregar as ciências.');
        return response.json();
      }).then(function (data) {
        if (current !== controller) return;
        data.pessoas.forEach(function (person) {
          var item = document.createElement('li');
          var name = document.createElement('span');
          name.textContent = person.nome;
          var info = document.createElement('small');
          info.textContent = '@' + person.username + ' · ' + person.ciente_em;
          item.append(name, info);
          list.appendChild(item);
        });
        next = data.proxima;
        loaded = true;
        more.hidden = !next;
        more.textContent = 'Carregar mais';
        feedback.textContent = data.total ? list.children.length + ' de ' + data.total + ' pessoas' : 'Nenhuma ciência encontrada.';
      }).catch(function (error) {
        if (error.name === 'AbortError') return;
        feedback.textContent = 'Não foi possível carregar. Tente novamente.';
        next = page;
        more.hidden = false;
        more.textContent = 'Tentar novamente';
      }).finally(function () {
        if (current === controller) more.disabled = false;
      });
    }

    details.addEventListener('toggle', function () {
      if (details.open && !loaded) load(1, false);
    });
    input.addEventListener('input', function () {
      clearTimeout(timer);
      if (controller) controller.abort();
      more.disabled = true;
      timer = setTimeout(function () { load(1, false); }, 250);
    });
    more.addEventListener('click', function () { load(next || 1, list.children.length > 0); });
  });

  var params = new URLSearchParams(window.location.search);
  document.querySelectorAll('[data-pauta-modal]').forEach(function (modal) {
    modal.addEventListener('shown.bs.modal', function () {
      var commentId = params.get('comentario');
      if (commentId && /^\d+$/.test(commentId) && params.get('pauta') === modal.dataset.pautaModal) {
        var target = modal.querySelector('#comentario-' + commentId);
        if (target) {
          target.classList.add('is-mentioned');
          target.scrollIntoView({ block: 'nearest' });
          target.focus({ preventScroll: true });
        }
      }
      var endpoint = modal.querySelector('[data-read-mentions]');
      var csrf = modal.querySelector('[name="csrfmiddlewaretoken"]');
      if (!endpoint || !csrf) return;
      fetch(endpoint.dataset.readMentions, {
        method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf.value }
      }).then(function (response) {
        if (!response.ok) throw new Error('Falha ao atualizar as menções.');
        return response.json();
      }).then(function (data) {
        var badge = document.querySelector('[data-mention-badge]');
        if (badge) {
          badge.textContent = data.nao_lidas;
          badge.hidden = !data.nao_lidas;
          badge.parentElement.setAttribute('aria-label', 'Menções em pautas: ' + data.nao_lidas + ' não lidas');
        }
      }).catch(function () { /* O aviso permanece não lido e pode ser aberto novamente. */ });
    });
  });
});
