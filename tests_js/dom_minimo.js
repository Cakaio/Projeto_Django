/* DOM minimo com MutationObserver DE VERDADE (callback em microtask).
   Existe porque o defeito que ele pega — laco infinito de observador — nao
   aparece em teste nenhum sem DOM: node --check passa, executar as funcoes
   passa, a suite do Django passa, e a aba do voluntario congela mesmo assim.
   So o que reage a mutacao do DOM pega isso. */
'use strict';

let observadores = [], agendado = false, voltas = 0, estourou = false;

/* Teto de seguranca. Um laco de observador e AUTO-ALIMENTADO: o callback
   enfileira a proxima volta, entao o `await` do teste NUNCA volta a rodar — no
   navegador e isso que congela a aba, e aqui derrubava o node por falta de
   memoria antes de dar tempo de relatar. O teto quebra o ciclo e deixa o teste
   dizer o que aconteceu. */
const TETO_DE_VOLTAS = 20;
/* Cada volta do laco monta uma casca inteira, e cada elemento novo gera outro
   registro: a fila cresce EXPONENCIALMENTE. Com teto alto o node morre por
   falta de memoria antes de conseguir relatar. Assentar leva 2 ou 3 voltas;
   20 separa com folga. */
const TETO_DE_REGISTROS = 2000;

class Lista {
  constructor(){ this._s = new Set(); }
  add(...c){ c.forEach(x => this._s.add(x)); }
  remove(...c){ c.forEach(x => this._s.delete(x)); }
  contains(c){ return this._s.has(c); }
  toggle(c, f){ f ? this.add(c) : this.remove(c); }
  get value(){ return [...this._s].join(' '); }
}

class El {
  constructor(tag){
    this.tagName = (tag || 'div').toUpperCase();
    this.childNodes = []; this.parentNode = null; this.nodeType = 1;
    this.attrs = {}; this.classList = new Lista();
    this.style = {}; this.textContent = ''; this.dataset = {}; this.options = [];
  }
  get className(){ return this.classList.value; }
  set className(v){ this.classList._s = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get children(){ return this.childNodes.filter(n => n.nodeType === 1); }
  set innerHTML(_v){ this.childNodes = []; }
  get innerHTML(){ return ''; }
  setAttribute(n, v){ this.attrs[n] = String(v); }
  getAttribute(n){ return n in this.attrs ? this.attrs[n] : null; }
  hasAttribute(n){ return n in this.attrs; }
  removeAttribute(n){ delete this.attrs[n]; }
  addEventListener(){} removeEventListener(){}
  insertAdjacentHTML(){} focus(){} blur(){} scrollIntoView(){}
  getBoundingClientRect(){ return {left:0,top:0,right:0,bottom:0,width:0,height:0}; }
  _registrar(adicionados){
    for (const o of observadores)
      if (o.alvo && this._dentroDe(o.alvo)) o.fila.push({ addedNodes: adicionados });
    agendar();
  }
  _dentroDe(raiz){ let n = this; while (n) { if (n === raiz) return true; n = n.parentNode; } return false; }
  appendChild(no){
    if (no.parentNode) no.parentNode._retirar(no);
    no.parentNode = this; this.childNodes.push(no);
    this._registrar([no]); return no;
  }
  insertBefore(no, ref){
    if (no.parentNode) no.parentNode._retirar(no);
    const i = ref ? this.childNodes.indexOf(ref) : this.childNodes.length;
    this.childNodes.splice(i < 0 ? this.childNodes.length : i, 0, no);
    no.parentNode = this; this._registrar([no]); return no;
  }
  _retirar(no){ const i = this.childNodes.indexOf(no); if (i >= 0) this.childNodes.splice(i, 1); no.parentNode = null; }
  remove(){ if (this.parentNode) this.parentNode._retirar(this); }
  closest(sel){ let n = this; while (n) { if (casa(n, sel)) return n; n = n.parentNode; } return null; }
  querySelectorAll(sel){
    const achados = [];
    (function anda(no){ for (const f of no.childNodes) { if (casa(f, sel)) achados.push(f); anda(f); } })(this);
    return achados;
  }
}

/* So o subconjunto de seletores que o pcf-combo usa. */
function casa(el, sel){
  if (el.nodeType !== 1) return false;
  let s = sel.trim(), negado = null;
  const m = s.match(/^(.*?):not\(\[([^\]]+)\]\)$/);
  if (m) { s = m[1]; negado = m[2]; }
  const attr = s.match(/\[([^\]=]+)\]$/);
  if (attr) { if (!el.hasAttribute(attr[1])) return false; s = s.slice(0, attr.index); }
  if (s.startsWith('.')) { if (!el.classList.contains(s.slice(1))) return false; s = ''; }
  if (s && el.tagName !== s.toUpperCase()) return false;
  if (negado && el.hasAttribute(negado)) return false;
  return true;
}

/* Como no navegador: o callback e microtask, e o navegador so repinta quando
   a fila SECA. E por isso que um laco aqui congela a aba em vez de so ficar
   lento. */
function agendar(){
  if (agendado) return;
  agendado = true;
  queueMicrotask(() => {
    agendado = false;
    const enfileirados = observadores.reduce((s, o) => s + o.fila.length, 0);
    if (++voltas > TETO_DE_VOLTAS || enfileirados > TETO_DE_REGISTROS) {
      estourou = true;
      observadores.forEach(o => { o.alvo = null; o.fila = []; });
      return;
    }
    for (const o of observadores) {
      const f = o.fila; o.fila = [];
      if (f.length) o.cb(f);
    }
  });
}

class MutationObserver {
  constructor(cb){ this.cb = cb; this.fila = []; this.alvo = null; observadores.push(this); }
  observe(alvo){ this.alvo = alvo; }
  disconnect(){ this.alvo = null; }
}

function novoAmbiente(){
  observadores = []; agendado = false; voltas = 0; estourou = false;
  const document = new El('html');
  document.body = new El('body');
  document.body.parentNode = document;
  document.childNodes.push(document.body);
  document.createElement = t => new El(t);
  document.readyState = 'complete';
  document.addEventListener = () => {};
  const window = { addEventListener(){}, console, MutationObserver };
  return { document, window, MutationObserver, El,
           voltas: () => voltas, estourou: () => estourou };
}

module.exports = { novoAmbiente, El };
