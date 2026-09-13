/* Quadro local: nenhuma movimentação faz uma requisição até salvar/publicar. */
(() => {
  'use strict';
  const sobrepoe = (a, b) => a.hora_inicio < b.hora_fim && a.hora_fim > b.hora_inicio;
  const horario = valor => typeof valor === 'string' && /^([01]\d|2[0-3]):[0-5]\d$/.test(valor);
  const contem = (n, a) => n.area === a.area_destino && n.hora_inicio <= a.hora_inicio && n.hora_fim >= a.hora_fim;

  function cobertura(n, voluntarios, ajudas) {
    if (!horario(n.hora_inicio) || !horario(n.hora_fim) || n.hora_inicio >= n.hora_fim) return [];
    const relevantes = ajudas.filter(a => horario(a.hora_inicio) && horario(a.hora_fim) && sobrepoe(n, a));
    const limites = [...new Set([n.hora_inicio, n.hora_fim, ...relevantes.flatMap(a => [
      a.hora_inicio < n.hora_inicio ? n.hora_inicio : a.hora_inicio,
      a.hora_fim > n.hora_fim ? n.hora_fim : a.hora_fim,
    ])])].sort();
    const segmentos = [];
    limites.slice(0, -1).forEach((inicio, i) => {
      const periodo = {hora_inicio: inicio, hora_fim: limites[i + 1]};
      const destinos = new Map(relevantes.filter(a => sobrepoe(periodo, a)).map(a => [a.voluntario, a.area_destino]));
      const proprios = [], extras = [];
      voluntarios.filter(v => v.apto).forEach(v => {
        if ((destinos.get(v.id) || v.area) === n.area) (v.area === n.area ? proprios : extras).push(v.id);
      });
      const anterior = segmentos[segmentos.length - 1];
      if (anterior && JSON.stringify([anterior.proprios, anterior.extras]) === JSON.stringify([proprios, extras])) {
        anterior.hora_fim = periodo.hora_fim;
      } else segmentos.push({...periodo, proprios, extras, total: proprios.length + extras.length});
    });
    return segmentos;
  }

  function analisar(quadro) {
    const erros = [];
    const areas = new Set(quadro.areas.map(a => a.valor));
    const pessoas = new Map(quadro.voluntarios.map(v => [v.id, v]));
    const periodoValido = item => horario(item.hora_inicio) && horario(item.hora_fim) && item.hora_inicio < item.hora_fim;
    if (!periodoValido(quadro)) erros.push({texto: 'Confira o início e o término do sábado.'});
    const checarPeriodo = (item, contexto) => {
      if (!periodoValido(item)) erros.push({...contexto, texto: `${contexto.nome}: o término deve ser posterior ao início.`});
      else if (item.hora_inicio < quadro.hora_inicio || item.hora_fim > quadro.hora_fim) {
        erros.push({...contexto, texto: `${contexto.nome}: horário fora do período do sábado.`});
      }
    };
    quadro.necessidades.forEach((n, i) => {
      const nome = quadro.areas.find(a => a.valor === n.area)?.nome || 'Necessidade';
      const contexto = {necessidade: n.key, nome};
      checarPeriodo(n, contexto);
      if (!areas.has(n.area) || !Number.isInteger(n.quantidade) || n.quantidade < 0 || n.quantidade > 100000) {
        erros.push({...contexto, texto: `${nome}: confira a área e a quantidade necessária.`});
      }
      if (quadro.necessidades.slice(0, i).some(o => o.area === n.area && sobrepoe(o, n))) {
        erros.push({...contexto, texto: `${nome}: necessidades com horários sobrepostos.`});
      }
    });
    quadro.ajudas.forEach((a, i) => {
      const v = pessoas.get(a.voluntario);
      const nome = v?.nome || 'Voluntário inexistente';
      const contexto = {ajuda: a.key, nome};
      checarPeriodo(a, contexto);
      if (!v?.apto) erros.push({...contexto, texto: `${nome}: precisa estar ativo e ter presença confirmada.`});
      if (v?.area === a.area_destino) erros.push({...contexto, texto: `${nome}: permanecer na própria área não gera ajuda.`});
      if (!areas.has(a.area_destino) || !quadro.necessidades.some(n => contem(n, a))) {
        erros.push({...contexto, texto: `${nome}: a ajuda deve caber em uma necessidade da área destino.`});
      }
      if (quadro.ajudas.slice(0, i).some(o => o.voluntario === a.voluntario && sobrepoe(o, a))) {
        erros.push({...contexto, texto: `${nome}: há ajudas com horários sobrepostos.`});
      }
    });
    return erros;
  }

  // As mesmas funções executadas no navegador são verificáveis sem DOM.
  if (typeof module !== 'undefined' && module.exports) module.exports = {cobertura, analisar, sobrepoe};
  if (typeof document === 'undefined') return;
  const root = document.getElementById('aj-quadro');
  if (!root) return;
  const $ = id => document.getElementById(id);
  function el(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([key, value]) => {
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = value;
      else if (value !== false && value != null) node.setAttribute(key, value === true ? '' : String(value));
    });
    children.forEach(child => node.append(child));
    return node;
  }
  const btn = (text, action, attrs = {}) => el('button', {type: 'button', class: 'aj-mini-btn', text, 'data-action': action, ...attrs});
  const cores = {VIOLETA: '#9c6ba9', ANIL: '#5f69a4', AZUL: '#5194c3', VERDE: '#72a27b', AMARELO: '#d2b344', LARANJA: '#e3965b', VERMELHO: '#c67870', FAMILIA_FELIZ: '#a88569', RECREACAO: '#61a99e', SUPPLY: '#9d907a'};
  let state, sequence = 0, baseline, saving = false, ajudaEditada = null, necessidadeEditada = null;
  const novaKey = () => `local-${++sequence}`;
  const nomeArea = area => state.areas.find(a => a.valor === area)?.nome || area || 'Sem área';
  const pessoa = id => state.voluntarios.find(v => v.id === Number(id));
  const editavel = () => state.status !== 'PUBLICADA' && !saving;
  const faixa = n => `${n.hora_inicio}–${n.hora_fim}`;
  function payload() {
    return {revisao: state.revisao, hora_inicio: state.hora_inicio, hora_fim: state.hora_fim,
      necessidades: state.necessidades.map(({area, hora_inicio, hora_fim, quantidade}) => ({area, hora_inicio, hora_fim, quantidade})),
      ajudas: state.ajudas.map(({voluntario, area_destino, hora_inicio, hora_fim}) => ({voluntario, area_destino, hora_inicio, hora_fim})),
    };
  }
  const alterado = () => JSON.stringify(payload()) !== baseline;
  function carregar(quadro) {
    state = quadro;
    state.necessidades.forEach(n => { n.key = novaKey(); });
    state.ajudas.forEach(a => { a.key = novaKey(); });
    baseline = JSON.stringify(payload());
    render();
  }
  function feedback(texto, erro = false) {
    const box = $('aj-feedback');
    box.textContent = texto;
    box.classList.toggle('aj-alert-error', erro);
    box.hidden = false;
  }
  function opcoes(select, lista, selecionado = '') {
    select.replaceChildren(...lista.map(([valor, nome]) => el('option', {value: valor, text: nome})));
    if (lista.some(([valor]) => String(valor) === String(selecionado))) select.value = selecionado;
  }
  function estatistica(n) {
    const segmentos = cobertura(n, state.voluntarios, state.ajudas);
    const minimo = segmentos.length ? Math.min(...segmentos.map(s => s.total)) : 0;
    const maximo = segmentos.length ? Math.max(...segmentos.map(s => s.total)) : 0;
    return {segmentos, minimo, maximo, falta: minimo < n.quantidade,
      classe: minimo < n.quantidade ? 'aj-short' : maximo > n.quantidade ? 'aj-over' : 'aj-met'};
  }
  function renderArea(n, erros) {
    const st = estatistica(n);
    const temErro = erros.some(e => e.necessidade === n.key || (e.ajuda && state.ajudas.some(a => a.key === e.ajuda && a.area_destino === n.area)));
    const card = el('article', {class: `pcf-card aj-area ${temErro ? 'aj-has-error' : ''}`, 'data-necessidade': n.key});
    card.style.setProperty('--area-color', cores[n.area] || 'var(--brand)');
    card.append(el('header', {class: 'aj-section-head'}, [el('h2', {text: nomeArea(n.area)}), el('span', {class: 'aj-time', text: faixa(n)})]));
    const contador = el('div', {class: `aj-counter ${st.classe}`, text: st.minimo === st.maximo ? st.minimo : `${st.minimo}–${st.maximo}`});
    contador.append(el('small', {text: ` / ${n.quantidade}`}));
    card.append(el('div', {class: 'aj-counter-row'}, [contador, el('span', {class: 'aj-muted', text: 'pessoas'})]));
    const barra = el('span');
    barra.style.width = `${n.quantidade ? Math.min(100, st.minimo / n.quantidade * 100) : 100}%`;
    card.append(el('div', {class: `aj-meter ${st.classe}`, 'aria-hidden': 'true'}, [barra]));
    const situacao = st.falta ? `Faltam até ${n.quantidade - st.minimo} pessoas` : st.maximo > n.quantidade ? `Até ${st.maximo - n.quantidade} pessoas a mais` : 'Necessidade atendida';
    card.append(el('p', {class: `aj-count ${st.classe}`, text: situacao}));
    if (n.sugestao?.includes('vagas extras')) card.append(el('p', {class: 'aj-muted', text: `Sugestão: ${n.sugestao}.`}));
    if (st.segmentos.length > 1) {
      const detalhes = el('details', {class: 'aj-segments'}, [el('summary', {text: 'Equipe varia no período · ver horários'})]);
      st.segmentos.forEach(s => detalhes.append(el('div', {class: 'aj-segment'}, [el('span', {text: faixa(s)}), el('strong', {text: `${s.total} / ${n.quantidade}`})])));
      card.append(detalhes);
    }
    const proprios = state.voluntarios.filter(v => v.apto && v.area === n.area);
    const grupo = el('div', {class: 'aj-group'}, [el('div', {class: 'aj-group-head'}, [el('span', {class: 'aj-section-label', text: 'Equipe da área'})])]);
    const chips = el('div', {class: 'aj-chips'});
    proprios.forEach(v => {
      const saindo = state.ajudas.filter(a => a.voluntario === v.id && sobrepoe(n, a));
      const disponivel = st.segmentos.some(s => s.proprios.includes(v.id));
      chips.append(el('span', {class: `aj-chip ${saindo.length ? 'aj-chip-away' : ''}`,
        draggable: editavel() ? 'true' : 'false', 'data-voluntario': v.id,
        text: `${v.nome}${saindo.length ? (disponivel ? ' · parcial' : ' · em ajuda') : ''}`,
        title: saindo.length ? saindo.map(a => `${nomeArea(a.area_destino)} ${faixa(a)}`).join('; ') : 'Presente na própria área durante todo o período',
      }));
    });
    if (!proprios.length) chips.append(el('span', {class: 'aj-muted', text: 'Nenhuma presença confirmada nesta área.'}));
    grupo.append(chips);
    card.append(grupo);
    const extras = state.ajudas.filter(a => a.area_destino === n.area && sobrepoe(n, a));
    const grupoExtras = el('div', {class: 'aj-group'});
    if (extras.length) grupoExtras.append(el('div', {class: 'aj-group-head'}, [el('span', {class: 'aj-section-label', text: 'Ajudas externas'})]));
    extras.forEach(a => {
      const v = pessoa(a.voluntario);
      const row = el('div', {class: 'aj-extra', draggable: editavel() ? 'true' : 'false', 'data-voluntario': a.voluntario, 'data-ajuda': a.key}, [
        el('div', {class: 'aj-extra-text'}, [el('strong', {text: v?.nome || 'Voluntário inexistente'}), el('small', {text: `${nomeArea(v?.area)} · ${faixa(a)}`})]),
      ]);
      if (editavel()) row.append(btn('Editar', 'editar-ajuda', {'data-key': a.key}), btn('×', 'remover-ajuda', {'data-key': a.key, class: 'aj-mini-btn aj-remove', 'aria-label': `Remover ajuda de ${v?.nome || 'voluntário'}`}));
      grupoExtras.append(row);
    });
    if (!extras.length) grupoExtras.append(el('p', {class: 'aj-drop-hint', text: editavel() ? 'Solte uma pessoa aqui' : 'Sem ajudas externas'}));
    card.append(grupoExtras);
    if (editavel()) card.append(el('footer', {class: 'aj-area-footer'}, [btn('+ Alocar', 'alocar', {'data-key': n.key, class: 'pcf-btn pcf-btn-outline pcf-btn-sm'}), btn('Ajustar necessidade', 'editar-necessidade', {'data-key': n.key})]));
    return card;
  }
  function renderEquipe() {
    const filtro = $('aj-busca').value.toLocaleLowerCase('pt-BR').normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    const necessidade = state.necessidades.find(n => n.key === $('aj-destino-filtro').value);
    const visiveis = state.voluntarios.filter(v => {
      const texto = `${v.nome} ${nomeArea(v.area)}`.toLocaleLowerCase('pt-BR').normalize('NFD').replace(/[\u0300-\u036f]/g, '');
      if (!texto.includes(filtro)) return false;
      return !necessidade || (v.apto && v.area !== necessidade.area && !state.ajudas.some(a => a.voluntario === v.id && sobrepoe(necessidade, a)));
    });
    const cards = visiveis.map(v => {
      const card = el('article', {class: `aj-person ${v.apto ? '' : 'aj-person-inactive'}`, 'data-voluntario': v.id, draggable: editavel() && v.apto ? 'true' : 'false'});
      const iniciais = v.nome.split(/\s+/).slice(0, 2).map(n => n[0]).join('');
      card.append(el('div', {class: 'aj-person-head'}, [el('span', {class: 'aj-avatar', text: iniciais, 'aria-hidden': 'true'}),
        el('div', {class: 'aj-person-title'}, [el('strong', {text: v.nome}), el('span', {class: 'aj-person-meta', text: nomeArea(v.area)})]),
        el('span', {class: `aj-car ${v.vai_de_carro ? '' : 'aj-no-car'}`, text: v.vai_de_carro === true ? 'De carro' : v.vai_de_carro === false ? 'Sem carro' : 'Carro: não informou'}),
      ]));
      if (!v.apto) card.append(el('p', {class: 'aj-form-error', text: 'Presença não confirmada ou voluntário inativo. Revise as ajudas.'}));
      const alocacoes = state.ajudas.filter(a => a.voluntario === v.id);
      if (alocacoes.length) card.append(el('div', {class: 'aj-person-assignments'}, alocacoes.map(a => el('span', {class: 'aj-assignment-tag', text: `${nomeArea(a.area_destino)} ${faixa(a)}`}))));
      const ultima = v.historico[0];
      const hist = el('details', {class: 'aj-history'}, [el('summary', {
        text: ultima ? `Última: ${ultima.data.slice(0, 5)} · ${ultima.area}` : 'Últimas ajudas',
        title: 'Ver até cinco ajudas recentes e preferências da enquete',
      })]);
      if (v.historico.length) hist.append(el('ul', {}, v.historico.map(h => el('li', {text: `${h.data} — ${h.area} · ${h.horario}`}))));
      else hist.append(el('p', {text: 'Nenhuma ajuda anterior publicada.'}));
      if (v.preferencias.length) hist.append(el('p', {text: `Na enquete: ${v.preferencias.join(', ')}.`}));
      card.append(hist);
      if (editavel() && v.apto) card.append(btn('Alocar →', 'alocar-pessoa', {'data-voluntario': v.id}));
      return card;
    });
    $('aj-equipe').replaceChildren(...(cards.length ? cards : [el('p', {class: 'aj-empty', text: 'Nenhuma pessoa disponível para este filtro.'})]));
    $('aj-total-equipe').textContent = necessidade ? `${visiveis.length} livres` : state.voluntarios.filter(v => v.apto).length;
  }
  function render() {
    const readonly = !editavel();
    $('aj-status').textContent = state.status === 'PUBLICADA' ? 'Publicada' : 'Rascunho';
    $('aj-status').className = `pcf-badge outline ${state.status === 'PUBLICADA' ? 'ok' : 'brand'}`;
    ['aj-inicio', 'aj-fim'].forEach(id => { $(id).disabled = readonly; });
    $('aj-inicio').value = state.hora_inicio;
    $('aj-fim').value = state.hora_fim;
    ['aj-salvar', 'aj-publicar', 'aj-adicionar'].forEach(id => { $(id).hidden = readonly; });
    ['aj-reabrir', 'aj-ver-publicada'].forEach(id => { $(id).hidden = state.status !== 'PUBLICADA'; });
    $('aj-salvo').textContent = alterado() ? 'Alterações não salvas' : state.revisao ? 'Todas as alterações salvas' : 'Sugestões ainda não salvas';
    const erros = analisar(state);
    $('aj-conflitos').hidden = !erros.length;
    $('aj-conflitos').replaceChildren(el('strong', {text: 'Revise antes de salvar ou publicar:'}), el('ul', {}, erros.map(e => {
      const li = el('li', {text: e.texto});
      if (e.ajuda && editavel()) li.append(btn('Editar', 'editar-ajuda', {'data-key': e.ajuda}), btn('Remover', 'remover-ajuda', {'data-key': e.ajuda}));
      return li;
    })));
    const faltas = state.necessidades.filter(n => estatistica(n).falta).length;
    $('aj-resumo').replaceChildren(...[[state.voluntarios.filter(v => v.apto).length, 'presenças confirmadas'], [state.ajudas.length, 'ajudas alocadas'], [faltas, 'necessidades com falta']].map(([num, texto]) => el('span', {}, [el('strong', {text: num}), ` ${texto}`])));
    $('aj-areas').replaceChildren(...(state.necessidades.length ? state.necessidades.map(n => renderArea(n, erros)) : [el('div', {class: 'pcf-card aj-empty', text: 'Nenhuma necessidade configurada. Use “+ Necessidade” para adicionar uma área.'})]));
    const selected = $('aj-destino-filtro').value;
    opcoes($('aj-destino-filtro'), [['', 'Todos os horários'], ...state.necessidades.map(n => [n.key, `${nomeArea(n.area)} · ${faixa(n)}`])], selected);
    renderEquipe();
  }

  function abrirAjuda(necessidadeKey = '', voluntarioId = '', ajudaKey = null) {
    if (!editavel()) return;
    if (!state.necessidades.length) return feedback('Adicione uma necessidade antes de alocar pessoas.', true);
    ajudaEditada = ajudaKey;
    const ajuda = state.ajudas.find(a => a.key === ajudaKey);
    const necessidade = state.necessidades.find(n => n.key === necessidadeKey) || (ajuda && state.necessidades.find(n => contem(n, ajuda))) || state.necessidades[0];
    $('aj-ajuda-titulo').textContent = ajuda ? 'Editar ajuda' : 'Alocar ajuda';
    opcoes($('aj-pessoa'), [['', 'Selecione uma pessoa'], ...state.voluntarios.filter(v => v.apto || v.id === ajuda?.voluntario).map(v => [v.id, `${v.nome} · ${nomeArea(v.area)}${v.apto ? '' : ' (indisponível)'}`])], ajuda?.voluntario || voluntarioId);
    opcoes($('aj-necessidade'), state.necessidades.map(n => [n.key, `${nomeArea(n.area)} · ${faixa(n)}`]), necessidade.key);
    $('aj-ajuda-inicio').value = ajuda?.hora_inicio || necessidade.hora_inicio;
    $('aj-ajuda-fim').value = ajuda?.hora_fim || necessidade.hora_fim;
    $('aj-ajuda-erro').textContent = '';
    $('aj-dialog-ajuda').showModal();
  }
  function confirmarAjuda(voluntarioId, necessidade, inicio, fim, key = null) {
    const ajuda = {key: key || novaKey(), voluntario: Number(voluntarioId), area_destino: necessidade.area, hora_inicio: inicio, hora_fim: fim};
    const outras = state.ajudas.filter(a => a.key !== key);
    const erros = analisar({...state, ajudas: [...outras, ajuda]}).filter(e => e.ajuda === ajuda.key);
    if (erros.length) return erros.map(e => e.texto).join(' ');
    state.ajudas = [...outras, ajuda];
    render();
    return '';
  }
  function abrirNecessidade(key = null) {
    if (!editavel()) return;
    necessidadeEditada = key;
    const n = state.necessidades.find(item => item.key === key);
    $('aj-necessidade-titulo').textContent = n ? 'Ajustar necessidade' : 'Nova necessidade';
    opcoes($('aj-n-area'), state.areas.map(a => [a.valor, a.nome]), n?.area || state.areas[0].valor);
    $('aj-n-inicio').value = n?.hora_inicio || (state.hora_inicio > '09:00' ? state.hora_inicio : '09:00');
    $('aj-n-fim').value = n?.hora_fim || (state.hora_fim < '11:00' ? state.hora_fim : '11:00');
    $('aj-n-quantidade').value = n?.quantidade ?? 1;
    $('aj-necessidade-erro').textContent = '';
    const antigoRemover = $('aj-remover-necessidade');
    if (antigoRemover) antigoRemover.remove();
    if (n) $('aj-form-necessidade').append(btn('Remover necessidade', 'remover-necessidade', {id: 'aj-remover-necessidade', class: 'aj-mini-btn aj-remove', 'data-key': key}));
    $('aj-dialog-necessidade').showModal();
  }

  async function persistir(acao) {
    if (saving) return;
    if (acao !== 'reabrir' && analisar(state).length) {
      feedback('Corrija os conflitos destacados antes de continuar.', true);
      $('aj-conflitos').scrollIntoView({block: 'center'});
      return;
    }
    saving = true;
    $('aj-controles').disabled = true;
    $('aj-salvo').textContent = 'Salvando…';
    try {
      const resposta = await fetch(root.dataset[acao], {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': root.querySelector('[name=csrfmiddlewaretoken]').value},
        body: JSON.stringify(payload()),
      });
      const json = await resposta.json().catch(() => null);
      if (!resposta.ok || !json?.quadro) throw new Error(json?.erros?.join(' ') || 'Não foi possível salvar. Confira sua conexão e sessão e tente novamente.');
      saving = false;
      carregar(json.quadro);
      feedback(acao === 'publicar' ? 'Escala publicada. Os voluntários já podem consultar suas ajudas.' : acao === 'reabrir' ? 'Escala reaberta como rascunho. Publique novamente ao terminar.' : 'Rascunho salvo. As ajudas serão exibidas aos voluntários após a publicação.');
    } catch (erro) {
      feedback(erro.message, true);
    } finally {
      saving = false;
      $('aj-controles').disabled = false;
      render();
    }
  }

  root.addEventListener('click', event => {
    const fechar = event.target.closest('[data-fechar]');
    if (fechar) return fechar.closest('dialog').close();
    const action = event.target.closest('[data-action]');
    if (!action || !editavel()) return;
    const key = action.dataset.key;
    switch (action.dataset.action) {
      case 'alocar': abrirAjuda(key); break;
      case 'alocar-pessoa': abrirAjuda($('aj-destino-filtro').value, action.dataset.voluntario); break;
      case 'editar-ajuda': abrirAjuda('', '', key); break;
      case 'remover-ajuda': state.ajudas = state.ajudas.filter(a => a.key !== key); render(); break;
      case 'editar-necessidade': abrirNecessidade(key); break;
      case 'remover-necessidade': {
        const n = state.necessidades.find(item => item.key === key);
        const alocadas = state.ajudas.filter(a => contem(n, a));
        if (!window.confirm(`Remover a necessidade de ${nomeArea(n.area)}${alocadas.length ? ` e suas ${alocadas.length} ajudas` : ''}? A alteração será salva quando você salvar o rascunho.`)) return;
        state.necessidades = state.necessidades.filter(item => item.key !== key);
        state.ajudas = state.ajudas.filter(a => !alocadas.includes(a));
        $('aj-dialog-necessidade').close();
        render();
        break;
      }
    }
  });
  $('aj-form-ajuda').addEventListener('submit', event => {
    event.preventDefault();
    const n = state.necessidades.find(item => item.key === $('aj-necessidade').value);
    if (!n || !editavel()) return;
    const erro = confirmarAjuda($('aj-pessoa').value, n, $('aj-ajuda-inicio').value, $('aj-ajuda-fim').value, ajudaEditada);
    $('aj-ajuda-erro').textContent = erro;
    if (!erro) $('aj-dialog-ajuda').close();
  });
  $('aj-necessidade').addEventListener('change', () => {
    const n = state.necessidades.find(item => item.key === $('aj-necessidade').value);
    if (n) { $('aj-ajuda-inicio').value = n.hora_inicio; $('aj-ajuda-fim').value = n.hora_fim; }
  });
  $('aj-form-necessidade').addEventListener('submit', event => {
    event.preventDefault();
    if (!editavel()) return;
    const n = {key: necessidadeEditada || novaKey(), area: $('aj-n-area').value, hora_inicio: $('aj-n-inicio').value, hora_fim: $('aj-n-fim').value, quantidade: Number($('aj-n-quantidade').value)};
    const necessidades = [...state.necessidades.filter(item => item.key !== necessidadeEditada), n].sort((a, b) => a.hora_inicio.localeCompare(b.hora_inicio) || nomeArea(a.area).localeCompare(nomeArea(b.area)));
    const erros = analisar({...state, necessidades}).filter(e => e.necessidade === n.key);
    $('aj-necessidade-erro').textContent = erros.map(e => e.texto).join(' ');
    if (erros.length) return;
    state.necessidades = necessidades;
    $('aj-dialog-necessidade').close();
    render();
  });
  root.addEventListener('dragstart', event => {
    const card = event.target.closest('[draggable="true"][data-voluntario]');
    if (!card || !editavel()) return;
    event.dataTransfer.setData('application/x-pcf-ajuda', JSON.stringify({voluntario: Number(card.dataset.voluntario), ajuda: card.dataset.ajuda || null}));
    event.dataTransfer.effectAllowed = 'copyMove';
  });
  root.addEventListener('dragover', event => {
    const card = event.target.closest('[data-necessidade]');
    if (card && editavel() && Array.from(event.dataTransfer.types).includes('application/x-pcf-ajuda')) {
      event.preventDefault(); card.classList.add('aj-drag-over');
    }
  });
  root.addEventListener('dragleave', event => {
    const card = event.target.closest('[data-necessidade]');
    if (card && !card.contains(event.relatedTarget)) card.classList.remove('aj-drag-over');
  });
  root.addEventListener('dragend', () => root.querySelectorAll('.aj-drag-over').forEach(n => n.classList.remove('aj-drag-over')));
  root.addEventListener('drop', event => {
    const card = event.target.closest('[data-necessidade]');
    if (!card || !editavel()) return;
    event.preventDefault(); card.classList.remove('aj-drag-over');
    let dados;
    try { dados = JSON.parse(event.dataTransfer.getData('application/x-pcf-ajuda')); } catch (_) { return; }
    const n = state.necessidades.find(item => item.key === card.dataset.necessidade);
    if (!n || !pessoa(dados.voluntario)) return;
    const erro = confirmarAjuda(dados.voluntario, n, n.hora_inicio, n.hora_fim, dados.ajuda);
    if (erro) {
      abrirAjuda(n.key, dados.voluntario, dados.ajuda);
      $('aj-ajuda-erro').textContent = `${erro} Ajuste o período para alocar.`;
    }
  });
  ['aj-inicio', 'aj-fim'].forEach(id => $(id).addEventListener('change', () => {
    if (!editavel()) return;
    state[id === 'aj-inicio' ? 'hora_inicio' : 'hora_fim'] = $(id).value;
    render();
  }));
  $('aj-busca').addEventListener('input', renderEquipe);
  $('aj-destino-filtro').addEventListener('change', renderEquipe);
  $('aj-adicionar').addEventListener('click', () => abrirNecessidade());
  $('aj-salvar').addEventListener('click', () => persistir('salvar'));
  $('aj-publicar').addEventListener('click', () => {
    if (analisar(state).length) return feedback('Corrija os conflitos destacados antes de publicar.', true);
    const faltas = state.necessidades.filter(n => estatistica(n).falta).length;
    $('aj-revisao-publicacao').textContent = `${state.ajudas.length} ajudas em ${state.necessidades.length} necessidades. ${faltas ? `${faltas} necessidades ainda têm falta de pessoas em algum horário. Você pode publicar e reorganizar depois.` : 'Todas as necessidades estão atendidas.'}`;
    $('aj-dialog-publicar').showModal();
  });
  $('aj-reabrir').addEventListener('click', () => $('aj-dialog-reabrir').showModal());
  $('aj-confirmar-publicacao').addEventListener('click', () => { $('aj-dialog-publicar').close(); persistir('publicar'); });
  $('aj-confirmar-reabertura').addEventListener('click', () => { $('aj-dialog-reabrir').close(); persistir('reabrir'); });
  window.addEventListener('beforeunload', event => { if (alterado() || saving) { event.preventDefault(); event.returnValue = ''; } });
  carregar(JSON.parse($('aj-dados').textContent));
})();
