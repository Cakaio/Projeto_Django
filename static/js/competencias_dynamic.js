document.addEventListener("DOMContentLoaded", function () {
  const salaSelect = document.getElementById("id_sala");
  if (!salaSelect) return;

  salaSelect.addEventListener("change", function () {
    const sala = this.value;
    const competenciaSelects = document.querySelectorAll('select[id$="competencia"]');
    const emptyOption = '<option value="">---</option>';

    if (!sala) {
      competenciaSelects.forEach(s => s.innerHTML = emptyOption);
      return;
    }

    fetch(`/semanario/ajax/get_competencias/?sala=${encodeURIComponent(sala)}`)
      .then(response => response.json())
      .then(data => {
        const competencias = data.competencias || [];
        competenciaSelects.forEach(s => {
          s.innerHTML = "";
          if (competencias.length > 0) {
            competencias.forEach(c => {
              const option = document.createElement("option");
              option.value = c;
              option.textContent = c;
              s.appendChild(option);
            });
          } else {
            s.innerHTML = '<option value="">Nenhuma competência disponível</option>';
          }
        });
      })
      .catch(err => {
        console.error("Erro ao buscar competências:", err);
      });
  });

  // Se já houver uma sala selecionada no carregamento da página, dispara o change para preencher as competências
  if (salaSelect.value) salaSelect.dispatchEvent(new Event('change'));
});
