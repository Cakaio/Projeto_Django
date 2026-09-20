/* Bazar — a tela de atendimento como um caixa de loja.
 *
 * Três passos, o saldo sempre à vista descendo, todo toque com volta, e nada
 * grava sem uma conferência com o nome da criança na frente.
 *
 * A REGRA DE OURO deste arquivo, que a versão anterior violava e foi o defeito
 * mais caro da tela:
 *
 *     NENHUMA FUNÇÃO QUE REDESENHA ESCONDE UM RECADO.
 *
 * Antes, `redesenharCarrinho()` fazia `elErro.hidden = true`, e era chamado no
 * `.finally` do envio — logo depois de a mensagem de erro ser escrita. Efeito:
 * "João já finalizou a retirada desta etapa" e "Falha de conexão" eram escritos
 * e apagados no mesmo piscar. O voluntário apertava Finalizar, a tela não
 * respondia, e ele apertava de novo. Mostrar e esconder recado é
 * responsabilidade de quem SABE o que aconteceu, nunca de quem desenha.
 *
 * ES5, sem build: o projeto não tem bundler no front.
 */
(function () {
  'use strict';

  var cfg = window.BAZAR;
  if (!cfg) return;

  // ───────────────────────────── elementos ─────────────────────────────
  var q = function (sel) { return document.querySelector(sel); };
  var todos = function (sel) {
    return Array.prototype.slice.call(document.querySelectorAll(sel));
  };

  var busca = q('[data-busca]');
  var sugestoes = q('[data-sugestoes]');
  var recadoBusca = q('[data-recado-busca]');
  var passoBusca = q('[data-passo-busca]');
  var passoPecas = q('[data-passo-pecas]');

  var ficha = q('[data-ficha]');
  var elNome = q('[data-nome]');
  var elSub = q('[data-sub]');
  var elTamanhos = q('[data-tamanhos]');
  var elJaPassou = q('[data-ja-passou]');
  var grade = q('[data-grade]');
  var tituloPecas = q('[data-titulo-pecas]');

  var rodape = q('[data-rodape]');
  var elSaldoNumero = q('[data-saldo-numero]');
  var elSaldoTexto = q('[data-saldo-texto]');
  var elBarra = q('[data-barra]');
  var elUltimo = q('[data-ultimo]');
  var btnDesfazer = q('[data-desfazer]');
  var elTotal = q('[data-total]');
  var elPecas = q('[data-pecas]');
  var btnConferir = q('[data-conferir]');
  var elLevouTexto = q('[data-levou-texto]');

  var folha = q('[data-folha]');
  var folhaNome = q('[data-folha-nome]');
  var folhaLinhas = q('[data-folha-linhas]');
  var folhaTotal = q('[data-folha-total]');
  var folhaSobra = q('[data-folha-sobra]');
  var selLevou = q('[data-levou]');
  var campoNome = q('[data-campo-nome]');
  var inpLevouNome = q('[data-levou-nome]');
  var recadoFolha = q('[data-recado-folha]');
  var btnConfirmar = q('[data-confirmar]');
  var btnVoltar = q('[data-voltar]');

  var telaVisitante = q('[data-visitante]');
  var inpVisNome = q('[data-visitante-nome]');
  var inpVisMotivo = q('[data-visitante-motivo]');
  var recadoVisitante = q('[data-recado-visitante]');

  var telaCaixa = q('[data-caixa]');
  var chipCaixa = q('[data-abrir-caixa]');
  var nomeCaixa = q('[data-caixa-nome]');

  if (!busca) return;

  // ───────────────────────────── estado ─────────────────────────────
  var atendido = null;      // ficha vinda do servidor, ou visitante
  var carrinho = {};        // {categoriaId: quantidade}
  var ordemDosToques = [];  // para o desfazer do último
  var token = null;         // chave do atendimento atual
  var enviando = false;
  var ultimoRecibo = null;  // {retiradaId, ate} enquanto o desfazer vale
  var temporizador = null;

  var CHAVE_CAIXA = 'bazar:caixa';

  // ───────────────────────────── utilidades ─────────────────────────────
  function novoToken() {
    if (window.crypto && window.crypto.randomUUID) {
      return window.crypto.randomUUID();
    }
    // Sem randomUUID (navegador antigo, http): data + aleatório basta, porque o
    // token só precisa ser único dentro de um Bazar.
    return 'bz-' + Date.now() + '-' + Math.floor(Math.random() * 1e9);
  }

  function mostrarRecado(elemento, classe, texto, rotuloBotao, aoClicar) {
    elemento.className = 'bz-recado ' + classe;
    elemento.textContent = texto;
    elemento.hidden = false;
    if (rotuloBotao) {
      var botao = document.createElement('button');
      botao.type = 'button';
      botao.textContent = rotuloBotao;
      botao.addEventListener('click', aoClicar);
      elemento.appendChild(document.createElement('br'));
      elemento.appendChild(botao);
    }
  }

  function esconderRecado(elemento) { elemento.hidden = true; }

  function pedirCsrf(corpo) {
    return fetch(cfg.urlFinalizar, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': cfg.csrf },
      body: corpo
    });
  }

  // ───────────────────────────── o caixa (sala) ─────────────────────────────
  function caixaEscolhido() {
    try { return window.localStorage.getItem(CHAVE_CAIXA); } catch (e) { return null; }
  }

  function guardarCaixa(id, nome) {
    try {
      window.localStorage.setItem(CHAVE_CAIXA, id);
      window.localStorage.setItem(CHAVE_CAIXA + ':nome', nome);
    } catch (e) { /* modo privado: segue sem lembrar */ }
    if (nomeCaixa) nomeCaixa.textContent = nome;
  }

  function nomeDoCaixa() {
    try { return window.localStorage.getItem(CHAVE_CAIXA + ':nome'); } catch (e) { return null; }
  }

  if (telaCaixa) {
    todos('[data-sala]').forEach(function (botao) {
      botao.addEventListener('click', function () {
        guardarCaixa(botao.dataset.sala, botao.textContent.trim());
        telaCaixa.hidden = true;
      });
    });
    if (chipCaixa) {
      chipCaixa.addEventListener('click', function () { telaCaixa.hidden = false; });
    }
    // Sair sem escolher. O chip "Caixa: escolher" continua no topo, entao a
    // decisao nao se perde — so deixa de barrar a fila.
    var depois = q('[data-caixa-depois]');
    if (depois) {
      depois.addEventListener('click', function () { telaCaixa.hidden = true; });
    }
    var guardado = nomeDoCaixa();
    if (guardado && nomeCaixa) {
      nomeCaixa.textContent = guardado;
    } else {
      // Primeira vez no aparelho: pergunta antes da fila começar.
      telaCaixa.hidden = false;
    }
  }

  // ───────────────────────────── busca ─────────────────────────────
  busca.addEventListener('input', function () {
    var termo = busca.value.trim();
    window.clearTimeout(temporizador);

    if (termo.length < 2) {
      sugestoes.hidden = true;
      esconderRecado(recadoBusca);
      return;
    }
    temporizador = window.setTimeout(function () { procurar(termo); }, 200);
  });

  function procurar(termo) {
    sugestoes.innerHTML = '<p class="bz-estado-busca">Procurando…</p>';
    sugestoes.hidden = false;

    fetch(cfg.urlBusca + '?q=' + encodeURIComponent(termo),
          { credentials: 'same-origin' })
      // O STATUS IMPORTA. Sem esta linha, um 409 "Nenhum Bazar aberto" virava
      // `resultados` indefinido, virava lista vazia, e a tela ACUSAVA A
      // CRIANCA DE NAO EXISTIR quando o problema era do sistema.
      .then(function (r) {
        return r.json().then(function (dados) {
          if (!r.ok) throw new Error(dados.erro || 'Falha na busca.');
          return dados;
        });
      })
      .then(function (dados) {
        if (dados.aviso) { mostrarRecado(recadoBusca, 'aviso', dados.aviso); }
        else { esconderRecado(recadoBusca); }
        desenharSugestoes(dados.resultados || [], termo);
      })
      .catch(function (erro) {
        // Sem .catch a lista ficava em "Procurando…" para sempre.
        // A mensagem do servidor vem na frente: "Nenhum Bazar aberto" e uma
        // informacao acionavel, "sem conexao" nao.
        var texto = (erro && erro.message && erro.message !== 'Failed to fetch')
          ? erro.message
          : 'Sem conexão agora. Continue pelo papel — o kit impresso está ' +
            'com a coordenação.';
        sugestoes.innerHTML = '';
        var aviso = document.createElement('p');
        aviso.className = 'bz-estado-busca';
        aviso.textContent = texto;
        sugestoes.appendChild(aviso);
      });
  }

  function desenharSugestoes(lista, termo) {
    sugestoes.innerHTML = '';

    if (!lista.length) {
      var vazio = document.createElement('div');
      vazio.className = 'bz-estado-busca';
      vazio.textContent = 'Ninguém com "' + termo + '". Confira a escrita, ' +
        'tente o sobrenome, ou registre como quem veio sem cadastro.';
      var botao = document.createElement('button');
      botao.type = 'button';
      botao.className = 'bz-outra';
      botao.textContent = 'Registrar quem veio sem cadastro';
      botao.addEventListener('click', abrirVisitante);
      vazio.appendChild(botao);
      sugestoes.appendChild(vazio);
      return;
    }

    lista.forEach(function (pessoa) {
      var botao = document.createElement('button');
      botao.type = 'button';
      botao.className = 'bz-sugestao';

      var nome = document.createElement('span');
      nome.className = 'bz-sugestao-nome';
      nome.textContent = pessoa.nome;

      // Idade e numerações JUNTO do nome: é o que separa duas "Maria Eduarda"
      // da mesma salinha, que sem isto são duas linhas idênticas.
      var partes = [pessoa.sala];
      if (pessoa.idade !== null && pessoa.idade !== undefined) {
        partes.push(pessoa.idade + ' anos');
      }
      var n = pessoa.numeracoes || {};
      if (n.camisa) partes.push('camisa ' + n.camisa);
      if (n.calcado) partes.push('calçado ' + n.calcado);

      var sub = document.createElement('span');
      sub.className = 'bz-sugestao-sub';
      sub.textContent = partes.join(' · ');

      botao.appendChild(nome);
      botao.appendChild(sub);
      botao.addEventListener('click', function () { escolher(pessoa.id); });
      sugestoes.appendChild(botao);
    });
  }

  function escolher(id) {
    sugestoes.innerHTML = '<p class="bz-estado-busca">Abrindo…</p>';

    fetch(cfg.urlSituacao.replace(/0\/$/, id + '/'), { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('situacao');
        return r.json();
      })
      .then(function (dados) {
        sugestoes.hidden = true;
        abrirAtendimento(dados);
      })
      .catch(function () {
        // A versão anterior não tinha .catch: o voluntário tocava no nome e
        // NADA acontecia — nem mensagem, nem mudança de tela.
        sugestoes.hidden = true;
        mostrarRecado(recadoBusca, 'erro',
          'Não consegui abrir a ficha. Toque em tentar de novo.',
          'Tentar de novo', function () {
            esconderRecado(recadoBusca);
            escolher(id);
          });
      });
  }

  // ───────────────────────────── atendimento ─────────────────────────────
  function abrirAtendimento(dados) {
    atendido = dados;
    carrinho = {};
    ordemDosToques = [];
    token = novoToken();
    ultimoRecibo = null;

    busca.value = '';
    esconderRecado(recadoBusca);

    // Quem levou volta ao PADRÃO a cada criança. Antes não era limpo: uma vez
    // marcado "Outra pessoa autorizada — Maria", a manhã inteira saía com a
    // Maria colada em crianças que vieram sozinhas.
    selLevou.selectedIndex = 0;
    inpLevouNome.value = '';
    campoNome.hidden = true;
    atualizarLevouTexto();

    elNome.textContent = dados.nome;
    var sub = [dados.sala];
    if (dados.idade !== null && dados.idade !== undefined) sub.push(dados.idade + ' anos');
    elSub.textContent = sub.join(' · ');

    desenharTamanhos(dados.numeracoes || {});

    // Criança que já passou: a grade NÃO é desenhada, e uma frase inteira toma
    // o lugar. Antes os botões ficavam idênticos aos clicáveis com
    // `disabled = true`, e o leigo tocava três vezes e concluía que travou.
    var jaPassou = !!dados.ja_retirou;
    ficha.classList.toggle('ja-passou', jaPassou);
    elJaPassou.hidden = !jaPassou;
    grade.hidden = jaPassou;
    tituloPecas.hidden = jaPassou;
    if (jaPassou) {
      elJaPassou.textContent = dados.recado_ja_retirou ||
        (dados.nome + ' já levou a sacola desta etapa.');
    }

    passoBusca.hidden = true;
    passoPecas.hidden = false;
    rodape.hidden = jaPassou;

    redesenhar();
  }

  function desenharTamanhos(numeracoes) {
    elTamanhos.innerHTML = '';
    var pares = [
      ['camisa', numeracoes.camisa],
      ['calça', numeracoes.calca],
      ['calçado', numeracoes.calcado]
    ];
    var algum = false;
    pares.forEach(function (par) {
      if (!par[1]) return;
      algum = true;
      var chip = document.createElement('span');
      chip.className = 'bz-tamanho';
      chip.innerHTML = '<span></span> ';
      chip.children[0].textContent = par[0];
      chip.appendChild(document.createTextNode(par[1]));
      elTamanhos.appendChild(chip);
    });
    elTamanhos.hidden = !algum;
  }

  function voltarParaBusca() {
    atendido = null;
    carrinho = {};
    ordemDosToques = [];
    token = null;
    passoPecas.hidden = true;
    passoBusca.hidden = false;
    rodape.hidden = true;
    sugestoes.hidden = true;
    busca.value = '';
  }

  q('[data-trocar]').addEventListener('click', voltarParaBusca);

  // ───────────────────────────── peças ─────────────────────────────
  todos('[data-bloco]').forEach(function (bloco) {
    var id = bloco.dataset.categoria;

    bloco.querySelector('[data-mais]').addEventListener('click', function () {
      if (!cabeMais(id)) return;
      carrinho[id] = (carrinho[id] || 0) + 1;
      ordemDosToques.push(id);
      redesenhar();
    });

    bloco.querySelector('[data-menos]').addEventListener('click', function () {
      if (!carrinho[id]) return;
      carrinho[id] -= 1;
      if (!carrinho[id]) delete carrinho[id];
      for (var i = ordemDosToques.length - 1; i >= 0; i--) {
        if (ordemDosToques[i] === id) { ordemDosToques.splice(i, 1); break; }
      }
      redesenhar();
    });
  });

  function pontosDe(id) {
    var bloco = document.querySelector('[data-categoria="' + id + '"]');
    return Number(bloco.dataset.pontos);
  }

  function nomeDe(id) {
    var bloco = document.querySelector('[data-categoria="' + id + '"]');
    return bloco.querySelector('.bz-mais-nome').textContent.trim();
  }

  function somaDoCarrinho() {
    var pontos = 0, pecas = 0;
    Object.keys(carrinho).forEach(function (id) {
      pontos += pontosDe(id) * carrinho[id];
      pecas += carrinho[id];
    });
    return { pontos: pontos, pecas: pecas };
  }

  function saldoAtual() {
    if (!cfg.descontaPontos || !atendido) return null;
    return (atendido.saldo || 0) - somaDoCarrinho().pontos;
  }

  function cabeMais(id) {
    var restante = saldoAtual();
    if (restante === null) return true;
    return pontosDe(id) <= restante;
  }

  btnDesfazer.addEventListener('click', function () {
    var id = ordemDosToques.pop();
    if (!id) return;
    carrinho[id] -= 1;
    if (!carrinho[id]) delete carrinho[id];
    redesenhar();
  });

  // ───────────────────────────── desenho ─────────────────────────────
  // Esta função NÃO esconde recado nenhum. Ver a regra de ouro no topo.
  function redesenhar() {
    var soma = somaDoCarrinho();
    var restante = saldoAtual();

    todos('[data-bloco]').forEach(function (bloco) {
      var id = bloco.dataset.categoria;
      var quantidade = carrinho[id] || 0;
      bloco.classList.toggle('tem', quantidade > 0);
      bloco.querySelector('[data-conta]').textContent = quantidade;

      // Impossibilidade vira FRASE dentro do botão, com o número exato do que
      // falta — nunca um botão cinza sem explicação.
      var cabe = cabeMais(id);
      bloco.classList.toggle('nao-cabe', !cabe);
      if (!cabe) {
        var falta = pontosDe(id) - restante;
        bloco.querySelector('[data-recusa]').textContent =
          'não cabe: falta ' + falta + ' ponto' + (falta === 1 ? '' : 's');
      }
    });

    elTotal.textContent = soma.pontos;
    elPecas.textContent = soma.pecas;

    var ultimo = ordemDosToques[ordemDosToques.length - 1];
    elUltimo.textContent = ultimo ? ('último: + ' + nomeDe(ultimo)) : 'Sacola vazia';
    btnDesfazer.hidden = !ultimo;

    // O SALDO DESCE. Era escrito uma vez e congelava, enquanto o que se mexia
    // era o total da sacola subindo noutro bloco — dois números grandes
    // competindo, e o leigo olhava para o errado.
    rodape.className = 'bz-rodape';
    if (restante === null) {
      elSaldoNumero.textContent = soma.pecas;
      elSaldoTexto.textContent = 'peça(s) — nesta etapa não há limite de pontos';
      rodape.classList.add('livre');
      elBarra.style.width = '0%';
    } else {
      elSaldoNumero.textContent = restante;
      elSaldoTexto.textContent = 'de ' + (atendido ? atendido.cota : cfg.cota) +
        ' pontos ainda sobram';
      if (restante === 0) rodape.classList.add('zerado');
      else if (restante <= 2) rodape.classList.add('pouco');
      var usados = (atendido ? atendido.cota : cfg.cota) - restante;
      var cota = (atendido ? atendido.cota : cfg.cota) || 1;
      elBarra.style.width = Math.min(100, (usados / cota) * 100) + '%';
    }

    btnConferir.disabled = !soma.pecas || enviando;
  }

  // ───────────────────────────── quem levou ─────────────────────────────
  function atualizarLevouTexto() {
    var rotulo = selLevou.options[selLevou.selectedIndex].textContent.trim();
    if (inpLevouNome.value.trim()) rotulo += ' — ' + inpLevouNome.value.trim();
    elLevouTexto.textContent = rotulo.toLowerCase();
  }

  selLevou.addEventListener('change', function () {
    // O nome só é pedido quando não foi o próprio atendido: um campo a menos
    // no caso comum, que é a maioria da fila.
    campoNome.hidden = selLevou.value === 'ATENDIDO';
    if (campoNome.hidden) inpLevouNome.value = '';
    atualizarLevouTexto();
  });
  inpLevouNome.addEventListener('input', atualizarLevouTexto);

  // ───────────────────────────── folha de conferência ─────────────────────────────
  btnConferir.addEventListener('click', function () {
    if (btnConferir.disabled) return;
    abrirFolha();
  });

  function abrirFolha() {
    var soma = somaDoCarrinho();
    folhaNome.textContent = atendido ? atendido.nome : '';
    folhaLinhas.innerHTML = '';

    Object.keys(carrinho).forEach(function (id) {
      var linha = document.createElement('div');
      linha.className = 'bz-folha-linha';
      linha.innerHTML = '<span></span><span></span>';
      linha.children[0].textContent = nomeDe(id) + ' × ' + carrinho[id];
      linha.children[1].textContent = (pontosDe(id) * carrinho[id]) + ' ponto(s)';
      folhaLinhas.appendChild(linha);
    });

    folhaTotal.textContent = soma.pontos;
    var restante = saldoAtual();
    folhaSobra.textContent = restante === null
      ? 'Nesta etapa não há limite de pontos.'
      : ('Vão sobrar ' + restante + ' de ' + atendido.cota + ' pontos.');

    esconderRecado(recadoFolha);
    folha.hidden = false;
  }

  btnVoltar.addEventListener('click', function () { folha.hidden = true; });

  btnConfirmar.addEventListener('click', function () { gravar(false); });

  // ───────────────────────────── veio e não levou nada ─────────────────────────────
  q('[data-sem-retirada]').addEventListener('click', function () {
    if (!atendido) return;
    if (somaDoCarrinho().pecas) {
      mostrarRecado(recadoBusca, 'aviso',
        'A sacola tem peça marcada. Tire as peças antes de registrar que não ' +
        'levou nada.');
      return;
    }
    gravar(true);
  });

  // ───────────────────────────── visitante ─────────────────────────────
  function abrirVisitante() {
    sugestoes.hidden = true;
    inpVisNome.value = '';
    inpVisMotivo.value = '';
    esconderRecado(recadoVisitante);
    telaVisitante.hidden = false;
  }

  q('[data-visitante-cancelar]').addEventListener('click', function () {
    telaVisitante.hidden = true;
  });

  q('[data-visitante-ok]').addEventListener('click', function () {
    var nome = inpVisNome.value.trim();
    if (!nome) {
      mostrarRecado(recadoVisitante, 'erro',
        'Escreva o nome da criança. Sem nome, o registro fica sem como ser ' +
        'conferido depois.');
      return;
    }
    telaVisitante.hidden = true;
    abrirAtendimento({
      nome: nome,
      sala: 'fora do cadastro',
      idade: null,
      saldo: cfg.cota,
      cota: cfg.cota,
      ja_retirou: false,
      numeracoes: {},
      visitante_nome: nome,
      visitante_motivo: inpVisMotivo.value.trim()
    });
  });

  // ───────────────────────────── gravar ─────────────────────────────
  function gravar(semRetirada) {
    if (enviando) return;
    enviando = true;
    btnConfirmar.disabled = true;
    btnConfirmar.textContent = 'Gravando…';

    var corpo = new URLSearchParams();
    if (atendido.visitante_nome) {
      corpo.set('visitante_nome', atendido.visitante_nome);
      corpo.set('visitante_motivo', atendido.visitante_motivo || '');
    } else {
      corpo.set('atendido', atendido.id);
    }
    corpo.set('token', token);
    corpo.set('retirado_por', selLevou.value);
    corpo.set('retirado_por_nome', inpLevouNome.value.trim());
    if (semRetirada) corpo.set('sem_retirada', '1');
    var caixa = caixaEscolhido();
    if (caixa) corpo.set('sala', caixa);
    Object.keys(carrinho).forEach(function (id) {
      corpo.set('qtd_' + id, carrinho[id]);
    });

    pedirCsrf(corpo)
      .then(function (r) {
        return r.json().then(function (c) { return { ok: r.ok, corpo: c }; });
      })
      .then(function (resposta) {
        if (!resposta.ok) {
          // O recado FICA na tela até alguém agir. Nada abaixo o apaga.
          mostrarRecado(recadoFolha, 'erro',
            resposta.corpo.erro || 'Não consegui registrar.');
          return;
        }
        concluir(resposta.corpo, semRetirada);
      })
      .catch(function () {
        mostrarRecado(recadoFolha, 'erro',
          'Falha de conexão — NADA foi gravado. Confira antes de tentar de novo, ' +
          'ou registre no papel.');
      })
      .then(function () {
        // Só devolve o botão. NÃO chama redesenhar(), que era exatamente o que
        // apagava a mensagem de erro escrita acima.
        enviando = false;
        btnConfirmar.disabled = false;
        btnConfirmar.textContent = 'Confirmar a entrega';
      });
  }

  function concluir(dados, semRetirada) {
    folha.hidden = true;
    ultimoRecibo = { id: dados.retirada };

    var texto = semRetirada
      ? (dados.nome + ' veio e não levou nada. Registrado.')
      : (dados.nome + ' levou ' + dados.pecas + ' peça(s), ' +
         dados.total + ' ponto(s). Pode entregar a sacola.');

    mostrarRecado(recadoBusca, 'ok', texto, 'Desfazer este registro',
      function () { desfazerRegistro(dados.retirada); });

    if (dados.alertas && dados.alertas.length) {
      var aviso = document.createElement('span');
      aviso.style.display = 'block';
      aviso.style.marginTop = '.4rem';
      aviso.textContent = 'Atenção ao estoque: ' + dados.alertas.join(' ') +
        ' A entrega foi registrada assim mesmo.';
      recadoBusca.appendChild(aviso);
    }

    // O desfazer vale por alguns minutos; depois some sozinho.
    window.setTimeout(function () {
      if (ultimoRecibo && ultimoRecibo.id === dados.retirada) {
        esconderRecado(recadoBusca);
        ultimoRecibo = null;
      }
    }, (cfg.minutosParaDesfazer || 2) * 60 * 1000);

    voltarParaBusca();
  }

  function desfazerRegistro(id) {
    var motivo = window.prompt(
      'Por que está desfazendo? (fica registrado)', 'marquei errado');
    if (motivo === null) return;

    var corpo = new URLSearchParams();
    corpo.set('motivo', motivo);

    fetch(cfg.urlCancelar.replace(/0\/$/, id + '/'), {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': cfg.csrf },
      body: corpo
    })
      .then(function (r) {
        return r.json().then(function (c) { return { ok: r.ok, corpo: c }; });
      })
      .then(function (resposta) {
        if (!resposta.ok) {
          mostrarRecado(recadoBusca, 'erro',
            resposta.corpo.erro || 'Não consegui desfazer.');
          return;
        }
        ultimoRecibo = null;
        mostrarRecado(recadoBusca, 'aviso',
          'Registro desfeito. A criança pode passar de novo.');
      })
      .catch(function () {
        mostrarRecado(recadoBusca, 'erro',
          'Falha de conexão ao desfazer. O registro CONTINUA valendo.');
      });
  }

  // Foco inicial só no desktop: no iOS, focar fora de um gesto do usuário não
  // abre o teclado e ainda rola a página sozinha.
  if (!('ontouchstart' in window)) busca.focus();
})();
