/* Tela de atendimento do Bazar.
 *
 * O critério de tudo aqui é um só: o voluntário está em pé, com uma fila na
 * frente, e cada clique a mais vira minuto de espera multiplicado por 150
 * crianças.
 *
 * Por isso:
 *  - a conta dos pontos aparece enquanto se marca, nunca depois;
 *  - o botão de finalizar desliga sozinho quando a sacola passa do saldo, em
 *    vez de deixar clicar e mostrar erro;
 *  - depois de finalizar, a tela volta sozinha para a busca, pronta para o
 *    próximo — ninguém precisa lembrar de limpar nada.
 */
(function () {
  'use strict';

  var cfg = window.BAZAR;
  if (!cfg) return;

  var busca = document.querySelector('[data-busca]');
  var sugestoes = document.querySelector('[data-sugestoes]');
  var painel = document.querySelector('[data-pessoa]');
  var elNome = document.querySelector('[data-nome]');
  var elSala = document.querySelector('[data-sala]');
  var elSaldo = document.querySelector('[data-saldo]');
  var elSaldoNumero = document.querySelector('[data-saldo-numero]');
  var elSaldoTexto = document.querySelector('[data-saldo-texto]');
  var elTamanhos = document.querySelector('[data-tamanhos]');
  var elBloqueio = document.querySelector('[data-bloqueio]');
  var elHistorico = document.querySelector('[data-historico]');
  var elLinhas = document.querySelector('[data-linhas]');
  var elTotal = document.querySelector('[data-total]');
  var elPecas = document.querySelector('[data-pecas]');
  var elErro = document.querySelector('[data-erro]');
  var elSucesso = document.querySelector('[data-sucesso]');
  var botaoFinalizar = document.querySelector('[data-finalizar]');
  var quemLevou = document.querySelector('[data-retirado-por]');
  var caixaNomeQuem = document.querySelector('[data-nome-de-quem]');
  var nomeQuem = document.querySelector('[data-retirado-nome]');
  var salaBazar = document.querySelector('[data-sala-bazar]');

  var atendido = null;      // {id, nome, saldo, ja_retirou, ...}
  var carrinho = {};        // {categoriaId: quantidade}
  var enviando = false;

  // ───────────────────────────── busca ─────────────────────────────
  var temporizador = null;

  busca.addEventListener('input', function () {
    window.clearTimeout(temporizador);
    var termo = busca.value.trim();
    if (termo.length < 2) {
      sugestoes.hidden = true;
      return;
    }
    temporizador = window.setTimeout(function () { procurar(termo); }, 200);
  });

  function procurar(termo) {
    fetch(cfg.urlBusca + '?q=' + encodeURIComponent(termo), {
      credentials: 'same-origin'
    })
      .then(function (r) { return r.json(); })
      .then(function (dados) {
        sugestoes.innerHTML = '';
        if (!dados.resultados || !dados.resultados.length) {
          sugestoes.hidden = true;
          return;
        }
        dados.resultados.forEach(function (pessoa) {
          var botao = document.createElement('button');
          botao.type = 'button';
          botao.className = 'bz-sugestao';
          botao.innerHTML = '<strong></strong><span></span>';
          botao.querySelector('strong').textContent = pessoa.nome;
          botao.querySelector('span').textContent = pessoa.sala;
          botao.addEventListener('click', function () { escolher(pessoa.id); });
          sugestoes.appendChild(botao);
        });
        sugestoes.hidden = false;
      })
      .catch(function () { sugestoes.hidden = true; });
  }

  // ──────────────────────────── a pessoa ────────────────────────────
  function escolher(id) {
    sugestoes.hidden = true;
    esconderRecados();

    fetch(cfg.urlSituacao.replace(/0\/$/, id + '/'), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (dados) {
        atendido = dados;
        carrinho = {};
        busca.value = '';
        desenharPessoa();
        painel.hidden = false;
        painel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
  }

  function desenharPessoa() {
    elNome.textContent = atendido.nome;
    elSala.textContent = atendido.sala;

    // Saldo. Na 2ª etapa não existe — mostrar zero ali enganaria o voluntário.
    elSaldo.className = 'bz-saldo';
    if (!cfg.descontaPontos) {
      elSaldo.classList.add('livre');
      elSaldoNumero.textContent = '∞';
      elSaldoTexto.textContent = '2ª etapa — sem limite de pontos';
    } else {
      elSaldoNumero.textContent = atendido.saldo;
      elSaldoTexto.textContent = 'ponto(s) disponíveis de ' + atendido.cota;
      if (atendido.saldo === 0) elSaldo.classList.add('zerado');
      else if (atendido.saldo <= 2) elSaldo.classList.add('pouco');
    }

    // Numeração da ficha: o dado que mais economiza tempo numa fila de roupa.
    var tamanhos = [];
    if (atendido.numeracoes.camisa) tamanhos.push(['Camisa', atendido.numeracoes.camisa]);
    if (atendido.numeracoes.calca) tamanhos.push(['Calça', atendido.numeracoes.calca]);
    if (atendido.numeracoes.calcado) tamanhos.push(['Calçado', atendido.numeracoes.calcado]);
    elTamanhos.innerHTML = '';
    tamanhos.forEach(function (par) {
      var caixa = document.createElement('span');
      caixa.className = 'bz-tamanho';
      caixa.innerHTML = '<span></span> ';
      caixa.querySelector('span').textContent = par[0];
      caixa.appendChild(document.createTextNode(par[1]));
      elTamanhos.appendChild(caixa);
    });
    elTamanhos.hidden = !tamanhos.length;

    // Já passou nesta etapa: a tela diz e trava, em vez de deixar registrar e
    // recusar no fim.
    elBloqueio.hidden = !atendido.ja_retirou;
    if (atendido.ja_retirou) {
      elBloqueio.textContent =
        atendido.nome + ' já finalizou a retirada desta etapa.';
    }

    elHistorico.innerHTML = '';
    (atendido.historico || []).forEach(function (registro) {
      var linha = document.createElement('li');
      linha.textContent = registro.etapa + ' · ' + registro.quando + ' · '
        + registro.itens.join(', ') + ' — ' + registro.pontos + ' pontos';
      elHistorico.appendChild(linha);
    });
    elHistorico.hidden = !(atendido.historico || []).length;

    document.querySelectorAll('[data-categoria]').forEach(function (botao) {
      botao.disabled = atendido.ja_retirou;
    });

    redesenharCarrinho();
  }

  // ─────────────────────────── o carrinho ───────────────────────────
  document.querySelectorAll('[data-categoria]').forEach(function (botao) {
    botao.addEventListener('click', function (evento) {
      if (!atendido || atendido.ja_retirou) return;
      var id = botao.dataset.categoria;
      // O "−" fica dentro do botão; clicar nele tira em vez de somar.
      if (evento.target.hasAttribute('data-menos')) {
        carrinho[id] = Math.max(0, (carrinho[id] || 0) - 1);
        if (!carrinho[id]) delete carrinho[id];
      } else {
        carrinho[id] = (carrinho[id] || 0) + 1;
      }
      esconderRecados();
      redesenharCarrinho();
    });
  });

  function totalDoCarrinho() {
    var pontos = 0;
    var pecas = 0;
    Object.keys(carrinho).forEach(function (id) {
      var botao = document.querySelector('[data-categoria="' + id + '"]');
      pontos += Number(botao.dataset.pontos) * carrinho[id];
      pecas += carrinho[id];
    });
    return { pontos: pontos, pecas: pecas };
  }

  function redesenharCarrinho() {
    document.querySelectorAll('[data-categoria]').forEach(function (botao) {
      var quantidade = carrinho[botao.dataset.categoria] || 0;
      var conta = botao.querySelector('[data-conta]');
      var menos = botao.querySelector('[data-menos]');
      botao.classList.toggle('tem', quantidade > 0);
      conta.textContent = quantidade;
      conta.hidden = !quantidade;
      menos.hidden = !quantidade;
    });

    var soma = totalDoCarrinho();
    elTotal.textContent = soma.pontos;
    elPecas.textContent = soma.pecas;

    elLinhas.innerHTML = '';
    Object.keys(carrinho).forEach(function (id) {
      var botao = document.querySelector('[data-categoria="' + id + '"]');
      var nome = botao.querySelector('.bz-categoria-nome').textContent;
      var pontos = Number(botao.dataset.pontos) * carrinho[id];
      var linha = document.createElement('div');
      linha.className = 'bz-resumo-linha';
      linha.innerHTML = '<span></span><span></span>';
      linha.children[0].textContent = nome + ' × ' + carrinho[id];
      linha.children[1].textContent = pontos + ' pontos';
      elLinhas.appendChild(linha);
    });

    // Passou do saldo: o botão desliga e a tela explica, em vez de deixar
    // clicar para receber recusa do servidor com a criança esperando.
    var estoura = cfg.descontaPontos && atendido && soma.pontos > atendido.saldo;
    botaoFinalizar.disabled = !soma.pecas || estoura || atendido.ja_retirou || enviando;

    if (estoura) {
      elErro.hidden = false;
      elErro.textContent = 'A sacola soma ' + soma.pontos + ' pontos e o saldo é '
        + atendido.saldo + '. Tire alguma peça.';
    } else if (!enviando) {
      elErro.hidden = true;
    }
  }

  // ────────────────────────── quem levou ──────────────────────────
  quemLevou.addEventListener('change', function () {
    // O nome só é pedido quando não foi o próprio atendido — campo a menos na
    // maioria dos atendimentos.
    caixaNomeQuem.hidden = quemLevou.value === 'ATENDIDO';
  });

  // ─────────────────────────── finalizar ───────────────────────────
  botaoFinalizar.addEventListener('click', function () {
    if (!atendido || enviando) return;
    enviando = true;
    botaoFinalizar.disabled = true;
    botaoFinalizar.textContent = 'Registrando...';

    var dados = new FormData();
    dados.append('atendido', atendido.id);
    dados.append('retirado_por', quemLevou.value);
    dados.append('retirado_por_nome', nomeQuem.value);
    dados.append('sala_do_bazar', salaBazar.value);
    Object.keys(carrinho).forEach(function (id) {
      dados.append('qtd_' + id, carrinho[id]);
    });

    fetch(cfg.urlFinalizar, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': cfg.csrf },
      body: dados
    })
      .then(function (r) { return r.json().then(function (c) { return { ok: r.ok, corpo: c }; }); })
      .then(function (resposta) {
        if (!resposta.ok) {
          elErro.hidden = false;
          elErro.textContent = resposta.corpo.erro || 'Não consegui registrar.';
          return;
        }
        var recado = resposta.corpo.nome + ': ' + resposta.corpo.pecas
          + ' peça(s), ' + resposta.corpo.total + ' pontos. Pode entregar a sacola.';
        if (resposta.corpo.alertas && resposta.corpo.alertas.length) {
          // Estoque estourado AVISA e não bloqueia — a peça já está na mão do
          // voluntário, e a contagem de bazar é aproximada.
          recado += ' Atenção ao estoque: ' + resposta.corpo.alertas.join(' ');
        }
        elSucesso.hidden = false;
        elSucesso.textContent = recado;

        // Volta para a busca, pronta para o próximo da fila.
        atendido = null;
        carrinho = {};
        painel.hidden = true;
        busca.value = '';
        busca.focus();
      })
      .catch(function () {
        elErro.hidden = false;
        elErro.textContent = 'Falha de conexão. Confira antes de tentar de novo.';
      })
      .finally(function () {
        enviando = false;
        botaoFinalizar.textContent = 'Finalizar retirada';
        redesenharCarrinho();
      });
  });

  function esconderRecados() {
    elErro.hidden = true;
    elSucesso.hidden = true;
  }

  busca.focus();
})();
