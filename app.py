from flask import Flask, render_template, request, redirect, url_for
import json, os

app = Flask(__name__)
app.secret_key = 'chave_super_secreta_123'

ARQUIVO = 'users.json'

# ---------- Funções de suporte ----------
def inicializar_usuarios_fixos():
    """Garante que existam contas padrão de admin e médico."""
    usuarios_fixos = [
        {"nome": "Admin", "CPF": "0001", "senha": "admin123", "tipo": "admin"},
        {"nome": "Dr. Carlos Silva", "CPF": "0002", "senha": "medico123", "tipo": "medico"}
    ]

    if not os.path.exists(ARQUIVO):
        with open(ARQUIVO, 'w') as f:
            json.dump(usuarios_fixos, f, indent=4, ensure_ascii=False)
        return

    with open(ARQUIVO, 'r') as f:
        try:
            usuarios = json.load(f)
        except json.JSONDecodeError:
            usuarios = []

    # Evita duplicar os usuários fixos
    cpfs_existentes = [u['CPF'] for u in usuarios]
    for u in usuarios_fixos:
        if u['CPF'] not in cpfs_existentes:
            usuarios.append(u)

    with open(ARQUIVO, 'w') as f:
        json.dump(usuarios, f, indent=4, ensure_ascii=False)


