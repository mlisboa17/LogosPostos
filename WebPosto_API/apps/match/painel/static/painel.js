// Logos Match: pequenos ajudantes de tela. Sem bibliotecas e sem chamadas externas.
(function () {
  // Botão "Mostrar" ao lado de cada campo de senha.
  document.querySelectorAll('input[type="password"]').forEach(function (campo) {
    var botao = document.createElement('button');
    botao.type = 'button';
    botao.className = 'secundario mostrar-senha';
    botao.textContent = 'Mostrar';
    botao.setAttribute('aria-label', 'Mostrar a senha');
    botao.addEventListener('click', function () {
      var visivel = campo.type === 'text';
      campo.type = visivel ? 'password' : 'text';
      botao.textContent = visivel ? 'Mostrar' : 'Ocultar';
      botao.setAttribute('aria-label', visivel ? 'Mostrar a senha' : 'Ocultar a senha');
    });
    campo.insertAdjacentElement('afterend', botao);
  });
  // Botão de envio mostra que está trabalhando e não aceita dois cliques.
  document.querySelectorAll('form').forEach(function (form) {
    form.addEventListener('submit', function () {
      var b = form.querySelector('button[type="submit"]');
      if (b && form.method.toLowerCase() === 'post') {
        setTimeout(function () { b.disabled = true; b.dataset.texto = b.textContent; b.textContent = 'Aguarde…'; }, 0);
      }
    });
  });
  // Notas: atualiza quantidade e total do que está marcado.
  var formNotas = document.getElementById('form-notas');
  if (formNotas) {
    var real = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
    var atualizar = function () {
      var marcadas = formNotas.querySelectorAll('input[name="ids"]:checked');
      var soma = 0;
      marcadas.forEach(function (c) { soma += parseFloat(c.dataset.valor || '0'); });
      var n = document.getElementById('selecionadas'), t = document.getElementById('total');
      if (n) { n.textContent = marcadas.length; }
      if (t) { t.textContent = real.format(soma); }
    };
    formNotas.addEventListener('change', atualizar);
  }
})();
