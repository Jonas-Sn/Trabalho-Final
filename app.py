from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, g
)
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'chave_super_secreta_123'

DATABASE = 'database.db'


# ========== Conexão com SQLite ==========

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row  # permite acessar por nome
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()

    # Tabela de usuários (admin, médico, paciente)
    db.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            CPF TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL,
            senha TEXT NOT NULL,
            tipo TEXT NOT NULL,      -- 'admin', 'medico', 'paciente'
            cargo TEXT               -- especialidade do médico (ou NULL)
        );
    """)

    # Tabela de consultas
    db.execute("""
        CREATE TABLE IF NOT EXISTS consultas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_cpf TEXT NOT NULL,
            medico_cpf   TEXT NOT NULL,
            data         TEXT NOT NULL,  -- 'YYYY-MM-DD'
            hora         TEXT NOT NULL,  -- 'HH:MM'
            tipo         TEXT NOT NULL,  -- 'Consulta', 'Retorno', etc
            status       TEXT NOT NULL,  -- 'solicitada', 'agendada', 'concluida', 'cancelada'
            observacoes  TEXT,
            resumo       TEXT,
            conclusao    TEXT,
            cargo        TEXT
        );
    """)

    # Tabela de notificações
    db.execute("""
        CREATE TABLE IF NOT EXISTS notificacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cpf   TEXT NOT NULL,
            texto TEXT NOT NULL,
            lida  INTEGER NOT NULL DEFAULT 0,
            data  TEXT NOT NULL
        );
    """)

    db.commit()


def inicializar_usuarios_fixos():
    """Cria admin e médico padrão se ainda não existirem."""
    db = get_db()

    usuarios_fixos = [
        {
            "nome": "Administrador",
            "CPF": "00000000001",
            "senha": "admin",
            "tipo": "admin",
            "cargo": "Administrador"
        },
        {
            "nome": "Dr. Carlos Silva",
            "CPF": "00000000002",
            "senha": "medico123",
            "tipo": "medico",
            "cargo": "Clínico Geral"
        },
        {
            "nome": "Dr. Evandro",
            "CPF": "00000000003",
            "senha": "medico123",
            "tipo": "medico",
            "cargo": "Nutricionista"
        },
        {
            "nome": "Dra. Sonia",
            "CPF": "00000000004",
            "senha": "medico123",
            "tipo": "medico",
            "cargo": "Pediatra"
        },
    ]

    for u in usuarios_fixos:
        cur = db.execute("SELECT 1 FROM usuarios WHERE CPF = ?", (u["CPF"],))
        if cur.fetchone() is None:
            db.execute(
                "INSERT INTO usuarios (CPF, nome, senha, tipo, cargo) VALUES (?,?,?,?,?)",
                (u["CPF"], u["nome"], u["senha"], u["tipo"], u["cargo"])
            )

    db.commit()


# ========== Rotas básicas ==========

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form['usuario']
        cpf = request.form['CPF']
        senha = request.form['senha']

        cpf = cpf.strip().replace(".", "").replace("-", "")
        if not cpf.isdigit() or len(cpf) != 11:
            return render_template('cadastro.html',
                                   erro="CPF inválido! Deve conter 11 dígitos numéricos.")

        db = get_db()

        cur = db.execute("SELECT 1 FROM usuarios WHERE CPF = ?", (cpf,))
        if cur.fetchone():
            return render_template('cadastro.html', erro="Esse CPF já está cadastrado!")

        db.execute(
            "INSERT INTO usuarios (CPF, nome, senha, tipo) VALUES (?, ?, ?, ?)",
            (cpf, nome, senha, 'paciente')
        )
        db.commit()
        return redirect(url_for('index'))

    return render_template('cadastro.html')


@app.route('/login', methods=['POST'])
def login():
    cpf = request.form['cpf']
    senha = request.form['senha']

    cpf = cpf.strip().replace('.', '').replace('-', '')

    db = get_db()
    cur = db.execute(
        "SELECT * FROM usuarios WHERE CPF = ? AND senha = ?",
        (cpf, senha)
    )
    u = cur.fetchone()

    if u:
        tipo = u["tipo"] if u["tipo"] else 'paciente'
        session['cpf'] = u["CPF"]
        session['tipo'] = tipo

        if tipo == 'admin':
            return redirect(url_for('dashboardadmin'))
        elif tipo == 'medico':
            return redirect(url_for('agendamedico'))
        else:
            return redirect(url_for('agendapaciente'))

    return render_template('index.html', erro="CPF ou senha incorretos!")


# ========== Admin - Clientes ==========

@app.route('/clientesadmin')
def clientesadmin():
    db = get_db()
    busca = (request.args.get('busca') or '').strip().lower()

    cur = db.execute("SELECT CPF, nome, senha, tipo, cargo FROM usuarios")
    usuarios = [dict(r) for r in cur.fetchall()]

    # Filtra só admin e pacientes
    usuarios = [u for u in usuarios if u.get('tipo') in ['admin', 'paciente']]

    if busca:
        usuarios = [
            u for u in usuarios
            if busca in u.get('nome', '').lower() or busca in u.get('CPF', '')
        ]

    for u in usuarios:
        cpf = u.get('CPF', '')
        if len(cpf) == 11 and cpf.isdigit():
            u['CPF'] = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
        else:
            u['CPF'] = cpf

        u['nome'] = (u.get('nome') or '').title()
        u['tipo'] = (u.get('tipo') or '').title()

    return render_template('clientesadmin.html', usuarios=usuarios)


@app.route('/novo_cliente', methods=['POST'])
def novo_cliente():
    nome = request.form['nome']
    cpf = request.form['CPF'].strip().replace('.', '').replace('-', '')
    senha = request.form['senha']

    db = get_db()

    cur = db.execute("SELECT 1 FROM usuarios WHERE CPF = ?", (cpf,))
    if cur.fetchone():
        flash('Este CPF já está cadastrado!', 'erro')
        return redirect(url_for('clientesadmin'))

    db.execute(
        "INSERT INTO usuarios (CPF, nome, senha, tipo) VALUES (?,?,?,?)",
        (cpf, nome, senha, 'paciente')
    )
    db.commit()
    flash('Cliente cadastrado com sucesso!', 'ok')
    return redirect(url_for('clientesadmin'))


@app.route('/remover_cliente', methods=['POST'])
def remover_cliente():
    cpf = (request.form.get('CPF') or '').replace('.', '').replace('-', '').strip()

    db = get_db()
    cur = db.execute("DELETE FROM usuarios WHERE CPF = ?", (cpf,))
    if cur.rowcount > 0:
        db.commit()
        flash('Cliente removido com sucesso!', 'ok')
    else:
        flash('Cliente não encontrado.', 'erro')

    return redirect(url_for('clientesadmin'))


@app.route('/salvar_edicao_cliente', methods=['POST'])
def salvar_edicao_cliente():
    cpf_original = (request.form.get('cpf_original') or '').replace('.', '').replace('-', '')
    nome = (request.form.get('nome') or '').strip().title()
    novo_cpf = ''.join(filter(str.isdigit, request.form.get('CPF') or ''))
    tipo = (request.form.get('tipo') or '').lower()
    cargo = (request.form.get('cargo') or '').strip()

    db = get_db()

    cur = db.execute("SELECT * FROM usuarios WHERE CPF = ?", (cpf_original,))
    u = cur.fetchone()

    if not u:
        flash('Registro não encontrado.', 'erro')
        return redirect(url_for('clientesadmin'))

    db.execute(
        "UPDATE usuarios SET nome = ?, CPF = ?, tipo = ?, cargo = ? WHERE CPF = ?",
        (nome, novo_cpf, tipo, cargo if cargo else None, cpf_original)
    )
    db.commit()
    flash('Registro atualizado com sucesso!', 'ok')

    if tipo == 'medico':
        return redirect(url_for('medicosadmin'))
    else:
        return redirect(url_for('clientesadmin'))


# ========== Admin - Médicos ==========

@app.route('/novo_medico', methods=['POST'])
def novo_medico():
    nome = request.form['nome']
    cpf = request.form['CPF'].strip().replace('.', '').replace('-', '')
    senha = request.form['senha']
    cargo = (request.form.get('cargo') or '').strip()

    if not cargo:
        flash('Informe o cargo/especialidade do médico.', 'erro')
        return redirect(url_for('medicosadmin'))

    db = get_db()

    cur = db.execute("SELECT 1 FROM usuarios WHERE CPF = ?", (cpf,))
    if cur.fetchone():
        flash('Este CPF já está cadastrado!', 'erro')
        return redirect(url_for('medicosadmin'))

    db.execute(
        "INSERT INTO usuarios (CPF, nome, senha, tipo, cargo) VALUES (?,?,?,?,?)",
        (cpf, nome, senha, 'medico', cargo)
    )
    db.commit()
    flash('Médico cadastrado com sucesso!', 'ok')
    return redirect(url_for('medicosadmin'))


@app.route('/remover_medico', methods=['POST'])
def remover_medico():
    cpf = (request.form.get('CPF') or '').replace('.', '').replace('-', '').strip()
    db = get_db()

    cur = db.execute("DELETE FROM usuarios WHERE CPF = ?", (cpf,))
    if cur.rowcount > 0:
        db.commit()
        flash('Médico removido com sucesso!', 'ok')
    else:
        flash('Médico não encontrado.', 'erro')

    return redirect(url_for('medicosadmin'))


@app.route('/medicosadmin')
def medicosadmin():
    db = get_db()
    busca = (request.args.get('busca') or '').strip().lower()

    cur = db.execute("SELECT CPF, nome, tipo, cargo FROM usuarios WHERE tipo = 'medico'")
    usuarios = [dict(r) for r in cur.fetchall()]

    if busca:
        usuarios = [
            u for u in usuarios
            if busca in (u.get('nome') or '').lower() or busca in (u.get('CPF') or '')
        ]

    for u in usuarios:
        cpf = u.get('CPF', '')
        if len(cpf) == 11 and cpf.isdigit():
            u['CPF'] = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
        else:
            u['CPF'] = cpf
        u['nome'] = (u.get('nome') or '').title()

    return render_template('medicosadmin.html', usuarios=usuarios)


# ========== Admin - Dashboard / Agenda ==========

@app.route('/dashboardadmin')
def dashboardadmin():
    return render_template('dashboardadmin.html')


@app.route('/agendaadmin', methods=['GET', 'POST'])
def agendaadmin():
    db = get_db()

    # POST: criar nova consulta
    if request.method == 'POST':
        paciente_cpf = (request.form.get('paciente_cpf') or '').replace('.', '').replace('-', '').strip()
        cargo = (request.form.get('cargo') or '').strip()
        medico_cpf = (request.form.get('medico_cpf') or '').replace('.', '').replace('-', '').strip()
        data = request.form.get('data') or ''
        hora = request.form.get('hora') or ''
        tipo = request.form.get('tipo') or 'Consulta'
        obs = request.form.get('observacoes') or ''

        if not (paciente_cpf and medico_cpf and data and hora and cargo):
            flash('Preencha todos os campos obrigatórios (paciente, cargo, médico, data e hora).', 'erro')
            return redirect(url_for('agendaadmin'))

        # Valida paciente
        cur = db.execute(
            "SELECT 1 FROM usuarios WHERE CPF = ? AND tipo = 'paciente'",
            (paciente_cpf,)
        )
        existe_paciente = cur.fetchone() is not None

        # Valida médico
        cur = db.execute(
            "SELECT 1 FROM usuarios WHERE CPF = ? AND tipo = 'medico'",
            (medico_cpf,)
        )
        existe_medico = cur.fetchone() is not None

        if not existe_paciente or not existe_medico:
            flash('CPF de paciente ou médico inválido.', 'erro')
            return redirect(url_for('agendaadmin'))

        # Conflito de horário
        cur = db.execute("""
            SELECT 1 FROM consultas
             WHERE medico_cpf = ?
               AND data       = ?
               AND hora       = ?
               AND status    != 'cancelada'
        """, (medico_cpf, data, hora))
        conflito = cur.fetchone() is not None

        if conflito:
            flash('Já existe consulta para esse médico neste horário.', 'erro')
            return redirect(url_for('agendaadmin'))

        db.execute("""
            INSERT INTO consultas
                (paciente_cpf, medico_cpf, data, hora, tipo, status, observacoes, cargo)
            VALUES (?,?,?,?,?,?,?,?)
        """, (paciente_cpf, medico_cpf, data, hora, tipo, 'agendada', obs, cargo))
        db.commit()
        flash('Consulta criada com sucesso!', 'ok')
        return redirect(url_for('agendaadmin'))

    # GET: listagem + filtros
    usuarios = [dict(r) for r in db.execute("SELECT * FROM usuarios").fetchall()]
    consultas = [dict(r) for r in db.execute("SELECT * FROM consultas").fetchall()]

    mapa_nomes = {u['CPF']: u['nome'] for u in usuarios}

    for c in consultas:
        c['paciente_nome'] = mapa_nomes.get(c.get('paciente_cpf', ''), c.get('paciente_cpf', ''))
        c['medico_nome'] = mapa_nomes.get(c.get('medico_cpf', ''), c.get('medico_cpf', ''))

    busca_paciente = (request.args.get('busca_paciente') or '').strip().lower()
    busca_medico = (request.args.get('busca_medico') or '').strip().lower()
    filtro_status = (request.args.get('status') or '').strip().lower()
    filtro_data = (request.args.get('data') or '').strip()

    lista = consultas

    if busca_paciente:
        lista = [
            c for c in lista
            if busca_paciente in (c.get('paciente_nome', '')).lower()
            or busca_paciente in (c.get('paciente_cpf', ''))
        ]

    if busca_medico:
        lista = [c for c in lista if busca_medico in (c.get('medico_nome', '')).lower()]

    if filtro_status:
        lista = [c for c in lista if (c.get('status') or '').lower() == filtro_status]

    if filtro_data:
        lista = [c for c in lista if c.get('data', '') == filtro_data]

    try:
        lista.sort(key=lambda x: (x.get('data', ''), x.get('hora', '')))
    except Exception:
        pass

    medicos = [u for u in usuarios if u.get('tipo') == 'medico']

    return render_template(
        'agendaadmin.html',
        consultas=lista,
        medicos=medicos,
        usuarios=usuarios
    )


@app.route('/aprovar_consulta', methods=['POST'])
def aprovar_consulta():
    consulta_id = (request.form.get('id') or '').strip()
    db = get_db()

    cur = db.execute("SELECT paciente_cpf FROM consultas WHERE id = ?", (consulta_id,))
    consulta = cur.fetchone()

    if not consulta:
        flash('Consulta não encontrada.', 'erro')
        return redirect(url_for('agendaadmin'))

    db.execute("UPDATE consultas SET status = 'agendada' WHERE id = ?", (consulta_id,))
    db.commit()
    flash('Consulta aprovada com sucesso!', 'ok')

    adicionar_notificacao(consulta["paciente_cpf"], "Sua consulta foi aprovada!")
    return redirect(url_for('agendaadmin'))


@app.route('/cancelar_consulta', methods=['POST'])
def cancelar_consulta():
    consulta_id = (request.form.get('id') or '').strip()
    db = get_db()

    cur = db.execute("UPDATE consultas SET status = 'cancelada' WHERE id = ?", (consulta_id,))
    if cur.rowcount > 0:
        db.commit()
        flash('Consulta cancelada.', 'ok')
    else:
        flash('Consulta não encontrada.', 'erro')

    return redirect(url_for('agendaadmin'))


# ========== Agenda Médico ==========

@app.route('/agendamedico')
def agendamedico():
    db = get_db()
    medico_cpf = (session.get('cpf') or request.args.get('medico_cpf') or '').replace('.', '').replace('-', '').strip()

    if not medico_cpf:
        return "Informe medico_cpf na querystring ou faça login como médico.", 400

    cur = db.execute("SELECT * FROM usuarios WHERE CPF = ? AND tipo = 'medico'", (medico_cpf,))
    medico = cur.fetchone()
    if not medico:
        return "Médico não encontrado ou não autorizado.", 403

    # Consultas deste médico (exceto canceladas)
    cur = db.execute("""
        SELECT * FROM consultas
         WHERE medico_cpf = ?
           AND status != 'cancelada'
    """, (medico_cpf,))
    minhas = [dict(r) for r in cur.fetchall()]

    # Mapa CPF -> nome
    mapa_nomes = {r['CPF']: r['nome'] for r in db.execute("SELECT CPF, nome FROM usuarios").fetchall()}

    for c in minhas:
        c['paciente_nome'] = mapa_nomes.get(c.get('paciente_cpf', ''), c.get('paciente_cpf', ''))

        paciente_cpf = c.get('paciente_cpf')

        # Histórico: consultas concluídas desse paciente (qualquer médico)
        cur_hist = db.execute("""
            SELECT * FROM consultas
             WHERE paciente_cpf = ?
               AND status = 'concluida'
             ORDER BY data DESC, hora DESC
        """, (paciente_cpf,))
        historico_rows = cur_hist.fetchall()

        historico = []
        for h in historico_rows:
            historico.append({
                'data': h['data'],
                'hora': h['hora'],
                'tipo': h['tipo'],
                'status': h['status'],
                'medico_nome': mapa_nomes.get(h['medico_cpf'], h['medico_cpf']),
                'resumo': h['resumo'],
                'conclusao': h['conclusao']
            })

        c['historico'] = historico

    try:
        minhas.sort(key=lambda x: (x.get('data', ''), x.get('hora', '')))
    except Exception:
        pass

    return render_template('agendamedico.html', medico=medico, consultas=minhas)


# ========== Agenda Paciente ==========

@app.route('/agendapaciente')
def agendapaciente():
    db = get_db()

    paciente_cpf = (session.get('cpf') or request.args.get('paciente_cpf') or '').replace('.', '').replace('-', '').strip()
    if not paciente_cpf:
        return "CPF do paciente não encontrado (faça login ou use ?paciente_cpf=XXXXXXXXXXX)", 400

    cur = db.execute("""
        SELECT * FROM consultas
         WHERE paciente_cpf = ?
         ORDER BY data, hora
    """, (paciente_cpf,))
    minhas = [dict(r) for r in cur.fetchall()]

    mapa_nomes = {r['CPF']: r['nome'] for r in db.execute("SELECT CPF, nome FROM usuarios").fetchall()}

    for c in minhas:
        c['medico_nome'] = mapa_nomes.get(c.get('medico_cpf', ''), c.get('medico_cpf', '—'))

    medicos = [dict(r) for r in db.execute("SELECT * FROM usuarios WHERE tipo = 'medico'").fetchall()]
    cargos = sorted({m.get('cargo') for m in medicos if m.get('cargo')})

    return render_template(
        'agendapaciente.html',
        consultas=minhas,
        medicos=medicos,
        cargos=cargos,
        paciente_cpf=paciente_cpf
    )

@app.route('/horarios_disponiveis')
def horarios_disponiveis():
    db = get_db()

    data = request.args.get("data") or ""
    medico_cpf = (request.args.get("medico_cpf") or "").replace(".", "").replace("-", "").strip()
    cargo = (request.args.get("cargo") or "").strip()

    # Se não tiver data, não tem o que fazer
    if not data:
        return jsonify({"horarios": []})

    # Se não veio médico, mas veio cargo, tenta escolher um médico pelo cargo
    if not medico_cpf and cargo:
        cur = db.execute(
            "SELECT CPF FROM usuarios WHERE tipo = 'medico' AND cargo = ?",
            (cargo,)
        )
        row = cur.fetchone()
        if row:
            medico_cpf = row["CPF"]

    # Se ainda assim não tem médico, devolve vazio
    if not medico_cpf:
        return jsonify({"horarios": []})

    # Busca horários já ocupados para esse médico nessa data (exceto canceladas)
    cur = db.execute("""
        SELECT hora FROM consultas
         WHERE medico_cpf = ?
           AND data = ?
           AND status != 'cancelada'
    """, (medico_cpf, data))
    ocupados = {r["hora"] for r in cur.fetchall()}

    # Grade padrão de horários (ajuste como quiser)
    base_horarios = []
    for h in range(8, 18):  # 08h até 17h
        for m in (0, 30):   # de 30 em 30 min
            base_horarios.append(f"{h:02d}:{m:02d}")

    # Filtra só horários livres
    livres = [h for h in base_horarios if h not in ocupados]

    return jsonify({"horarios": livres})


@app.route('/solicitar_consulta', methods=['POST'])
def solicitar_consulta():
    db = get_db()

    paciente_cpf = (session.get('cpf') or request.form.get('paciente_cpf') or '').replace('.', '').replace('-', '').strip()
    cargo = (request.form.get('cargo') or '').strip()
    medico_cpf = (request.form.get('medico_cpf') or '').replace('.', '').replace('-', '').strip()
    data = request.form.get('data') or ''
    hora = request.form.get('hora') or ''
    tipo = request.form.get('tipo') or 'Consulta'
    obs = request.form.get('observacoes') or ''

    if not paciente_cpf or not data or not hora or not cargo:
        flash('Preencha Data, Hora e selecione um Cargo/Especialidade. Médico é opcional.', 'erro')
        return redirect(url_for('agendapaciente', paciente_cpf=paciente_cpf))

    cur = db.execute(
        "SELECT 1 FROM usuarios WHERE CPF = ? AND tipo = 'paciente'",
        (paciente_cpf,)
    )
    if cur.fetchone() is None:
        flash('Paciente inválido.', 'erro')
        return redirect(url_for('agendapaciente', paciente_cpf=paciente_cpf))

    # Médicos daquele cargo
    medicos_do_cargo = [r for r in db.execute(
        "SELECT * FROM usuarios WHERE tipo = 'medico' AND cargo = ?",
        (cargo,)
    ).fetchall()]

    if not medicos_do_cargo:
        flash('Não há médicos cadastrados para o cargo selecionado.', 'erro')
        return redirect(url_for('agendapaciente', paciente_cpf=paciente_cpf))

    medico_escolhido = None

    if medico_cpf:
        medico_escolhido = next((m for m in medicos_do_cargo if m['CPF'] == medico_cpf), None)
        if not medico_escolhido:
            flash('Médico inválido para o cargo selecionado.', 'erro')
            return redirect(url_for('agendapaciente', paciente_cpf=paciente_cpf))
    else:
        medico_escolhido = medicos_do_cargo[0]
        medico_cpf = medico_escolhido['CPF']

    # Insere como SOLICITADA
    db.execute("""
        INSERT INTO consultas
            (paciente_cpf, medico_cpf, data, hora, tipo, status, observacoes, cargo)
        VALUES (?,?,?,?,?,?,?,?)
    """, (paciente_cpf, medico_cpf, data, hora, tipo, 'solicitada', obs, cargo))
    db.commit()

    flash(f'Solicitação enviada! Médico atribuído: {medico_escolhido["nome"]}.', 'ok')
    adicionar_notificacao(paciente_cpf, "Sua consulta foi solicitada e aguarda aprovação.")
    return redirect(url_for('agendapaciente', paciente_cpf=paciente_cpf))


@app.route('/concluir_consulta', methods=['POST'])
def concluir_consulta():
    consulta_id = (request.form.get('id') or '').strip()
    resumo = (request.form.get('resumo') or '').strip()
    conclusao = (request.form.get('conclusao') or '').strip()

    db = get_db()

    cur = db.execute("SELECT * FROM consultas WHERE id = ?", (consulta_id,))
    c = cur.fetchone()

    if not c:
        flash('Consulta não encontrada.', 'erro')
        return redirect(url_for('agendamedico'))

    # Só permite concluir se estiver AGENDADA
    if c["status"] != 'agendada':
        flash('Somente consultas agendadas podem ser concluídas.', 'erro')
        return redirect(url_for('agendamedico'))

    db.execute("""
        UPDATE consultas
           SET status    = 'concluida',
               resumo    = ?,
               conclusao = ?
         WHERE id = ?
    """, (resumo, conclusao, consulta_id))
    db.commit()

    flash('Consulta marcada como concluída e registrada no histórico.', 'ok')
    adicionar_notificacao(c["paciente_cpf"], "Sua consulta foi concluída! Veja o resumo no histórico.")
    return redirect(url_for('agendamedico'))




# ========== Logout ==========

@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu com sucesso.', 'ok')
    return redirect(url_for('index'))


# ========== Notificações ==========

def adicionar_notificacao(cpf, texto):
    db = get_db()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.execute(
        "INSERT INTO notificacoes (cpf, texto, lida, data) VALUES (?,?,0,?)",
        (cpf, texto, agora)
    )
    db.commit()


@app.route("/notificacoes_count")
def notificacoes_count():
    cpf = session.get("cpf")
    if not cpf:
        return {"count": 0}

    db = get_db()
    cur = db.execute(
        "SELECT COUNT(*) AS qtd FROM notificacoes WHERE cpf = ? AND lida = 0",
        (cpf,)
    )
    row = cur.fetchone()
    return {"count": row["qtd"] if row else 0}


@app.route("/notificacoes_lista")
def notificacoes_lista():
    cpf = session.get("cpf")
    if not cpf:
        return jsonify([])

    db = get_db()
    cur = db.execute("""
        SELECT texto, lida, data
          FROM notificacoes
         WHERE cpf = ?
         ORDER BY data DESC
    """, (cpf,))
    notificacoes = [dict(r) for r in cur.fetchall()]
    return jsonify(notificacoes)


@app.route("/notificacoes_marcar_lidas", methods=["POST"])
def notificacoes_marcar_lidas():
    cpf = session.get("cpf")
    if not cpf:
        return ("", 204)

    db = get_db()
    db.execute("UPDATE notificacoes SET lida = 1 WHERE cpf = ?", (cpf,))
    db.commit()
    return ("", 204)


# ========== Main ==========

if __name__ == '__main__':
    with app.app_context():
        init_db()
        inicializar_usuarios_fixos()
    app.run(debug=True)
