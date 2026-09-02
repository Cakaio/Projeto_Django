/* Estúdio: editor de página com posicionamento livre.
 *
 * A folha tem tamanho fixo em px (A4 a 96 dpi) e só a visualização escola —
 * por isso toda conta aqui converte o movimento do mouse pela escala antes de
 * mexer na coordenada. Sem isso, arrastar 10px na tela moveria 14px na folha e
 * nada pousaria onde a pessoa soltou.
 *
 * SOBRE A DUPLICAÇÃO DE `cssDeEstilo`: o servidor tem a mesma tradução em
 * estudio/models.py, e ela é a autoritativa — é a que desenha a página
 * publicada e o PDF. A cópia aqui existe só para a pré-visualização responder
 * na hora em que a pessoa mexe no controle; ao recarregar, o servidor manda.
 * Se as duas divergirem, a que está certa é a do Python.
 */
(function () {
  'use strict';

  window.PCF_ESTUDIO = '2026-09-02';

  var raiz = document.getElementById('estudio');
  if (!raiz) return;

  var dadosBrutos = document.getElementById('estudio-estado');
  if (!dadosBrutos) return;

  var estado = JSON.parse(dadosBrutos.textContent);
  var paginaAtual = estado.paginas[0] ? String(estado.paginas[0].id) : null;
  var selecionado = null;
  var sujo = false;
  var proximoIdLocal = -1;   // negativo = elemento que ainda não existe no banco

  var palco = raiz.querySelector('[data-palco]');
  var painel = raiz.querySelector('[data-painel]');
  var avisoSalvar = raiz.querySelector('[data-aviso-salvar]');

  var LIMITE = parseInt(raiz.dataset.limite || '20000', 10);
  var FONTES = {
    display: "'Trebuchet MS', 'Segoe UI', Verdana, sans-serif",
    corpo: "'Segoe UI', system-ui, -apple-system, sans-serif",
    serif: "Georgia, 'Times New Roman', serif",
    mono: "'Consolas', 'Courier New', monospace"
  };

  /* ── utilidades ───────────────────────────────────────────────────── */

  function paginaPorId(id) {
    for (var i = 0; i < estado.paginas.length; i++) {
      if (String(estado.paginas[i].id) === String(id)) return estado.paginas[i];
    }
    return null;
  }

  function elementoPorId(pagina, id) {
    for (var i = 0; i < pagina.elementos.length; i++) {
      if (String(pagina.elementos[i].id) === String(id)) return pagina.elementos[i];
    }
    return null;
  }

  function preso(valor, minimo, maximo) {
    return Math.max(minimo, Math.min(maximo, Math.round(valor)));
  }

  function marcarSujo() {
    sujo = true;
    if (avisoSalvar) {
      avisoSalvar.textContent = 'Alterações não salvas';
      avisoSalvar.dataset.estado = 'sujo';
    }
  }

  function marcarLimpo(quantos) {
    sujo = false;
    if (avisoSalvar) {
      avisoSalvar.textContent = quantos === undefined
        ? 'Tudo salvo' : 'Salvo (' + quantos + ' elementos)';
      avisoSalvar.dataset.estado = 'limpo';
    }
  }

  function csrf() {
    var campo = document.querySelector('[name=csrfmiddlewaretoken]');
    return campo ? campo.value : '';
  }

  /* ── estilo -> CSS (só para a pré-visualização; ver nota do topo) ─── */

  var COR = /^#[0-9a-fA-F]{3,8}$|^rgba?\([\d\s.,%]+\)$|^transparent$/;
  var ALINHAMENTOS = ['left', 'center', 'right', 'justify'];
  var AJUSTES = ['cover', 'contain', 'fill', 'none'];

  function corValida(valor) {
    return (typeof valor === 'string' && COR.test(valor.trim())) ? valor.trim() : null;
  }

  function numero(valor, minimo, maximo) {
    var n = parseFloat(valor);
    if (isNaN(n)) return null;
    return Math.max(minimo, Math.min(maximo, n));
  }

  function cssDeEstilo(estilo) {
    var e = estilo || {};
    var partes = [];

    var cor = corValida(e.cor);
    if (cor) partes.push('color:' + cor);
    var fundo = corValida(e.fundo);
    if (fundo) partes.push('background:' + fundo);

    if (FONTES[e.fonte]) partes.push('font-family:' + FONTES[e.fonte]);

    var pares = [
      ['tamanho', 'font-size', 4, 400, 'px'],
      ['raio', 'border-radius', 0, 999, 'px'],
      ['letra_espaco', 'letter-spacing', -10, 40, 'px'],
      ['entrelinha', 'line-height', 0.6, 4, ''],
      ['opacidade', 'opacity', 0, 1, '']
    ];
    pares.forEach(function (p) {
      var v = numero(e[p[0]], p[2], p[3]);
      if (v !== null) partes.push(p[1] + ':' + v + p[4]);
    });

    var peso = numero(e.peso, 100, 900);
    if (peso !== null) partes.push('font-weight:' + (Math.floor(peso / 100) * 100));

    if (ALINHAMENTOS.indexOf(e.alinhamento) >= 0) partes.push('text-align:' + e.alinhamento);
    if (AJUSTES.indexOf(e.ajuste) >= 0) partes.push('object-fit:' + e.ajuste);
    if (e.maiusculas) partes.push('text-transform:uppercase');

    var lb = numero(e.borda_largura, 0, 40);
    var cb = corValida(e.borda_cor);
    if (lb && cb) partes.push('border:' + lb + 'px solid ' + cb);

    var lc = numero(e.contorno_largura, 0, 12);
    var cc = corValida(e.contorno_cor);
    if (lc && cc) {
      partes.push('-webkit-text-stroke:' + lc + 'px ' + cc);
      partes.push('paint-order:stroke fill');
    }

    if (e.forma === 'elipse') partes.push('border-radius:50%');
    if (e.sombra) partes.push('box-shadow:0 2px 10px rgba(0,0,0,.18)');

    return partes.join(';');
  }

  /* ── desenho ──────────────────────────────────────────────────────── */

  function escala() {
    var folha = palco.querySelector('.est-folha');
    if (!folha) return 1;
    var atual = parseFloat(palco.dataset.escala || '1');
    return atual || 1;
  }

  function ajustarEscala() {
    var folha = palco.querySelector('.est-folha');
    if (!folha) return;
    var disponivel = palco.parentElement.clientWidth - 48;
    var fator = Math.min(1, disponivel / estado.largura);
    palco.dataset.escala = String(fator);
    folha.style.transform = 'scale(' + fator + ')';
    // A folha escalada continua ocupando o tamanho original no fluxo; sem
    // ajustar a altura do palco sobraria um vão enorme embaixo.
    palco.style.height = (estado.altura * fator) + 'px';
    palco.style.width = (estado.largura * fator) + 'px';
  }

  function desenharElemento(el) {
    var caixa = document.createElement('div');
    caixa.className = 'est-el est-el-' + el.tipo.toLowerCase();
    caixa.dataset.el = el.id;
    caixa.dataset.tipo = el.tipo;
    if (el.travado) caixa.dataset.travado = '1';
    caixa.style.left = el.x + 'px';
    caixa.style.top = el.y + 'px';
    caixa.style.width = el.largura + 'px';
    caixa.style.height = el.altura + 'px';
    caixa.style.zIndex = el.z;
    if (el.rotacao) caixa.style.transform = 'rotate(' + el.rotacao + 'deg)';

    var dentro;
    if (el.tipo === 'TEXTO') {
      dentro = document.createElement('div');
      dentro.className = 'est-texto';
      dentro.textContent = el.texto || '';
    } else if (el.tipo === 'IMAGEM') {
      dentro = document.createElement('img');
      dentro.className = 'est-img';
      dentro.src = (estado.assets[el.imagem] || {}).url || '';
      dentro.alt = (estado.assets[el.imagem] || {}).nome || '';
    } else {
      dentro = document.createElement('div');
      dentro.className = 'est-forma';
    }
    dentro.setAttribute('style', cssDeEstilo(el.estilo));
    caixa.appendChild(dentro);
    return caixa;
  }

  function desenharPagina() {
    var pagina = paginaPorId(paginaAtual);
    if (!pagina) return;

    palco.innerHTML = '';
    var folha = document.createElement('div');
    folha.className = 'est-folha';
    folha.dataset.pagina = pagina.id;
    folha.style.width = estado.largura + 'px';
    folha.style.height = estado.altura + 'px';
    folha.style.background = corValida(pagina.cor_de_fundo) || '#ffffff';

    pagina.elementos
      .slice()
      .sort(function (a, b) { return a.z - b.z; })
      .forEach(function (el) { folha.appendChild(desenharElemento(el)); });

    palco.appendChild(folha);
    ajustarEscala();
    if (selecionado) marcarSelecionado(selecionado);
    atualizarPainel();
    atualizarMiniaturas();
  }

  function marcarSelecionado(id) {
    palco.querySelectorAll('.est-el.is-sel').forEach(function (n) {
      n.classList.remove('is-sel');
      var alcas = n.querySelector('.est-alcas');
      if (alcas) alcas.remove();
    });
    var caixa = palco.querySelector('[data-el="' + id + '"]');
    if (!caixa) { selecionado = null; return; }
    caixa.classList.add('is-sel');

    if (caixa.dataset.travado === '1') return;

    var alcas = document.createElement('div');
    alcas.className = 'est-alcas';
    ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'].forEach(function (pos) {
      var alca = document.createElement('span');
      alca.className = 'est-alca est-alca-' + pos;
      alca.dataset.alca = pos;
      alcas.appendChild(alca);
    });
    var girar = document.createElement('span');
    girar.className = 'est-girar';
    girar.dataset.girar = '1';
    girar.title = 'Girar';
    alcas.appendChild(girar);
    caixa.appendChild(alcas);
  }

  function selecionar(id) {
    selecionado = id === null ? null : String(id);
    marcarSelecionado(selecionado);
    atualizarPainel();
  }

  /* ── miniaturas das páginas ───────────────────────────────────────── */

  function atualizarMiniaturas() {
    var lista = raiz.querySelector('[data-miniaturas]');
    if (!lista) return;
    lista.querySelectorAll('[data-ir-pagina]').forEach(function (botao) {
      var ativo = String(botao.dataset.irPagina) === String(paginaAtual);
      botao.classList.toggle('is-ativa', ativo);
    });
  }

  /* ── painel de propriedades ───────────────────────────────────────── */

  function atualizarPainel() {
    if (!painel) return;
    var pagina = paginaPorId(paginaAtual);
    var el = (selecionado && pagina) ? elementoPorId(pagina, selecionado) : null;

    painel.querySelectorAll('[data-quando]').forEach(function (bloco) {
      var quando = bloco.dataset.quando;
      var mostrar = (quando === 'nada' && !el)
        || (quando === 'algo' && !!el)
        || (el && quando === el.tipo.toLowerCase());
      bloco.hidden = !mostrar;
    });

    if (!el) return;

    painel.querySelectorAll('[data-prop]').forEach(function (campo) {
      var chave = campo.dataset.prop;
      var valor;
      if (chave === 'x' || chave === 'y' || chave === 'largura'
          || chave === 'altura' || chave === 'rotacao' || chave === 'z') {
        valor = el[chave];
      } else if (chave === 'texto') {
        valor = el.texto || '';
      } else if (chave === 'travado') {
        campo.checked = !!el.travado;
        return;
      } else {
        valor = (el.estilo || {})[chave];
      }
      if (campo.type === 'checkbox') {
        campo.checked = !!valor;
      } else {
        campo.value = valor === undefined || valor === null ? '' : valor;
      }
    });
  }

  function aplicarNoDom(el) {
    var caixa = palco.querySelector('[data-el="' + el.id + '"]');
    if (!caixa) return;
    caixa.style.left = el.x + 'px';
    caixa.style.top = el.y + 'px';
    caixa.style.width = el.largura + 'px';
    caixa.style.height = el.altura + 'px';
    caixa.style.zIndex = el.z;
    caixa.style.transform = el.rotacao ? 'rotate(' + el.rotacao + 'deg)' : '';
    if (el.travado) { caixa.dataset.travado = '1'; } else { delete caixa.dataset.travado; }

    var dentro = caixa.querySelector('.est-texto, .est-img, .est-forma');
    if (dentro) {
      dentro.setAttribute('style', cssDeEstilo(el.estilo));
      if (el.tipo === 'TEXTO') dentro.textContent = el.texto || '';
      if (el.tipo === 'IMAGEM') {
        var asset = estado.assets[el.imagem] || {};
        dentro.src = asset.url || '';
      }
    }
  }

  /* ── arrastar, redimensionar, girar ───────────────────────────────── */

  var gesto = null;

  palco.addEventListener('pointerdown', function (evento) {
    var alca = evento.target.closest('[data-alca]');
    var girar = evento.target.closest('[data-girar]');
    var caixa = evento.target.closest('.est-el');

    if (!caixa) { selecionar(null); return; }
    var pagina = paginaPorId(paginaAtual);
    var el = elementoPorId(pagina, caixa.dataset.el);
    if (!el) return;

    if (String(caixa.dataset.el) !== String(selecionado)) selecionar(caixa.dataset.el);
    if (el.travado) return;

    var fator = escala();
    gesto = {
      tipo: girar ? 'girar' : (alca ? 'redimensionar' : 'mover'),
      alca: alca ? alca.dataset.alca : null,
      el: el,
      x0: evento.clientX,
      y0: evento.clientY,
      ex: el.x, ey: el.y, el0: el.largura, ea0: el.altura, er0: el.rotacao,
      fator: fator
    };
    palco.setPointerCapture(evento.pointerId);
    evento.preventDefault();
  });

  palco.addEventListener('pointermove', function (evento) {
    if (!gesto) return;
    // Divide pela escala: o mouse anda na tela, o elemento mora na folha.
    var dx = (evento.clientX - gesto.x0) / gesto.fator;
    var dy = (evento.clientY - gesto.y0) / gesto.fator;
    var el = gesto.el;

    if (gesto.tipo === 'mover') {
      if (evento.shiftKey) {
        // Shift tranca o eixo de maior movimento: é como se alinha uma coluna
        // de fotos sem ficar caçando pixel.
        if (Math.abs(dx) > Math.abs(dy)) { dy = 0; } else { dx = 0; }
      }
      el.x = preso(gesto.ex + dx, -LIMITE, LIMITE);
      el.y = preso(gesto.ey + dy, -LIMITE, LIMITE);
    } else if (gesto.tipo === 'redimensionar') {
      var a = gesto.alca;
      var nx = gesto.ex, ny = gesto.ey, nl = gesto.el0, na = gesto.ea0;
      if (a.indexOf('e') >= 0) nl = gesto.el0 + dx;
      if (a.indexOf('s') >= 0) na = gesto.ea0 + dy;
      if (a.indexOf('w') >= 0) { nl = gesto.el0 - dx; nx = gesto.ex + dx; }
      if (a.indexOf('n') >= 0) { na = gesto.ea0 - dy; ny = gesto.ey + dy; }
      // Mínimo de 8px: caixa de largura zero desaparece da tela e não há como
      // pegá-la de volta com o mouse.
      el.largura = preso(Math.max(8, nl), 8, LIMITE);
      el.altura = preso(Math.max(8, na), 8, LIMITE);
      el.x = preso(nx, -LIMITE, LIMITE);
      el.y = preso(ny, -LIMITE, LIMITE);
    } else {
      var passo = evento.shiftKey ? 15 : 1;
      var bruto = gesto.er0 + dx / 2;
      el.rotacao = preso(Math.round(bruto / passo) * passo, -180, 180);
    }

    aplicarNoDom(el);
    atualizarPainel();
    evento.preventDefault();
  });

  function terminarGesto() {
    if (!gesto) return;
    gesto = null;
    marcarSujo();
    marcarSelecionado(selecionado);
  }

  palco.addEventListener('pointerup', terminarGesto);
  palco.addEventListener('pointercancel', terminarGesto);

  /* ── edição de texto na própria folha ─────────────────────────────── */

  palco.addEventListener('dblclick', function (evento) {
    var caixa = evento.target.closest('.est-el');
    if (!caixa || caixa.dataset.tipo !== 'TEXTO' || caixa.dataset.travado === '1') return;
    var dentro = caixa.querySelector('.est-texto');
    if (!dentro) return;

    // plaintext-only mantém o campo como TEXTO: colar do Word não traz HTML,
    // que é o que o modelo se recusa a guardar.
    dentro.setAttribute('contenteditable', 'plaintext-only');
    if (dentro.contentEditable !== 'plaintext-only') dentro.contentEditable = 'true';
    dentro.focus();

    function encerrar() {
      dentro.removeAttribute('contenteditable');
      var pagina = paginaPorId(paginaAtual);
      var el = elementoPorId(pagina, caixa.dataset.el);
      if (el) {
        // textContent, não innerHTML: o que sai daqui tem que ser texto puro
        // mesmo que o navegador tenha inserido <div> ao dar Enter.
        el.texto = dentro.textContent;
        marcarSujo();
        atualizarPainel();
      }
      dentro.removeEventListener('blur', encerrar);
    }
    dentro.addEventListener('blur', encerrar);
  });

  /* ── painel: mudanças ─────────────────────────────────────────────── */

  if (painel) {
    // 'input' E 'change': select nativo dispara os dois, mas o combo de busca
    // do projeto (pcf-combo.js) dispara SO 'change'. Se um dia ele passar a
    // envolver estes campos, ouvir apenas 'input' faria os controles de estilo
    // pararem de funcionar sem nenhum aviso.
    var aoMudar = function (evento) {
      var campo = evento.target.closest('[data-prop]');
      if (!campo || !selecionado) return;
      var pagina = paginaPorId(paginaAtual);
      var el = elementoPorId(pagina, selecionado);
      if (!el) return;

      var chave = campo.dataset.prop;
      var valor = campo.type === 'checkbox' ? campo.checked : campo.value;

      if (['x', 'y', 'largura', 'altura', 'rotacao', 'z'].indexOf(chave) >= 0) {
        var n = parseFloat(valor);
        if (isNaN(n)) return;
        el[chave] = chave === 'rotacao' ? preso(n, -180, 180)
          : (chave === 'z' ? preso(n, -999, 999) : preso(n, -LIMITE, LIMITE));
        if (chave === 'largura' || chave === 'altura') el[chave] = Math.max(8, el[chave]);
      } else if (chave === 'texto') {
        el.texto = String(valor);
      } else if (chave === 'travado') {
        el.travado = !!valor;
      } else {
        el.estilo = el.estilo || {};
        if (valor === '' || valor === false) { delete el.estilo[chave]; }
        else { el.estilo[chave] = valor; }
      }

      aplicarNoDom(el);
      marcarSujo();
      if (chave === 'travado') marcarSelecionado(selecionado);
    };
    painel.addEventListener('input', aoMudar);
    painel.addEventListener('change', aoMudar);

    painel.addEventListener('click', function (evento) {
      var acao = evento.target.closest('[data-acao]');
      if (!acao) return;
      var pagina = paginaPorId(paginaAtual);
      var el = selecionado ? elementoPorId(pagina, selecionado) : null;
      var nome = acao.dataset.acao;

      if (nome === 'apagar' && el) {
        pagina.elementos = pagina.elementos.filter(function (o) { return o !== el; });
        selecionado = null;
        desenharPagina();
        marcarSujo();
      } else if ((nome === 'frente' || nome === 'tras') && el) {
        var zs = pagina.elementos.map(function (o) { return o.z; });
        el.z = nome === 'frente' ? Math.max.apply(null, zs) + 1 : Math.min.apply(null, zs) - 1;
        aplicarNoDom(el);
        marcarSujo();
        atualizarPainel();
      } else if (nome === 'duplicar' && el) {
        var copia = JSON.parse(JSON.stringify(el));
        copia.id = proximoIdLocal--;
        copia.x += 16;
        copia.y += 16;
        pagina.elementos.push(copia);
        desenharPagina();
        selecionar(copia.id);
        marcarSujo();
      }
      evento.preventDefault();
    });
  }

  /* ── adicionar elemento ───────────────────────────────────────────── */

  function adicionar(dados) {
    var pagina = paginaPorId(paginaAtual);
    if (!pagina) return;
    var zs = pagina.elementos.map(function (o) { return o.z; });
    var novo = Object.assign({
      id: proximoIdLocal--,
      x: 80, y: 80, largura: 240, altura: 100, rotacao: 0,
      z: (zs.length ? Math.max.apply(null, zs) : 0) + 1,
      texto: '', imagem: null, estilo: {}, travado: false
    }, dados);
    pagina.elementos.push(novo);
    desenharPagina();
    selecionar(novo.id);
    marcarSujo();
  }

  raiz.addEventListener('click', function (evento) {
    var botao = evento.target.closest('[data-adicionar]');
    if (!botao) return;
    var tipo = botao.dataset.adicionar;
    if (tipo === 'texto') {
      adicionar({ tipo: 'TEXTO', texto: 'Escreva aqui',
                  estilo: { fonte: 'corpo', tamanho: 16, cor: '#2b2b2b' } });
    } else if (tipo === 'forma') {
      adicionar({ tipo: 'FORMA', altura: 160,
                  estilo: { forma: 'retangulo', fundo: '#fce3cd', raio: 16 } });
    } else if (tipo === 'imagem') {
      abrirSeletorDeImagem();
    }
    evento.preventDefault();
  });

  /* ── seletor de imagem ────────────────────────────────────────────── */

  var seletor = raiz.querySelector('[data-seletor-imagem]');

  function abrirSeletorDeImagem() {
    if (!seletor) return;
    seletor.hidden = false;
  }

  if (seletor) {
    seletor.addEventListener('click', function (evento) {
      if (evento.target.closest('[data-fechar]') || evento.target === seletor) {
        seletor.hidden = true;
        return;
      }
      var escolha = evento.target.closest('[data-asset]');
      if (!escolha) return;
      var id = escolha.dataset.asset;
      var asset = estado.assets[id];
      adicionar({
        tipo: 'IMAGEM', imagem: parseInt(id, 10),
        largura: 260, altura: 200,
        estilo: { ajuste: 'cover', raio: 12 }
      });
      if (asset) seletor.hidden = true;
    });

    var formulario = seletor.querySelector('[data-form-asset]');
    if (formulario) {
      formulario.addEventListener('submit', function (evento) {
        evento.preventDefault();
        var corpo = new FormData(formulario);
        fetch(formulario.action, {
          method: 'POST', body: corpo,
          headers: { 'X-CSRFToken': csrf() }
        }).then(function (r) { return r.json(); }).then(function (dados) {
          if (!dados.ok) {
            alert('Não deu para subir a imagem. Confira formato e tamanho.');
            return;
          }
          estado.assets[dados.asset.id] = dados.asset;
          var galeria = seletor.querySelector('[data-galeria]');
          if (galeria) {
            var item = document.createElement('button');
            item.type = 'button';
            item.className = 'est-asset';
            item.dataset.asset = dados.asset.id;
            item.innerHTML = '<img src="' + dados.asset.url + '" alt="">';
            item.appendChild(document.createTextNode(dados.asset.nome));
            galeria.insertBefore(item, galeria.firstChild);
          }
          formulario.reset();
        }).catch(function () {
          alert('Falha de rede ao subir a imagem.');
        });
      });
    }
  }

  /* ── trocar de página ─────────────────────────────────────────────── */

  raiz.addEventListener('click', function (evento) {
    var botao = evento.target.closest('[data-ir-pagina]');
    if (!botao) return;
    evento.preventDefault();
    var destino = botao.dataset.irPagina;
    if (String(destino) === String(paginaAtual)) return;

    // Trocar de página com alteração pendente perderia o trabalho em silêncio.
    var seguir = function () {
      paginaAtual = destino;
      selecionado = null;
      desenharPagina();
    };
    if (sujo) { salvar().then(seguir, seguir); } else { seguir(); }
  });

  /* ── salvar ───────────────────────────────────────────────────────── */

  function salvar() {
    var pagina = paginaPorId(paginaAtual);
    if (!pagina) return Promise.resolve();

    // A rota vem do template com pk 0 no lugar da página; troca-se o trecho
    // inteiro para não casar por acidente com outro '0' da URL.
    var rota = raiz.dataset.rotaSalvar.replace('/pagina/0/', '/pagina/' + pagina.id + '/');
    var carga = {
      cor_de_fundo: pagina.cor_de_fundo,
      elementos: pagina.elementos.map(function (el) {
        return {
          tipo: el.tipo, x: el.x, y: el.y,
          largura: el.largura, altura: el.altura,
          rotacao: el.rotacao, z: el.z,
          texto: el.texto || '', imagem: el.imagem,
          estilo: el.estilo || {}, travado: !!el.travado
        };
      })
    };

    if (avisoSalvar) avisoSalvar.textContent = 'Salvando…';
    return fetch(rota, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
      body: JSON.stringify(carga)
    }).then(function (r) { return r.json(); }).then(function (dados) {
      if (dados.ok) { marcarLimpo(dados.salvos); } else { throw new Error(dados.erro); }
    }).catch(function () {
      if (avisoSalvar) {
        avisoSalvar.textContent = 'Não salvou — tente de novo';
        avisoSalvar.dataset.estado = 'erro';
      }
    });
  }

  var botaoSalvar = raiz.querySelector('[data-salvar]');
  if (botaoSalvar) {
    botaoSalvar.addEventListener('click', function (evento) {
      evento.preventDefault();
      salvar();
    });
  }

  /* ── teclado ──────────────────────────────────────────────────────── */

  document.addEventListener('keydown', function (evento) {
    var editando = document.activeElement
      && (document.activeElement.isContentEditable
          || /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName));

    if ((evento.ctrlKey || evento.metaKey) && evento.key.toLowerCase() === 's') {
      evento.preventDefault();
      salvar();
      return;
    }
    if (editando) return;

    if (evento.key === 'Escape') { selecionar(null); return; }
    if (!selecionado) return;

    var pagina = paginaPorId(paginaAtual);
    var el = elementoPorId(pagina, selecionado);
    if (!el || el.travado) return;

    if (evento.key === 'Delete' || evento.key === 'Backspace') {
      pagina.elementos = pagina.elementos.filter(function (o) { return o !== el; });
      selecionado = null;
      desenharPagina();
      marcarSujo();
      evento.preventDefault();
      return;
    }

    var passo = evento.shiftKey ? 10 : 1;
    var movimentos = { ArrowLeft: [-passo, 0], ArrowRight: [passo, 0],
                       ArrowUp: [0, -passo], ArrowDown: [0, passo] };
    var mover = movimentos[evento.key];
    if (mover) {
      el.x = preso(el.x + mover[0], -LIMITE, LIMITE);
      el.y = preso(el.y + mover[1], -LIMITE, LIMITE);
      aplicarNoDom(el);
      atualizarPainel();
      marcarSujo();
      evento.preventDefault();
    }
  });

  window.addEventListener('beforeunload', function (evento) {
    if (!sujo) return;
    evento.preventDefault();
    evento.returnValue = '';
  });

  window.addEventListener('resize', ajustarEscala);

  // O aviso "o editor não carregou" nasce visível no HTML. Chegar aqui prova
  // que o JS subiu, então ele sai. Se este arquivo não for entregue, o aviso
  // fica na tela e explica o que fazer — em vez de palco vazio sem motivo.
  var alerta = raiz.querySelector('[data-editor-caiu]');
  if (alerta) alerta.hidden = true;

  desenharPagina();
  marcarLimpo();
})();