def carregar_usuarios():
    try:
        with open('users.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def salvar_usuarios(usuarios):
    with open('users.json', 'w', encoding='utf-8') as f:
        json.dump(usuarios, f, ensure_ascii=False, indent=2)

# Consultas

APPT_FILE = 'appointments.json'

def carregar_consultas():
    if os.path.exists('consultas.json'):
        with open('consultas.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def salvar_consultas(consultas):
    with open('consultas.json', 'w', encoding='utf-8') as f:
        json.dump(consultas, f, ensure_ascii=False, indent=4)

def gerar_id_consulta(consultas):
    if not consultas:
        return 1
    return max(c.get('id', 0) for c in consultas) + 1

# ---------- Rotas principais ----------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form['usuario']
        cpf = request.form['CPF']
        senha = request.form['senha']

        # 🔍 Validação simples de CPF
        cpf = cpf.strip().replace(".", "").replace("-", "")
        if not cpf.isdigit() or len(cpf) != 11:
            return render_template('cadastro.html', erro="CPF inválido! Deve conter 11 dígitos numéricos.")

        usuarios = carregar_usuarios()

        for u in usuarios:
            if u['CPF'] == cpf:
                return render_template('cadastro.html', erro="Esse CPF já está cadastrado!")

        usuarios.append({
            'nome': nome,
            'CPF': cpf,
            'senha': senha,
            'tipo': 'paciente'
        })

        with open(ARQUIVO, 'w') as f:
            json.dump(usuarios, f, indent=4, ensure_ascii=False)

        return redirect(url_for('index'))

    return render_template('cadastro.html')


@app.route('/login', methods=['POST'])
def login():
    from flask import session  # garante que session está importado
    cpf = request.form['cpf']
    senha = request.form['senha']

    cpf = cpf.strip().replace('.', '').replace('-', '')

    if not os.path.exists('users.json'):
        with open('users.json', 'w') as f:
            json.dump([], f)

    with open('users.json', 'r') as f:
        try:
            usuarios = json.load(f)
        except json.JSONDecodeError:
            usuarios = []

    for u in usuarios:
        cpf_salvo = u['CPF'].replace('.', '').replace('-', '')

        if cpf_salvo == cpf and u['senha'] == senha:
            tipo = u.get('tipo', 'paciente')
            session['cpf'] = u['CPF']
            session['tipo'] = tipo

            if tipo == 'admin':
                return redirect(url_for('dashboardadmin'))
            elif tipo == 'medico':
                return redirect(url_for('agendamedico'))
            else:
                return redirect(url_for('agendapaciente'))

    return render_template('index.html', erro="CPF ou senha incorretos!")


@app.route('/clientesadmin')
def clientesadmin():
    usuarios = carregar_usuarios()
    busca = request.args.get('busca', '').strip().lower()
    usuarios = [u for u in usuarios if u.get('tipo') in ['admin', 'paciente']]

    # Filtra os usuários
    if busca:
        usuarios = [u for u in usuarios if busca in u['nome'].lower() or busca in u['CPF']]

     # 🔹 Formata os CPFs antes de enviar pro template
    for u in usuarios:
        cpf = u.get('CPF', '')
        if len(cpf) == 11 and cpf.isdigit():
            u['CPF'] = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
        else:
            # Caso o CPF esteja com outro formato (como 0001 dos usuários fixos)
            u['CPF'] = cpf
        
        # Nome com inicial maiúscula (e resto minúsculo)
        nome = u.get('nome', '')
        u['nome'] = nome.title()

        # Tipo com primeira letra maiúscula (Admin, Medico, Paciente)
        tipo = u.get('tipo', '')
        u['tipo'] = tipo.title()

    return render_template('clientesadmin.html', usuarios=usuarios)

@app.route('/novo_cliente', methods=['POST'])
def novo_cliente():
    nome = request.form['nome']
    cpf = request.form['CPF'].strip().replace('.', '').replace('-', '')
    senha = request.form['senha']

    usuarios = carregar_usuarios()

    # Verifica se CPF já existe
    for u in usuarios:
        if u['CPF'] == cpf:
            flash('Este CPF já está cadastrado!', 'erro')
            return redirect(url_for('clientesadmin'))

    # Adiciona como paciente por padrão
    usuarios.append({
        'nome': nome,
        'CPF': cpf,
        'senha': senha,
        'tipo': 'paciente'
    })

    with open(ARQUIVO, 'w') as f:
        json.dump(usuarios, f, indent=4, ensure_ascii=False)

    return redirect(url_for('clientesadmin'))

from datetime import datetime

@app.route('/novo_medico', methods=['POST'])
def novo_medico():
    nome = request.form['nome']
    cpf = request.form['CPF'].strip().replace('.', '').replace('-', '')
    senha = request.form['senha']

    usuarios = carregar_usuarios()

    # Verifica se CPF já existe
    for u in usuarios:
        if u['CPF'] == cpf:
            flash('Este CPF já está cadastrado!', 'erro')
            return redirect(url_for('medicosadmin'))

    # Adiciona como paciente por padrão
    usuarios.append({
        'nome': nome,
        'CPF': cpf,
        'senha': senha,
        'tipo': 'medico'
    })

    with open(ARQUIVO, 'w') as f:
        json.dump(usuarios, f, indent=4, ensure_ascii=False)

    return redirect(url_for('medicosadmin'))

from datetime import datetime

@app.route('/remover_cliente', methods=['POST'])
def remover_cliente():
    cpf = (request.form.get('CPF') or '').replace('.', '').replace('-', '').strip()
    usuarios = carregar_usuarios()

    # Remove o cliente independentemente do formato (com/sem pontos)
    novos_usuarios = [
        u for u in usuarios
        if u.get('CPF', '').replace('.', '').replace('-', '').strip() != cpf
    ]

    if len(novos_usuarios) != len(usuarios):
        salvar_usuarios(novos_usuarios)
        flash('Cliente removido com sucesso!', 'ok')
    else:
        flash('Cliente não encontrado.', 'erro')

    return redirect(url_for('clientesadmin'))

@app.route('/remover_medico', methods=['POST'])
def remover_medico():
    cpf = (request.form.get('CPF') or '').replace('.', '').replace('-', '').strip()
    usuarios = carregar_usuarios()

    # Remove o cliente independentemente do formato (com/sem pontos)
    novos_usuarios = [
        u for u in usuarios
        if u.get('CPF', '').replace('.', '').replace('-', '').strip() != cpf
    ]

    if len(novos_usuarios) != len(usuarios):
        salvar_usuarios(novos_usuarios)
        flash('Médico removido com sucesso!', 'ok')
    else:
        flash('Médico não encontrado.', 'erro')

    return redirect(url_for('medicosadmin'))

@app.route('/salvar_edicao_cliente', methods=['POST'])
def salvar_edicao_cliente():
    cpf_original = (request.form.get('cpf_original') or '').replace('.', '').replace('-', '')
    nome = request.form.get('nome').strip().title()
    novo_cpf = ''.join(filter(str.isdigit, request.form.get('CPF') or ''))
    tipo = request.form.get('tipo').lower()

    usuarios = carregar_usuarios()
    alterou = False

    for u in usuarios:
        if u['CPF'].replace('.', '').replace('-', '') == cpf_original:
            u['nome'] = nome
            u['CPF'] = novo_cpf
            u['tipo'] = tipo
            alterou = True
            break

    if alterou:
        salvar_usuarios(usuarios)
        flash('Cliente atualizado com sucesso!', 'ok')
    else:
        flash('Cliente não encontrado.', 'erro')

    return redirect(url_for('clientesadmin'))

@app.route('/dashboardadmin')
def dashboardadmin():
    return render_template('dashboardadmin.html')

@app.route('/agendaadmin', methods=['GET', 'POST'])
def agendaadmin():
    # Garantir acesso de admin (opcional)
    # if session.get('tipo') != 'admin':
    #     return "Acesso negado", 403

    usuarios = carregar_usuarios()
    consultas = carregar_consultas()

    # Enriquecer consultas com nomes de pacientes e médicos
    mapa_nomes = {u['CPF']: u['nome'] for u in usuarios}
    for c in consultas:
        c['paciente_nome'] = mapa_nomes.get(c.get('paciente_cpf', ''), c.get('paciente_cpf', ''))
        c['medico_nome']   = mapa_nomes.get(c.get('medico_cpf', ''), c.get('medico_cpf', ''))

    # --- Criar nova consulta (POST do formulário do admin)
    if request.method == 'POST':
        paciente_cpf = (request.form.get('paciente_cpf') or '').replace('.', '').replace('-', '').strip()
        medico_cpf   = (request.form.get('medico_cpf') or '').replace('.', '').replace('-', '').strip()
        data         = request.form.get('data')   # YYYY-MM-DD
        hora         = request.form.get('hora')   # HH:MM
        tipo         = request.form.get('tipo') or 'Consulta'
        obs          = request.form.get('observacoes') or ''

        # Validações
        if not paciente_cpf or not medico_cpf or not data or not hora:
            flash('Preencha todos os campos obrigatórios.', 'erro')
            return redirect(url_for('agendaadmin'))

        # Verifica se o paciente e médico existem
        existe_paciente = any(u for u in usuarios if u['CPF'] == paciente_cpf and u.get('tipo', 'paciente') == 'paciente')
        existe_medico   = any(u for u in usuarios if u['CPF'] == medico_cpf and u.get('tipo') == 'medico')
        if not existe_paciente or not existe_medico:
            flash('CPF de paciente ou médico inválido.', 'erro')
            return redirect(url_for('agendaadmin'))

        # Verifica conflito de horário
        conflito = any(
            c for c in consultas
            if c['medico_cpf'] == medico_cpf and c['data'] == data and c['hora'] == hora and c['status'] != 'cancelada'
        )
        if conflito:
            flash('Já existe consulta para esse médico neste horário.', 'erro')
            return redirect(url_for('agendaadmin'))

        # Cria nova consulta
        nova = {
            "id": gerar_id_consulta(consultas),
            "paciente_cpf": paciente_cpf,
            "medico_cpf": medico_cpf,
            "data": data,
            "hora": hora,
            "tipo": tipo,
            "status": "agendada",
            "observacoes": obs
        }

        consultas.append(nova)
        salvar_consultas(consultas)
        flash('Consulta criada com sucesso!', 'ok')
        return redirect(url_for('agendaadmin'))

    # --- FILTROS (paciente, médico, status, data)
    busca_paciente = (request.args.get('busca_paciente') or '').strip().lower()
    busca_medico   = (request.args.get('busca_medico') or '').strip().lower()
    filtro_status  = (request.args.get('status') or '').strip().lower()
    filtro_data    = (request.args.get('data') or '').strip()

    lista = consultas

    # Filtro por paciente (nome ou CPF)
    if busca_paciente:
        lista = [
            c for c in lista
            if busca_paciente in c.get('paciente_nome', '').lower()
            or busca_paciente in c.get('paciente_cpf', '')
        ]

    # Filtro por médico (nome)
    if busca_medico:
        lista = [c for c in lista if busca_medico in c.get('medico_nome', '').lower()]

    # Filtro por status e data
    if filtro_status:
        lista = [c for c in lista if c.get('status', '').lower() == filtro_status]
    if filtro_data:
        lista = [c for c in lista if c.get('data', '') == filtro_data]

    # Ordenar por data/hora (seguro)
    try:
        lista.sort(key=lambda x: (x.get('data', ''), x.get('hora', '')))
    except Exception:
        pass

    # Lista de médicos (para autocomplete no HTML)
    medicos = [u for u in usuarios if u.get('tipo') == 'medico']

    return render_template('agendaadmin.html', consultas=lista, medicos=medicos, usuarios=usuarios)


@app.route('/aprovar_consulta', methods=['POST'])
def aprovar_consulta():
    consulta_id = (request.form.get('id') or '').strip()
    consultas = carregar_consultas()

    alterou = False
    for c in consultas:
        if str(c.get('id')) == str(consulta_id):
            c['status'] = 'agendada'
            alterou = True
            break

    if alterou:
        salvar_consultas(consultas)
        flash('Consulta aprovada com sucesso!', 'ok')
    else:
        flash('Consulta não encontrada.', 'erro')

    return redirect(url_for('agendaadmin'))


@app.route('/cancelar_consulta', methods=['POST'])
def cancelar_consulta():
    consulta_id = (request.form.get('id') or '').strip()
    consultas = carregar_consultas()  # sempre recarrega do arquivo

    alterou = False
    for c in consultas:
        # compara de forma robusta (string vs int)
        if str(c.get('id')) == str(consulta_id):
            c['status'] = 'cancelada'
            alterou = True
            break

    if alterou:
        salvar_consultas(consultas)   # SALVA no consultas.json
        flash('Consulta cancelada.', 'ok')
    else:
        flash('Consulta não encontrada.', 'erro')

    return redirect(url_for('agendaadmin'))


@app.route('/agendamedico')
def agendamedico():
    from flask import session
    usuarios = carregar_usuarios()
    consultas = carregar_consultas()

    # Tenta pegar o CPF da sessão, ou da querystring para testes
    medico_cpf = (session.get('cpf') or request.args.get('medico_cpf') or '').replace('.', '').replace('-', '').strip()

    if not medico_cpf:
        return "Informe medico_cpf na querystring (ex.: ?medico_cpf=0002)", 400

    medico = next((u for u in usuarios if u['CPF'] == medico_cpf and u.get('tipo') == 'medico'), None)
    if not medico:
        return "Médico não encontrado ou não autorizado.", 403

    # Filtra apenas as consultas do médico
    minhas = [c for c in consultas if c['medico_cpf'] == medico_cpf and c.get('status') != 'cancelada']

    # Enriquecer nomes de pacientes
    mapa_nomes = {u['CPF']: u['nome'] for u in usuarios}
    for c in minhas:
        c['paciente_nome'] = mapa_nomes.get(c.get('paciente_cpf', ''), c.get('paciente_cpf', ''))

    # Ordenar por data/hora
    try:
        minhas.sort(key=lambda x: (x['data'], x['hora']))
    except Exception:
        pass

    return render_template('agendamedico.html', medico=medico, consultas=minhas)


from flask import session, flash

@app.route('/agendapaciente')
def agendapaciente():
    usuarios = carregar_usuarios()
    consultas = carregar_consultas()

    # Tenta pegar o CPF do paciente da sessão; se não tiver, permite via querystring (útil pra teste)
    paciente_cpf = (session.get('cpf') or request.args.get('paciente_cpf') or '').replace('.', '').replace('-', '').strip()
    if not paciente_cpf:
        return "CPF do paciente não encontrado (faça login ou use ?paciente_cpf=XXXXXXXXXXX)", 400

    # Consultas do paciente (todas, exceto canceladas — se quiser mostrar canceladas, remova o filtro)
    minhas = [c for c in consultas if c['paciente_cpf'] == paciente_cpf]

    # Enriquecer nomes e ordenar
    mapa_nomes = {u['CPF']: u['nome'] for u in usuarios}
    for c in minhas:
        c['medico_nome'] = mapa_nomes.get(c.get('medico_cpf', ''), c.get('medico_cpf', '—'))

    try:
        minhas.sort(key=lambda x: (x['data'], x['hora']))
    except:
        pass

    # Lista de médicos para o select do formulário
    medicos = [u for u in usuarios if u.get('tipo') == 'medico']

    return render_template('agendapaciente.html',
                           consultas=minhas,
                           medicos=medicos,
                           paciente_cpf=paciente_cpf)


@app.route('/solicitar_consulta', methods=['POST'])
def solicitar_consulta():
    usuarios = carregar_usuarios()
    consultas = carregar_consultas()

    # CPF do paciente: preferir sessão; se não houver, pega do form (hidden)
    paciente_cpf = (session.get('cpf') or request.form.get('paciente_cpf') or '').replace('.', '').replace('-', '').strip()
    medico_cpf   = (request.form.get('medico_cpf') or '').replace('.', '').replace('-', '').strip()
    data         = request.form.get('data') or ''
    hora         = request.form.get('hora') or ''
    tipo         = request.form.get('tipo') or 'Consulta'
    obs          = request.form.get('observacoes') or ''

    # Valida pac
    if not paciente_cpf or not data or not hora:
        flash('Preencha pelo menos Data e Hora. Médico é opcional na solicitação.', 'erro')
        return redirect(url_for('agendapaciente', paciente_cpf=paciente_cpf))

    # (Opcional) checar se paciente existe
    existe_paciente = any(u for u in usuarios if u['CPF'] == paciente_cpf and u.get('tipo', 'paciente') == 'paciente')
    if not existe_paciente:
        flash('Paciente inválido.', 'erro')
        return redirect(url_for('agendapaciente', paciente_cpf=paciente_cpf))

    # Se médico informado, validar que existe (mas não bloquear se você quiser permitir vazio)
    if medico_cpf:
        existe_medico = any(u for u in usuarios if u['CPF'] == medico_cpf and u.get('tipo') == 'medico')
        if not existe_medico:
            flash('Médico inválido.', 'erro')
            return redirect(url_for('agendapaciente', paciente_cpf=paciente_cpf))

    nova = {
        "id": gerar_id_consulta(consultas),
        "paciente_cpf": paciente_cpf,
        "medico_cpf": medico_cpf,   # pode ser "" se paciente não escolheu
        "data": data,
        "hora": hora,
        "tipo": tipo,
        "status": "solicitada",
        "observacoes": obs
    }
    consultas.append(nova)
    salvar_consultas(consultas)
    flash('Solicitação enviada! Aguarde confirmação do administrador.', 'ok')

    return redirect(url_for('agendapaciente', paciente_cpf=paciente_cpf))

@app.route('/concluir_consulta', methods=['POST'])
def concluir_consulta():
    consulta_id = (request.form.get('id') or '').strip()
    consultas = carregar_consultas()

    alterou = False
    for c in consultas:
        if str(c.get('id')) == str(consulta_id):
            c['status'] = 'concluida'
            alterou = True
            break

    if alterou:
        salvar_consultas(consultas)
        flash('Consulta marcada como concluída.', 'ok')
    else:
        flash('Consulta não encontrada.', 'erro')

    return redirect(url_for('agendamedico'))

from flask import session, redirect, url_for, flash

@app.route('/logout')
def logout():
    session.clear()  # limpa todos os dados da sessão
    flash('Você saiu com sucesso.', 'ok')
    return redirect(url_for('index'))


@app.route('/medicosadmin')
def medicosadmin():
    usuarios = carregar_usuarios()
    busca = request.args.get('busca', '').strip().lower()
    usuarios = [u for u in usuarios if u.get('tipo') in ['medico']]

    # Filtra os usuários
    if busca:
        usuarios = [u for u in usuarios if busca in u['nome'].lower() or busca in u['CPF']]

     # 🔹 Formata os CPFs antes de enviar pro template
    for u in usuarios:
        cpf = u.get('CPF', '')
        if len(cpf) == 11 and cpf.isdigit():
            u['CPF'] = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
        else:
            # Caso o CPF esteja com outro formato (como 0001 dos usuários fixos)
            u['CPF'] = cpf
        
        # Nome com inicial maiúscula (e resto minúsculo)
        nome = u.get('nome', '')
        u['nome'] = nome.title()

        # Tipo com primeira letra maiúscula (Admin, Medico, Paciente)
        tipo = u.get('tipo', '')
        u['tipo'] = tipo.title()

    return render_template('medicosadmin.html', usuarios=usuarios)

if __name__ == '__main__':
    inicializar_usuarios_fixos()
    app.run(debug=True)
