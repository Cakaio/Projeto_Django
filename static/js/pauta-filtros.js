/* Filtro do quadro de pautas.
 *
 * Filtra no NAVEGADOR, escondendo cards já renderizados, em vez de recarregar a
 * página. A razão é simples: o quadro já vem inteiro no HTML, então ir ao
 * servidor para filtrar seria pagar duas vezes pelo mesmo conteúdo — e o
 * resultado aparece instantâneo enquanto a pessoa digita.
 *
 * O que cada card sabe sobre si vem do servidor em data-*: texto de busca já
 * em minúsculas (com etiqueta e responsável dentro, que não aparecem no card),
 * grupo, prioridade, se é minha, se falta minha ciência, se está atrasada.
 * Cavar isso do DOM a cada tecla seria lento e frágil.
 */
(function () {
  'use strict';

  var barra = document.querySelector('[data-board-filters]');
  if (!barra) return;

  var busca = barra.querySelector('[data-filter-busca]');
  var grupo = barra.querySelector('[data-filter-grupo]');
  var prioridade = barra.querySelector('[data-filter-prioridade]');
  var responsavel = barra.querySelector('[data-filter-responsavel]');
  var limpar = barra.querySelector('[data-filter-limpar]');

  var resumo = document.querySelector('[data-board-summary]');
  var atalhos = resumo ? Array.prototype.slice.call(
    resumo.querySelectorAll('[data-quick]')) : [];

  var resultado = document.querySelector('[data-filter-resultado]');
  var aviso = document.querySelector('[data-board-live]');
  var colunas = Array.prototype.slice.call(
    document.querySelectorAll('[data-kanban-column]'));

  var atalhoAtivo = 'tudo';

  function cardsDaColuna(coluna) {
    return Array.prototype.slice.call(coluna.querySelectorAll('[data-kanban-card]'));
  }

  function normalizar(texto) {
    // Sem acento: quem procura "orcamento" tem que achar "orçamento". O
    // servidor já manda o texto em minúsculas; aqui só cai o diacrítico.
    return (texto || '')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');
  }

  function passaNoFiltro(card) {
    if (atalhoAtivo === 'minhas' && card.dataset.minha !== '1') return false;
    if (atalhoAtivo === 'sem-ciencia' && card.dataset.semCiencia !== '1') return false;
    if (atalhoAtivo === 'atrasadas' && card.dataset.atrasada !== '1') return false;

    if (grupo && grupo.value && card.dataset.grupo !== grupo.value) return false;
    if (prioridade && prioridade.value && card.dataset.prioridade !== prioridade.value) return false;

    if (responsavel && responsavel.value) {
      var lista = (card.dataset.responsaveis || '').split(/\s+/);
      if (lista.indexOf(responsavel.value) === -1) return false;
    }

    var termo = normalizar(busca ? busca.value.trim() : '');
    if (termo) {
      // Todas as palavras precisam aparecer, em qualquer ordem: é como as
      // pessoas buscam ("evento maio" achando "Evento de maio").
      var palavras = termo.split(/\s+/);
      var alvo = normalizar(card.dataset.busca);
      for (var i = 0; i < palavras.length; i += 1) {
        if (alvo.indexOf(palavras[i]) === -1) return false;
      }
    }
    return true;
  }

  function temFiltroAtivo() {
    return Boolean(
      (busca && busca.value.trim()) ||
      (grupo && grupo.value) ||
      (prioridade && prioridade.value) ||
      (responsavel && responsavel.value) ||
      atalhoAtivo !== 'tudo'
    );
  }

  function aplicar() {
    var visiveis = 0;
    var total = 0;

    colunas.forEach(function (coluna) {
      var visiveisNaColuna = 0;
      cardsDaColuna(coluna).forEach(function (card) {
        total += 1;
        var mostra = passaNoFiltro(card);
        card.hidden = !mostra;
        if (mostra) {
          visiveisNaColuna += 1;
          visiveis += 1;
        }
      });

      var contador = coluna.querySelector('[data-column-count]');
      if (contador) {
        contador.textContent = String(visiveisNaColuna);
        contador.setAttribute('aria-label', visiveisNaColuna + ' cards');
      }

      // O vazio da coluna passa a dizer a verdade do momento: "nenhuma nesta
      // etapa" quando não há nada, "nada com esse filtro" quando há e está
      // escondido. Dizer sempre a primeira frase confundiria.
      var vazio = coluna.querySelector('[data-column-empty]');
      if (vazio) {
        vazio.hidden = visiveisNaColuna > 0;
        vazio.textContent = (cardsDaColuna(coluna).length && !visiveisNaColuna)
          ? 'Nada nesta etapa com o filtro atual.'
          : 'Nenhuma pauta nesta etapa.';
      }
    });

    if (limpar) limpar.hidden = !temFiltroAtivo();

    if (resultado) {
      if (temFiltroAtivo()) {
        resultado.hidden = false;
        resultado.textContent = visiveis
          ? 'Mostrando ' + visiveis + ' de ' + total + ' pauta' + (total === 1 ? '' : 's') + '.'
          : 'Nenhuma pauta encontrada. Ajuste a busca ou limpe os filtros.';
      } else {
        resultado.hidden = true;
      }
    }

    // Leitor de tela precisa saber que a lista mudou — sem isto, filtrar é uma
    // mudança silenciosa para quem não enxerga o quadro.
    if (aviso) aviso.textContent = visiveis + ' pautas visíveis.';

    guardarNaUrl();
  }

  function guardarNaUrl() {
    if (!window.history || !window.history.replaceState) return;
    var parametros = new URLSearchParams(window.location.search);

    // `concluidas=todas` é decisão do servidor e não pode ser apagada aqui.
    ['q', 'grupo', 'prioridade', 'responsavel', 'ver'].forEach(function (chave) {
      parametros.delete(chave);
    });

    if (busca && busca.value.trim()) parametros.set('q', busca.value.trim());
    if (grupo && grupo.value) parametros.set('grupo', grupo.value);
    if (prioridade && prioridade.value) parametros.set('prioridade', prioridade.value);
    if (responsavel && responsavel.value) parametros.set('responsavel', responsavel.value);
    if (atalhoAtivo !== 'tudo') parametros.set('ver', atalhoAtivo);

    var consulta = parametros.toString();
    window.history.replaceState(
      null, '', window.location.pathname + (consulta ? '?' + consulta : ''));
  }

  function lerDaUrl() {
    var parametros = new URLSearchParams(window.location.search);
    if (busca) busca.value = parametros.get('q') || '';
    if (grupo) grupo.value = parametros.get('grupo') || '';
    if (prioridade) prioridade.value = parametros.get('prioridade') || '';
    if (responsavel) responsavel.value = parametros.get('responsavel') || '';

    var ver = parametros.get('ver');
    if (ver && ['minhas', 'sem-ciencia', 'atrasadas'].indexOf(ver) !== -1) {
      atalhoAtivo = ver;
    }
    marcarAtalhos();
  }

  function marcarAtalhos() {
    atalhos.forEach(function (botao) {
      botao.setAttribute(
        'aria-pressed', botao.dataset.quick === atalhoAtivo ? 'true' : 'false');
    });
  }

  atalhos.forEach(function (botao) {
    botao.addEventListener('click', function () {
      // Clicar no atalho já ativo volta para "tudo": o botão vira interruptor,
      // em vez de exigir procurar onde desligar.
      atalhoAtivo = (atalhoAtivo === botao.dataset.quick) ? 'tudo' : botao.dataset.quick;
      marcarAtalhos();
      aplicar();
    });
  });

  [grupo, prioridade, responsavel].forEach(function (campo) {
    if (campo) campo.addEventListener('change', aplicar);
  });

  if (busca) {
    var temporizador = null;
    busca.addEventListener('input', function () {
      window.clearTimeout(temporizador);
      temporizador = window.setTimeout(aplicar, 120);
    });
    busca.addEventListener('search', aplicar);
  }

  if (limpar) {
    limpar.addEventListener('click', function () {
      if (busca) busca.value = '';
      if (grupo) grupo.value = '';
      if (prioridade) prioridade.value = '';
      if (responsavel) responsavel.value = '';
      atalhoAtivo = 'tudo';
      marcarAtalhos();
      aplicar();
      if (busca) busca.focus();
    });
  }

  lerDaUrl();
  aplicar();
})();
