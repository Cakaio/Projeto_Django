/* PCF — select com busca (combobox), sem dependência nenhuma.
   Transforma <select> em campo onde se digita para filtrar. Feito para o
   catálogo do Supply, que tem item demais para achar rolando a lista.

   COMO SOBREVIVE A FALHA: o <select> original continua no formulário, é ele que
   guarda o valor e é ele que o POST envia. O combobox é uma casca em cima. Se
   este arquivo não carregar, não rodar, ou vier velho de um cache, o usuário vê
   o select nativo e o formulário funciona igual. Por isso a casca é construída
   ANTES de esconder o original — nunca o contrário.

   Aplica-se sozinho a select com mais de LIMITE opções. Para forçar:
   data-busca="on" liga em qualquer tamanho, data-busca="off" desliga. */
(function () {
  'use strict';

  window.PCF_COMBO = '2026-08-20';

  var LIMITE = 8;               // abaixo disso, rolar a lista nativa é mais rápido
  var contador = 0;

  /* ---------- texto sem acento e sem caixa ----------
     "joao" tem de achar "João" e "cartolina" tem de achar "Cartolina A4".
     Sem isto, metade das buscas em português falharia por causa do acento. */
  function normalizar(texto) {
    return (texto || '')
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .toLowerCase().trim();
  }

  function elegivel(select) {
    if (select.multiple || select.size > 1) return false;      // v1: só escolha única
    if (select.disabled) return false;
    if (select.closest('.pcf-combo')) return false;            // já é de um combo
    var forcado = select.getAttribute('data-busca');
    if (forcado === 'off') return false;
    if (forcado === 'on') return true;
    return select.options.length > LIMITE;
  }

  /* Opções do select, achatando optgroup (o rótulo do grupo vira cabeçalho). */
  function lerOpcoes(select) {
    var lista = [];
    Array.prototype.forEach.call(select.children, function (filho) {
      if (filho.tagName === 'OPTGROUP') {
        lista.push({ grupo: true, texto: filho.label });
        Array.prototype.forEach.call(filho.children, function (opcao) {
          if (!opcao.disabled) lista.push({ valor: opcao.value, texto: opcao.text });
        });
      } else if (filho.tagName === 'OPTION' && !filho.disabled) {
        lista.push({ valor: filho.value, texto: filho.text });
      }
    });
    return lista;
  }

  function rotuloAtual(select) {
    var opcao = select.options[select.selectedIndex];
    if (!opcao) return '';
    // Opção vazia é placeholder ("---------"), não escolha de verdade.
    return opcao.value === '' ? '' : opcao.text;
  }

  function construir(select) {
    var id = 'pcf-combo-' + (++contador);
    var opcoes = lerOpcoes(select);

    var caixa = document.createElement('div');
    caixa.className = 'pcf-combo';

    var gatilho = document.createElement('button');
    gatilho.type = 'button';                  // nunca submeter o formulário
    gatilho.className = 'pcf-input pcf-combo-gatilho';
    gatilho.setAttribute('aria-haspopup', 'listbox');
    gatilho.setAttribute('aria-expanded', 'false');
    gatilho.id = id + '-gatilho';

    var textoGatilho = document.createElement('span');
    textoGatilho.className = 'pcf-combo-texto';
    gatilho.appendChild(textoGatilho);
    gatilho.insertAdjacentHTML('beforeend',
      '<svg class="pcf-combo-seta" width="15" height="15" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>');

    var painel = document.createElement('div');
    painel.className = 'pcf-combo-painel';
    painel.id = id + '-painel';

    var busca = document.createElement('input');
    busca.type = 'text';
    busca.className = 'pcf-combo-busca';
    busca.setAttribute('placeholder', 'Digite para procurar…');
    busca.setAttribute('autocomplete', 'off');
    busca.setAttribute('role', 'combobox');
    busca.setAttribute('aria-controls', id + '-lista');
    busca.setAttribute('aria-expanded', 'true');

    var lista = document.createElement('ul');
    lista.className = 'pcf-combo-lista';
    lista.id = id + '-lista';
    lista.setAttribute('role', 'listbox');

    var vazio = document.createElement('p');
    vazio.className = 'pcf-combo-vazio';
    vazio.textContent = 'Nada encontrado.';
    vazio.hidden = true;

    painel.appendChild(busca);
    painel.appendChild(lista);
    painel.appendChild(vazio);
    caixa.appendChild(gatilho);
    caixa.appendChild(painel);

    var itens = [];      // só os selecionáveis, na ordem visível
    var marcado = -1;

    function pintar(filtro) {
      lista.innerHTML = '';
      itens = [];
      var alvo = normalizar(filtro);
      opcoes.forEach(function (opcao) {
        if (opcao.grupo) {
          if (alvo) return;                  // filtrando, cabeçalho só atrapalha
          var titulo = document.createElement('li');
          titulo.className = 'pcf-combo-grupo';
          titulo.setAttribute('role', 'presentation');
          titulo.textContent = opcao.texto;
          lista.appendChild(titulo);
          return;
        }
        if (alvo && normalizar(opcao.texto).indexOf(alvo) === -1) return;
        var li = document.createElement('li');
        li.className = 'pcf-combo-opcao';
        li.setAttribute('role', 'option');
        li.id = id + '-op-' + itens.length;
        li.textContent = opcao.texto || '—';
        li.dataset.valor = opcao.valor;
        if (opcao.valor === select.value) {
          li.classList.add('is-escolhida');
          li.setAttribute('aria-selected', 'true');
        }
        li.addEventListener('mousedown', function (ev) {
          ev.preventDefault();               // não perder o foco antes do clique
          escolher(opcao.valor);
        });
        lista.appendChild(li);
        itens.push(li);
      });
      vazio.hidden = itens.length > 0;
      marcar(itens.length ? 0 : -1);
    }

    function marcar(indice) {
      if (marcado >= 0 && itens[marcado]) itens[marcado].classList.remove('is-ativa');
      marcado = indice;
      if (marcado >= 0 && itens[marcado]) {
        itens[marcado].classList.add('is-ativa');
        busca.setAttribute('aria-activedescendant', itens[marcado].id);
        // scrollIntoView cru rola a PÁGINA junto; aqui só a lista se move.
        var item = itens[marcado];
        var acima = item.offsetTop < lista.scrollTop;
        var abaixo = item.offsetTop + item.offsetHeight > lista.scrollTop + lista.clientHeight;
        if (acima) lista.scrollTop = item.offsetTop;
        else if (abaixo) lista.scrollTop = item.offsetTop + item.offsetHeight - lista.clientHeight;
      } else {
        busca.removeAttribute('aria-activedescendant');
      }
    }

    function mostrarEscolha() {
      var rotulo = rotuloAtual(select);
      textoGatilho.textContent = rotulo || (select.options[0] ? select.options[0].text : '');
      textoGatilho.classList.toggle('is-vazio', !rotulo);
    }

    function escolher(valor) {
      select.value = valor;
      // Evento de verdade: quem escuta `change` no select (inclusive o
      // onchange="this.form.submit()" dos filtros) precisa continuar sendo
      // avisado como se a pessoa tivesse mexido no select nativo.
      select.dispatchEvent(new Event('change', { bubbles: true }));
      mostrarEscolha();
      fechar();
      gatilho.focus();
    }

    function posicionar() {
      var r = gatilho.getBoundingClientRect();
      var altura = painel.offsetHeight || 260;
      var cabeEmbaixo = window.innerHeight - r.bottom > altura + 8;
      painel.style.left = r.left + 'px';
      painel.style.width = r.width + 'px';
      painel.style.top = cabeEmbaixo ? (r.bottom + 4) + 'px'
                                     : Math.max(4, r.top - altura - 4) + 'px';
    }

    function abrir() {
      if (painel.classList.contains('is-aberto')) return;
      // O painel vai para o BODY, não fica dentro da casca. Motivo concreto: no
      // Supply a linha do pedido vive num container com rolagem horizontal, e
      // um painel posicionado dentro dele era RECORTADO — aparecia só a primeira
      // opção. No body, com posição de tela, ele escapa de qualquer overflow.
      document.body.appendChild(painel);
      painel.classList.add('is-aberto');
      gatilho.setAttribute('aria-expanded', 'true');
      busca.value = '';
      pintar('');
      posicionar();
      busca.focus();
      // Enquanto aberto, acompanha a página: rolar sem reposicionar deixaria o
      // painel solto no meio da tela, longe do campo.
      window.addEventListener('scroll', posicionar, true);
      window.addEventListener('resize', posicionar);
    }

    function fechar() {
      painel.classList.remove('is-aberto');
      gatilho.setAttribute('aria-expanded', 'false');
      window.removeEventListener('scroll', posicionar, true);
      window.removeEventListener('resize', posicionar);
      // Volta para dentro da casca: assim uma linha removida leva o painel
      // embora em vez de deixá-lo órfão no body.
      if (painel.parentNode === document.body) caixa.appendChild(painel);
    }

    gatilho.addEventListener('click', function () {
      painel.classList.contains('is-aberto') ? fechar() : abrir();
    });

    busca.addEventListener('input', function () { pintar(busca.value); });

    busca.addEventListener('keydown', function (ev) {
      if (ev.key === 'ArrowDown') { ev.preventDefault(); marcar(Math.min(marcado + 1, itens.length - 1)); }
      else if (ev.key === 'ArrowUp') { ev.preventDefault(); marcar(Math.max(marcado - 1, 0)); }
      else if (ev.key === 'Enter') {
        ev.preventDefault();
        if (itens[marcado]) escolher(itens[marcado].dataset.valor);
      } else if (ev.key === 'Escape') { ev.preventDefault(); fechar(); gatilho.focus(); }
      else if (ev.key === 'Tab') { fechar(); }
    });

    document.addEventListener('mousedown', function (ev) {
      if (!caixa.contains(ev.target) && !painel.contains(ev.target)) fechar();
    });

    // O select segue sendo a verdade: se outro script mudar o valor, o rótulo
    // acompanha em vez de mentir.
    select.addEventListener('change', mostrarEscolha);

    mostrarEscolha();
    return caixa;
  }

  function ligar(select) {
    if (!elegivel(select)) return;
    var caixa;
    try {
      caixa = construir(select);
    } catch (erro) {
      // Falhou montando: deixa o select nativo em paz. Melhor sem busca do que
      // sem campo.
      if (window.console) console.warn('pcf-combo: não consegui montar', erro);
      return;
    }
    select.parentNode.insertBefore(caixa, select);
    caixa.appendChild(select);                        // o select vive DENTRO da casca
    // Escondido mas ainda focável: com display:none o navegador não consegue
    // focar um campo obrigatório inválido e a validação do HTML5 travaria com
    // "An invalid form control is not focusable".
    select.classList.add('pcf-combo-nativo');
    select.setAttribute('tabindex', '-1');
    select.setAttribute('data-combo-pronto', '1');
  }

  function varrer(raiz) {
    var selects = (raiz || document).querySelectorAll('select:not([data-combo-pronto])');
    Array.prototype.forEach.call(selects, ligar);
  }

  /* Linha clonada (o Supply adiciona pedido com cloneNode) vem com a casca
     duplicada e o marcador do original. Sem limpar, a linha nova mostraria um
     combobox morto, preso ao valor da linha copiada. */
  function limparClones(raiz) {
    var prontos = raiz.querySelectorAll('select[data-combo-pronto]');
    Array.prototype.forEach.call(prontos, function (select) {
      var casca = select.closest('.pcf-combo');
      if (!casca) return;
      casca.parentNode.insertBefore(select, casca);
      casca.remove();
      select.classList.remove('pcf-combo-nativo');
      select.removeAttribute('tabindex');
      select.removeAttribute('data-combo-pronto');
    });
  }

  function iniciar() {
    varrer(document);

    if (!window.MutationObserver) return;
    var observador = new MutationObserver(function (registros) {
      registros.forEach(function (registro) {
        Array.prototype.forEach.call(registro.addedNodes, function (no) {
          if (no.nodeType !== 1) return;
          limparClones(no);
          if (no.tagName === 'SELECT') {
            // O próprio nó é um select clonado: limparClones olha descendentes,
            // não a si mesmo. Sem isto a linha nova ficaria com a casca da
            // linha copiada, presa ao valor dela.
            if (no.hasAttribute('data-combo-pronto')) {
              var casca = no.closest('.pcf-combo');
              if (casca) {
                casca.parentNode.insertBefore(no, casca);
                casca.remove();
              }
              no.classList.remove('pcf-combo-nativo');
              no.removeAttribute('tabindex');
              no.removeAttribute('data-combo-pronto');
            }
            ligar(no);
          }
          varrer(no);
        });
      });
    });
    observador.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }

  window.pcfCombo = { varrer: varrer, ligar: ligar };
})();
