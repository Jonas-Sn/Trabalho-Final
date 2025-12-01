function validarCPF(cpf) {
  if (!cpf) return false;
  cpf = cpf.replace(/\D/g, '');
  if (cpf.length !== 11) return false;
  if (/^(\d)\1{10}$/.test(cpf)) return false;

  let soma = 0;
  for (let i = 0; i < 9; i++) {
    soma += parseInt(cpf.charAt(i), 10) * (10 - i);
  }
  let resto = soma % 11;
  let dig1 = (resto < 2) ? 0 : 11 - resto;
  if (dig1 !== parseInt(cpf.charAt(9), 10)) return false;

  soma = 0;
  for (let i = 0; i < 10; i++) {
    soma += parseInt(cpf.charAt(i), 10) * (11 - i);
  }
  resto = soma % 11;
  let dig2 = (resto < 2) ? 0 : 11 - resto;
  if (dig2 !== parseInt(cpf.charAt(10), 10)) return false;

  return true;
}

const input = document.getElementById('usuario');
let msg = document.querySelector('#cpf-msg');

if (!msg) {
  msg = document.createElement('span');
  msg.id = 'cpf-msg';
  msg.style.marginLeft = '10px';
  input.insertAdjacentElement('afterend', msg);
}

function validarEExibirMensagem() {
  const valor = input.value;
  if (valor.trim() === '') {
    msg.textContent = '';
    return;
  }
  if (validarCPF(valor)) {
    msg.style.color = 'green';
    msg.textContent = 'CPF válido';
  } else {
    msg.style.color = 'crimson';
    msg.textContent = 'CPF inválido';
  }
}

// Valida a cada alteração (digitação, colar, etc)
input.addEventListener('input', validarEExibirMensagem);

// Bloqueia digitação de letras
input.addEventListener('keypress', (e) => {
  const char = String.fromCharCode(e.which || e.keyCode);
  if (!/[0-9]/.test(char) && !e.ctrlKey && !e.metaKey && e.key !== 'Backspace') {
    e.preventDefault();
  }
});

// Também bloqueia colar texto que não seja números
input.addEventListener('paste', (e) => {
  const paste = (e.clipboardData || window.clipboardData).getData('text');
  if (!/^\d*$/.test(paste)) {
    e.preventDefault();
  }
});
