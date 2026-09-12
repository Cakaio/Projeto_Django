/* Escolha de várias pessoas com busca.
 *
 * Substitui o <select multiple> nativo, que exige Ctrl+clique para marcar mais
 * de uma — impossível no celular, e o PCF é PWA. Aqui são caixas de seleção de
 * verdade: acessíveis por teclado e por toque, sem instrução nenhuma.
 *
 * A busca só esconde linhas; nunca desmarca. Filtrar não pode apagar escolha
 * que a pessoa já fez, senão procurar o segundo nome perderia o primeiro.
 */
(function () {
  'use strict';

  document.querySelectorAll('[data-escolha-pessoas]').forEach(function (caixa) {
    var busca = caixa.querySelector('[data-pessoas-busca]');
    var vazio = caixa.querySelector('[data-pessoas-vazio]');
    var contagem = caixa.querySelector('[data-pessoas-contagem]');
    var itens = Array.prototype.slice.call(caixa.querySelectorAll('li'));
    if (!itens.length) return;

    function normalizar(texto) {
      return (texto || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    }

    function marcados() {
      return caixa.querySelectorAll('input[type="checkbox"]:checked').length;
    }

    function atualizarContagem() {
      var total = marcados();
      if (!contagem) return;
      contagem.textContent = total
        ? total + (total === 1 ? ' pessoa escolhida' : ' pessoas escolhidas')
        : '';
      itens.forEach(function (item) {
        var campo = item.querySelector('input[type="checkbox"]');
        item.classList.toggle('esta-marcada', Boolean(campo && campo.checked));
      });
    }

    function filtrar() {
      var termo = normalizar(busca ? busca.value.trim() : '');
      var visiveis = 0;
      itens.forEach(function (item) {
        var campo = item.querySelector('input[type="checkbox"]');
        // Quem já está marcado nunca some da lista: sumir daria a impressão de
        // que a escolha foi perdida.
        var mostra = !termo
          || (campo && campo.checked)
          || normalizar(item.textContent).indexOf(termo) !== -1;
        item.hidden = !mostra;
        if (mostra) visiveis += 1;
      });
      if (vazio) vazio.hidden = visiveis > 0;
    }

    if (busca) {
      busca.addEventListener('input', filtrar);
      // Enter dentro da busca enviaria o formulário inteiro sem querer.
      busca.addEventListener('keydown', function (evento) {
        if (evento.key === 'Enter') evento.preventDefault();
      });
    }
    caixa.addEventListener('change', atualizarContagem);
    atualizarContagem();
  });
})();
