/* O pcf-combo NAO pode entrar em laco ao ver a propria montagem.
 *
 * Em 09/2026 clicar em "Materiais" no semanario CONGELAVA a aba. O modal
 * insere um <select> com o catalogo inteiro do Supply; acima de LIMITE=8
 * opcoes o pcf-combo o transforma em campo de busca, movendo-o para dentro de
 * uma casca `.pcf-combo`. O MutationObserver dele observa o body inteiro,
 * entao ele via a PROPRIA montagem como conteudo novo e a desmontava achando
 * que era clone de linha (o `limparClones`, que existe para o "adicionar
 * linha" do Supply). Desmontava, remontava, desmontava...
 *
 * Callback de MutationObserver e microtask: o navegador so repinta quando a
 * fila seca. Ela nunca secava. O `hidden` do modal ja tinha sido removido, mas
 * o quadro com ele nunca chegava a tela.
 *
 * Nada disso aparece sem DOM: node --check passa, executar as funcoes passa, a
 * suite do Django passa. Com 8 itens ou menos tambem nao acontece — por isso
 * "funcionava" em desenvolvimento e travava em producao.
 *
 * Uso: node tests_js/pcf_combo_sem_laco.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { novoAmbiente, El } = require('./dom_minimo.js');

// PCF_COMBO_JS aponta para outra copia — serve para provar que este teste
// REPROVA a versao anterior ao conserto, em vez de so aprovar a atual.
const ARQUIVO = process.env.PCF_COMBO_JS
  || path.join(__dirname, '..', 'static', 'js', 'pcf-combo.js');
const LIMITE = 8;                       // tem de casar com o LIMITE do pcf-combo
const TAMANHOS = [1, LIMITE, LIMITE + 1, 40, 300];
const TETO_DE_VOLTAS = 500;

async function drenar(n){ for (let i = 0; i < n; i++) await Promise.resolve(); }

/* Devolve true se a fila de mutacoes SECOU (a aba repintaria). */
async function assenta(qtdOpcoes){
  const amb = novoAmbiente();
  new Function('document', 'window', 'MutationObserver', 'console',
    fs.readFileSync(ARQUIVO, 'utf8'))(amb.document, amb.window, amb.MutationObserver,
                                     { warn(){}, error(){}, log(){} });
  await drenar(20);

  const tbody = new El('tbody');
  amb.document.body.appendChild(tbody);
  await drenar(20);

  // Exatamente o que `abrirMateriais` faz: monta a linha e enche o select.
  const tr = new El('tr'), td = new El('td'), select = new El('select');
  select.classList.add('mat-item');
  for (let i = 0; i < qtdOpcoes; i++) {
    const o = new El('option');
    o.value = String(i); o.text = 'Item ' + i; o.textContent = o.text;
    select.appendChild(o); select.options.push(o);
  }
  select.selectedIndex = 0;
  td.appendChild(select); tr.appendChild(td);
  tbody.appendChild(tr);

  let anterior = -1, estavel = 0;
  for (let i = 0; i < TETO_DE_VOLTAS && estavel < 5 && !amb.estourou(); i++) {
    await Promise.resolve();
    if (amb.voltas() === anterior) estavel++;
    else { estavel = 0; anterior = amb.voltas(); }
  }
  return { assentou: estavel >= 5 && !amb.estourou(), voltas: amb.voltas() };
}

(async () => {
  let falhou = false;
  for (const n of TAMANHOS) {
    const r = await assenta(n);
    const marca = r.assentou ? 'ok  ' : 'FALHA';
    console.log(`${marca} ${String(n).padStart(4)} opcoes -> ${r.assentou
      ? `fila secou em ${r.voltas} voltas`
      : `fila NUNCA seca (${r.voltas} voltas) — a aba congela`}`);
    if (!r.assentou) falhou = true;
  }
  if (falhou) {
    console.log('\nO pcf-combo voltou a reagir a propria montagem.');
    console.log('Procure a marca de autoria `__pcfCasca` em static/js/pcf-combo.js.');
    process.exit(1);
  }
  console.log('\nTodos os tamanhos assentam.');
})().catch(e => { console.error('ESTOUROU:', e.message); process.exit(1); });
