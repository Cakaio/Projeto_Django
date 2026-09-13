const {test} = require('node:test');
const assert = require('node:assert/strict');
const {cobertura, analisar} = require('../static/js/ajudas.js');

const base = () => ({
  hora_inicio: '06:00', hora_fim: '12:30', areas: [{valor: 'AZUL'}, {valor: 'VERDE'}, {valor: 'SUPPLY'}],
  voluntarios: [{id: 1, area: 'AZUL', nome: 'Caio', apto: true}, {id: 2, area: 'VERDE', nome: 'Bia', apto: true}],
  necessidades: [{key: 'n1', area: 'AZUL', hora_inicio: '09:00', hora_fim: '11:00', quantidade: 1},
    {key: 'n2', area: 'VERDE', hora_inicio: '09:00', hora_fim: '11:00', quantidade: 2}],
  ajudas: [{key: 'a1', voluntario: 1, area_destino: 'VERDE', hora_inicio: '09:00', hora_fim: '10:00'}],
});

test('saída parcial desconta da origem e retorno restaura contagem', () => {
  const s = base();
  const azul = cobertura(s.necessidades[0], s.voluntarios, s.ajudas);
  assert.deepEqual(azul.map(p => [p.hora_inicio, p.hora_fim, p.total]), [['09:00', '10:00', 0], ['10:00', '11:00', 1]]);
  assert.deepEqual(cobertura(s.necessidades[1], s.voluntarios, s.ajudas).map(p => p.total), [2, 1]);
});
test('ajudas contíguas permitidas e sobrepostas bloqueadas', () => {
  const s = base();
  s.ajudas.push({...s.ajudas[0], key: 'a2', hora_inicio: '10:00', hora_fim: '11:00'});
  assert.deepEqual(analisar(s), []);
  s.ajudas[1].hora_inicio = '09:59';
  assert(analisar(s).some(e => e.texto.includes('sobrepostos')));
});
test('próprios contam sem registros, inaptos não contam', () => {
  const s = base(); s.ajudas = [];
  assert.equal(cobertura(s.necessidades[0], s.voluntarios, s.ajudas)[0].total, 1);
  s.voluntarios[0].apto = false;
  assert.equal(cobertura(s.necessidades[0], s.voluntarios, s.ajudas)[0].total, 0);
});
test('própria área e pessoa ausente são conflitos', () => {
  const s = base(); s.ajudas[0].area_destino = 'AZUL'; s.voluntarios[0].apto = false;
  assert(analisar(s).some(e => e.texto.includes('própria área')));
  assert(analisar(s).some(e => e.texto.includes('presença confirmada')));
});
test('ajuda fora do dia ou da necessidade é recusada', () => {
  const s = base(); s.ajudas[0].hora_inicio = '05:30';
  assert(analisar(s).some(e => e.texto.includes('fora do período')));
  assert(analisar(s).some(e => e.texto.includes('caber em uma necessidade')));
});
test('remoção de necessidade destaca a ajuda órfã para correção', () => {
  const s = base(); s.necessidades = [s.necessidades[0]];
  assert(analisar(s).some(e => e.ajuda === 'a1'));
});
test('troca de pessoa mantendo quantidade preserva segmentos distintos', () => {
  const s = base(); s.voluntarios.push({id: 3, area: 'SUPPLY', nome: 'Dani', apto: true});
  s.ajudas.push({key: 'a2', voluntario: 3, area_destino: 'VERDE', hora_inicio: '10:00', hora_fim: '11:00'});
  const segmentos = cobertura(s.necessidades[1], s.voluntarios, s.ajudas);
  assert.equal(segmentos.length, 2);
  assert.deepEqual(segmentos.map(p => p.extras), [[1], [3]]);
});
test('necessidades de mesma área contíguas permitidas, sobrepostas recusadas', () => {
  const s = base(); s.necessidades.push({...s.necessidades[0], key: 'n3', hora_inicio: '11:00', hora_fim: '12:30'});
  assert.deepEqual(analisar(s), []);
  s.necessidades[2].hora_inicio = '10:30';
  assert(analisar(s).some(e => e.necessidade === 'n3'));
});
