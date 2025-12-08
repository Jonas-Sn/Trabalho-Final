from datetime import datetime
import sqlite3

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, g
)

app = Flask(__name__)
app.secret_key = "chave_super_secreta_123"

DATABASE = "database.db"

# ---------------------------------------------------------------------
# Constantes simples para evitar "strings mágicas" espalhadas
# ---------------------------------------------------------------------

TIPO_ADMIN = "admin"
TIPO_MEDICO = "medico"
TIPO_PACIENTE = "paciente"

STATUS_SOLICITADA = "solicitada"
STATUS_AGENDADA = "agendada"
STATUS_CONCLUIDA = "concluida"
STATUS_CANCELADA = "cancelada"


# ---------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------

def get_db():
    """Abre conexão com o SQLite para a requisição atual."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """Fecha a conexão ao final do ciclo da requisição."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def normalizar_cpf(cpf: str) -> str:
    """Remove pontos e traços, mantendo só dígitos."""
    return "".join(filter(str.isdigit, cpf or ""))


def formatar_cpf(cpf: str) -> str:
    """Formata CPF como 000.000.000-00, se tiver 11 dígitos."""
    cpf_limpo = normalizar_cpf(cpf)
    if len(cpf_limpo) == 11:
        return f"{cpf_limpo[:3]}.{cpf_limpo[3:6]}.{cpf_limpo[6:9]}-{cpf_limpo[9:]}"
    return cpf or ""


def init_db():
    """Cria as tabelas, se ainda não existirem."""
    db = get_db()

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            CPF   TEXT UNIQUE NOT NULL,
            nome  TEXT NOT NULL,
            senha TEXT NOT NULL,
            tipo  TEXT NOT NULL,  -- admin, medico, paciente
            cargo TEXT            -- especialidade do médico (ou NULL)
        );
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS consultas (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_cpf TEXT NOT NULL,
            medico_cpf   TEXT NOT NULL,
            data         TEXT NOT NULL,  -- YYYY-MM-DD
            hora         TEXT NOT NULL,  -- HH:MM
            tipo         TEXT NOT NULL,  -- Consulta, Retorno etc
            status       TEXT NOT NULL,  -- solicitada, agendada, concluida, cancelada
            observacoes  TEXT,
            resumo       TEXT,
            conclusao    TEXT,
            cargo        TEXT
        );
        """
    )

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS notificacoes (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            cpf   TEXT NOT NULL,
            texto TEXT NOT NULL,
            lida  INTEGER NOT NULL DEFAULT 0,
            data  TEXT NOT NULL
        );
        """
    )

    db.commit()


def inicializar_usuarios_fixos():
    """
    Cria alguns usuários padrão (admin, médicos e um paciente),
    só se ainda não existirem.
    """
    db = get_db()

    usuarios_fixos = [
        {
            "nome": "Administrador",
            "CPF": "00000000001",
            "senha": "admin",
            "tipo": TIPO_ADMIN,
            "cargo": "Administrador",
        },
        {
            "nome": "Dr. Carlos Silva",
            "CPF": "00000000002",
            "senha": "medico123",
            "tipo": TIPO_MEDICO,
            "cargo": "Clínico Geral",
        },
        {
            "nome": "Dr. Evandro",
            "CPF": "00000000003",
            "senha": "medico123",
            "tipo": TIPO_MEDICO,
            "cargo": "Nutricionista",
        },
        {
            "nome": "Dra. Sonia",
            "CPF": "00000000004",
            "senha": "medico123",
            "tipo": TIPO_MEDICO,
            "cargo": "Pediatra",
        },
        {
            "nome": "Cristiano",
            "CPF": "11111111111",
            "senha": "1234",
            "tipo": TIPO_PACIENTE,
            "cargo": None,
        },
    ]

    for u in usuarios_fixos:
        cur = db.execute("SELECT 1 FROM usuarios WHERE CPF = ?", (u["CPF"],))
        if cur.fetchone() is None:
            db.execute(
                """
                INSERT INTO usuarios (CPF, nome, senha, tipo, cargo)
                VALUES (?, ?, ?, ?, ?)
                """,
                (u["CPF"], u["nome"], u["senha"], u["tipo"], u["cargo"]),
            )

    db.commit()


def adicionar_notificacao(cpf: str, texto: str):
    """Insere uma notificação simples para um usuário."""
    db = get_db()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M")
    db.execute(
        "INSERT INTO notificacoes (cpf, texto, lida, data) VALUES (?, ?, 0, ?)",
        (cpf, texto, agora),
    )
    db.commit()


# ---------------------------------------------------------------------
# Rotas principais / autenticação
# ---------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        nome = request.form.get("usuario", "").strip()
        cpf = normalizar_cpf(request.form.get("CPF", ""))
        senha = request.form.get("senha", "")

        if not cpf.isdigit() or len(cpf) != 11:
            return render_template(
                "cadastro.html",
                erro="CPF inválido! Deve conter 11 dígitos numéricos.",
            )

        db = get_db()
        cur = db.execute("SELECT 1 FROM usuarios WHERE CPF = ?", (cpf,))
        if cur.fetchone():
            return render_template(
                "cadastro.html",
                erro="Esse CPF já está cadastrado!",
            )

        db.execute(
            "INSERT INTO usuarios (CPF, nome, senha, tipo) VALUES (?, ?, ?, ?)",
            (cpf, nome, senha, TIPO_PACIENTE),
        )
        db.commit()
        return redirect(url_for("index"))

    return render_template("cadastro.html")


@app.route("/login", methods=["POST"])
def login():
    cpf = normalizar_cpf(request.form.get("cpf", ""))
    senha = request.form.get("senha", "")

    db = get_db()
    cur = db.execute(
        "SELECT * FROM usuarios WHERE CPF = ? AND senha = ?",
        (cpf, senha),
    )
    usuario = cur.fetchone()

    if not usuario:
        return render_template("index.html", erro="CPF ou senha incorretos!")

    tipo = usuario["tipo"] or TIPO_PACIENTE
    session["cpf"] = usuario["CPF"]
    session["tipo"] = tipo

    if tipo == TIPO_ADMIN:
        return redirect(url_for("dashboardadmin"))
    if tipo == TIPO_MEDICO:
        return redirect(url_for("agendamedico"))
    return redirect(url_for("agendapaciente"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Você saiu com sucesso.", "ok")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------
# Admin - clientes (pacientes e admins)
# ---------------------------------------------------------------------

@app.route("/clientesadmin")
def clientesadmin():
    db = get_db()
    busca = (request.args.get("busca") or "").strip().lower()

    cur = db.execute("SELECT CPF, nome, senha, tipo, cargo FROM usuarios")
    usuarios = [dict(r) for r in cur.fetchall()]

    # mantém somente admins e pacientes
    usuarios = [
        u for u in usuarios if u.get("tipo") in (TIPO_ADMIN, TIPO_PACIENTE)
    ]

    if busca:
        usuarios = [
            u
            for u in usuarios
            if busca in (u.get("nome") or "").lower()
            or busca in (u.get("CPF") or "")
        ]

    for u in usuarios:
        u["CPF"] = formatar_cpf(u.get("CPF", ""))
        u["nome"] = (u.get("nome") or "").title()
        u["tipo"] = (u.get("tipo") or "").title()

    return render_template("clientesadmin.html", usuarios=usuarios)


@app.route("/novo_cliente", methods=["POST"])
def novo_cliente():
    nome = (request.form.get("nome") or "").strip()
    cpf = normalizar_cpf(request.form.get("CPF", ""))
    senha = request.form.get("senha", "")

    db = get_db()
    cur = db.execute("SELECT 1 FROM usuarios WHERE CPF = ?", (cpf,))
    if cur.fetchone():
        flash("Este CPF já está cadastrado!", "erro")
        return redirect(url_for("clientesadmin"))

    db.execute(
        "INSERT INTO usuarios (CPF, nome, senha, tipo) VALUES (?, ?, ?, ?)",
        (cpf, nome, senha, TIPO_PACIENTE),
    )
    db.commit()
    flash("Cliente cadastrado com sucesso!", "ok")
    return redirect(url_for("clientesadmin"))


@app.route("/remover_cliente", methods=["POST"])
def remover_cliente():
    cpf = normalizar_cpf(request.form.get("CPF") or "")

    db = get_db()
    cur = db.execute("DELETE FROM usuarios WHERE CPF = ?", (cpf,))
    if cur.rowcount > 0:
        db.commit()
        flash("Cliente removido com sucesso!", "ok")
    else:
        flash("Cliente não encontrado.", "erro")

    return redirect(url_for("clientesadmin"))


@app.route("/salvar_edicao_cliente", methods=["POST"])
def salvar_edicao_cliente():
    cpf_original = normalizar_cpf(request.form.get("cpf_original") or "")
    nome = (request.form.get("nome") or "").strip().title()
    novo_cpf = normalizar_cpf(request.form.get("CPF") or "")
    tipo = (request.form.get("tipo") or "").lower()
    cargo = (request.form.get("cargo") or "").strip() or None

    db = get_db()

    cur = db.execute("SELECT * FROM usuarios WHERE CPF = ?", (cpf_original,))
    registro = cur.fetchone()
    if not registro:
        flash("Registro não encontrado.", "erro")
        return redirect(url_for("clientesadmin"))

    db.execute(
        """
        UPDATE usuarios
           SET nome = ?, CPF = ?, tipo = ?, cargo = ?
         WHERE CPF = ?
        """,
        (nome, novo_cpf, tipo, cargo, cpf_original),
    )
    db.commit()
    flash("Registro atualizado com sucesso!", "ok")

    if tipo == TIPO_MEDICO:
        return redirect(url_for("medicosadmin"))
    return redirect(url_for("clientesadmin"))


# ---------------------------------------------------------------------
# Admin - médicos
# ---------------------------------------------------------------------

@app.route("/medicosadmin")
def medicosadmin():
    db = get_db()
    busca = (request.args.get("busca") or "").strip().lower()

    cur = db.execute(
        "SELECT CPF, nome, tipo, cargo FROM usuarios WHERE tipo = ?",
        (TIPO_MEDICO,),
    )
    usuarios = [dict(r) for r in cur.fetchall()]

    if busca:
        usuarios = [
            u
            for u in usuarios
            if busca in (u.get("nome") or "").lower()
            or busca in (u.get("CPF") or "")
        ]

    for u in usuarios:
        u["CPF"] = formatar_cpf(u.get("CPF", ""))
        u["nome"] = (u.get("nome") or "").title()

    return render_template("medicosadmin.html", usuarios=usuarios)


@app.route("/novo_medico", methods=["POST"])
def novo_medico():
    nome = (request.form.get("nome") or "").strip()
    cpf = normalizar_cpf(request.form.get("CPF") or "")
    senha = request.form.get("senha", "")
    cargo = (request.form.get("cargo") or "").strip()

    if not cargo:
        flash("Informe o cargo/especialidade do médico.", "erro")
        return redirect(url_for("medicosadmin"))

    db = get_db()
    cur = db.execute("SELECT 1 FROM usuarios WHERE CPF = ?", (cpf,))
    if cur.fetchone():
        flash("Este CPF já está cadastrado!", "erro")
        return redirect(url_for("medicosadmin"))

    db.execute(
        """
        INSERT INTO usuarios (CPF, nome, senha, tipo, cargo)
        VALUES (?, ?, ?, ?, ?)
        """,
        (cpf, nome, senha, TIPO_MEDICO, cargo),
    )
    db.commit()
    flash("Médico cadastrado com sucesso!", "ok")
    return redirect(url_for("medicosadmin"))


@app.route("/remover_medico", methods=["POST"])
def remover_medico():
    cpf = normalizar_cpf(request.form.get("CPF") or "")

    db = get_db()
    cur = db.execute("DELETE FROM usuarios WHERE CPF = ?", (cpf,))
    if cur.rowcount > 0:
        db.commit()
        flash("Médico removido com sucesso!", "ok")
    else:
        flash("Médico não encontrado.", "erro")

    return redirect(url_for("medicosadmin"))


# ---------------------------------------------------------------------
# Admin - dashboard / agenda
# ---------------------------------------------------------------------

@app.route("/dashboardadmin")
def dashboardadmin():
    return render_template("dashboardadmin.html")


@app.route("/agendaadmin", methods=["GET", "POST"])
def agendaadmin():
    db = get_db()

    if request.method == "POST":
        paciente_cpf = normalizar_cpf(request.form.get("paciente_cpf") or "")
        medico_cpf = normalizar_cpf(request.form.get("medico_cpf") or "")
        cargo = (request.form.get("cargo") or "").strip()
        data = request.form.get("data") or ""
        hora = request.form.get("hora") or ""
        tipo = request.form.get("tipo") or "Consulta"
        obs = request.form.get("observacoes") or ""

        if not (paciente_cpf and medico_cpf and data and hora and cargo):
            flash(
                "Preencha todos os campos obrigatórios (paciente, cargo, médico, data e hora).",
                "erro",
            )
            return redirect(url_for("agendaadmin"))

        # valida paciente
        cur = db.execute(
            "SELECT 1 FROM usuarios WHERE CPF = ? AND tipo = ?",
            (paciente_cpf, TIPO_PACIENTE),
        )
        if cur.fetchone() is None:
            flash("CPF de paciente inválido.", "erro")
            return redirect(url_for("agendaadmin"))

        # valida médico
        cur = db.execute(
            "SELECT 1 FROM usuarios WHERE CPF = ? AND tipo = ?",
            (medico_cpf, TIPO_MEDICO),
        )
        if cur.fetchone() is None:
            flash("CPF de médico inválido.", "erro")
            return redirect(url_for("agendaadmin"))

        # evita conflito de horário
        cur = db.execute(
            """
            SELECT 1
              FROM consultas
             WHERE medico_cpf = ?
               AND data       = ?
               AND hora       = ?
               AND status    != ?
            """,
            (medico_cpf, data, hora, STATUS_CANCELADA),
        )
        if cur.fetchone():
            flash("Já existe consulta para esse médico neste horário.", "erro")
            return redirect(url_for("agendaadmin"))

        db.execute(
            """
            INSERT INTO consultas
                (paciente_cpf, medico_cpf, data, hora, tipo, status, observacoes, cargo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (paciente_cpf, medico_cpf, data, hora, tipo, STATUS_AGENDADA, obs, cargo),
        )
        db.commit()
        flash("Consulta criada com sucesso!", "ok")
        return redirect(url_for("agendaadmin"))

    # GET: listagem com filtros
    usuarios = [dict(r) for r in db.execute("SELECT * FROM usuarios").fetchall()]
    consultas = [dict(r) for r in db.execute("SELECT * FROM consultas").fetchall()]

    mapa_nomes = {u["CPF"]: u["nome"] for u in usuarios}

    for c in consultas:
        c["paciente_nome"] = mapa_nomes.get(
            c.get("paciente_cpf", ""), c.get("paciente_cpf", "")
        )
        c["medico_nome"] = mapa_nomes.get(
            c.get("medico_cpf", ""), c.get("medico_cpf", "")
        )

    busca_paciente = (request.args.get("busca_paciente") or "").strip().lower()
    busca_medico = (request.args.get("busca_medico") or "").strip().lower()
    filtro_status = (request.args.get("status") or "").strip().lower()
    filtro_data = (request.args.get("data") or "").strip()

    lista = consultas

    if busca_paciente:
        lista = [
            c
            for c in lista
            if busca_paciente in (c.get("paciente_nome", "")).lower()
            or busca_paciente in (c.get("paciente_cpf", ""))
        ]

    if busca_medico:
        lista = [
            c
            for c in lista
            if busca_medico in (c.get("medico_nome", "")).lower()
        ]

    if filtro_status:
        lista = [
            c
            for c in lista
            if (c.get("status") or "").lower() == filtro_status
        ]

    if filtro_data:
        lista = [c for c in lista if c.get("data", "") == filtro_data]

    try:
        lista.sort(key=lambda x: (x.get("data", ""), x.get("hora", "")))
    except Exception:
        pass

    medicos = [u for u in usuarios if u.get("tipo") == TIPO_MEDICO]

    return render_template(
        "agendaadmin.html",
        consultas=lista,
        medicos=medicos,
        usuarios=usuarios,
    )


@app.route("/aprovar_consulta", methods=["POST"])
def aprovar_consulta():
    consulta_id = (request.form.get("id") or "").strip()
    db = get_db()

    cur = db.execute(
        "SELECT paciente_cpf FROM consultas WHERE id = ?", (consulta_id,)
    )
    consulta = cur.fetchone()
    if not consulta:
        flash("Consulta não encontrada.", "erro")
        return redirect(url_for("agendaadmin"))

    db.execute(
        "UPDATE consultas SET status = ? WHERE id = ?",
        (STATUS_AGENDADA, consulta_id),
    )
    db.commit()
    flash("Consulta aprovada com sucesso!", "ok")

    adicionar_notificacao(consulta["paciente_cpf"], "Sua consulta foi aprovada!")
    return redirect(url_for("agendaadmin"))


@app.route("/cancelar_consulta", methods=["POST"])
def cancelar_consulta():
    consulta_id = (request.form.get("id") or "").strip()
    db = get_db()

    cur = db.execute(
        "UPDATE consultas SET status = ? WHERE id = ?",
        (STATUS_CANCELADA, consulta_id),
    )
    if cur.rowcount > 0:
        db.commit()
        flash("Consulta cancelada.", "ok")
    else:
        flash("Consulta não encontrada.", "erro")

    return redirect(url_for("agendaadmin"))


# ---------------------------------------------------------------------
# Agenda médico
# ---------------------------------------------------------------------

@app.route("/agendamedico")
def agendamedico():
    db = get_db()
    medico_cpf = normalizar_cpf(
        session.get("cpf") or request.args.get("medico_cpf") or ""
    )

    if not medico_cpf:
        return (
            "Informe medico_cpf na querystring ou faça login como médico.",
            400,
        )

    cur = db.execute(
        "SELECT * FROM usuarios WHERE CPF = ? AND tipo = ?",
        (medico_cpf, TIPO_MEDICO),
    )
    medico = cur.fetchone()
    if not medico:
        return "Médico não encontrado ou não autorizado.", 403

    cur = db.execute(
        """
        SELECT * FROM consultas
         WHERE medico_cpf = ?
           AND status != ?
        """,
        (medico_cpf, STATUS_CANCELADA),
    )
    consultas_medico = [dict(r) for r in cur.fetchall()]

    mapa_nomes = {
        r["CPF"]: r["nome"]
        for r in db.execute("SELECT CPF, nome FROM usuarios").fetchall()
    }

    for c in consultas_medico:
        c["paciente_nome"] = mapa_nomes.get(
            c.get("paciente_cpf", ""), c.get("paciente_cpf", "")
        )

        paciente_cpf = c.get("paciente_cpf")
        cur_hist = db.execute(
            """
            SELECT *
              FROM consultas
             WHERE paciente_cpf = ?
               AND status       = ?
             ORDER BY data DESC, hora DESC
            """,
            (paciente_cpf, STATUS_CONCLUIDA),
        )
        historico_rows = cur_hist.fetchall()
        historico = []
        for h in historico_rows:
            historico.append(
                {
                    "data": h["data"],
                    "hora": h["hora"],
                    "tipo": h["tipo"],
                    "status": h["status"],
                    "medico_nome": mapa_nomes.get(
                        h["medico_cpf"], h["medico_cpf"]
                    ),
                    "resumo": h["resumo"],
                    "conclusao": h["conclusao"],
                }
            )

        c["historico"] = historico

    try:
        consultas_medico.sort(
            key=lambda x: (x.get("data", ""), x.get("hora", ""))
        )
    except Exception:
        pass

    return render_template(
        "agendamedico.html", medico=medico, consultas=consultas_medico
    )


@app.route("/concluir_consulta", methods=["POST"])
def concluir_consulta():
    consulta_id = (request.form.get("id") or "").strip()
    resumo = (request.form.get("resumo") or "").strip()
    conclusao = (request.form.get("conclusao") or "").strip()

    db = get_db()
    cur = db.execute("SELECT * FROM consultas WHERE id = ?", (consulta_id,))
    consulta = cur.fetchone()

    if not consulta:
        flash("Consulta não encontrada.", "erro")
        return redirect(url_for("agendamedico"))

    if consulta["status"] != STATUS_AGENDADA:
        flash("Somente consultas agendadas podem ser concluídas.", "erro")
        return redirect(url_for("agendamedico"))

    db.execute(
        """
        UPDATE consultas
           SET status    = ?,
               resumo    = ?,
               conclusao = ?
         WHERE id = ?
        """,
        (STATUS_CONCLUIDA, resumo, conclusao, consulta_id),
    )
    db.commit()

    flash("Consulta marcada como concluída e registrada no histórico.", "ok")
    adicionar_notificacao(
        consulta["paciente_cpf"],
        "Sua consulta foi concluída! Veja o resumo no histórico.",
    )
    return redirect(url_for("agendamedico"))


# ---------------------------------------------------------------------
# Agenda paciente
# ---------------------------------------------------------------------

@app.route("/agendapaciente")
def agendapaciente():
    db = get_db()

    paciente_cpf = normalizar_cpf(
        session.get("cpf") or request.args.get("paciente_cpf") or ""
    )
    if not paciente_cpf:
        return (
            "CPF do paciente não encontrado (faça login ou use ?paciente_cpf=XXXXXXXXXXX)",
            400,
        )

    cur = db.execute(
        """
        SELECT *
          FROM consultas
         WHERE paciente_cpf = ?
         ORDER BY data, hora
        """,
        (paciente_cpf,),
    )
    consultas_paciente = [dict(r) for r in cur.fetchall()]

    mapa_nomes = {
        r["CPF"]: r["nome"]
        for r in db.execute("SELECT CPF, nome FROM usuarios").fetchall()
    }

    for c in consultas_paciente:
        c["medico_nome"] = mapa_nomes.get(
            c.get("medico_cpf", ""), c.get("medico_cpf", "—")
        )

    medicos = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM usuarios WHERE tipo = ?", (TIPO_MEDICO,)
        ).fetchall()
    ]
    cargos = sorted({m.get("cargo") for m in medicos if m.get("cargo")})

    return render_template(
        "agendapaciente.html",
        consultas=consultas_paciente,
        medicos=medicos,
        cargos=cargos,
        paciente_cpf=paciente_cpf,
    )


@app.route("/horarios_disponiveis")
def horarios_disponiveis():
    db = get_db()

    data = request.args.get("data") or ""
    medico_cpf = normalizar_cpf(request.args.get("medico_cpf") or "")
    cargo = (request.args.get("cargo") or "").strip()

    if not data:
        return jsonify({"horarios": []})

    # se veio cargo mas não veio médico, tenta achar um médico daquele cargo
    if not medico_cpf and cargo:
        cur = db.execute(
            "SELECT CPF FROM usuarios WHERE tipo = ? AND cargo = ?",
            (TIPO_MEDICO, cargo),
        )
        row = cur.fetchone()
        if row:
            medico_cpf = row["CPF"]

    if not medico_cpf:
        return jsonify({"horarios": []})

    cur = db.execute(
        """
        SELECT hora
          FROM consultas
         WHERE medico_cpf = ?
           AND data       = ?
           AND status    != ?
        """,
        (medico_cpf, data, STATUS_CANCELADA),
    )
    ocupados = {r["hora"] for r in cur.fetchall()}

    base_horarios = []
    for h in range(8, 18):  # 08h até 17h
        for m in (0, 30):
            base_horarios.append(f"{h:02d}:{m:02d}")

    livres = [h for h in base_horarios if h not in ocupados]
    return jsonify({"horarios": livres})


@app.route("/solicitar_consulta", methods=["POST"])
def solicitar_consulta():
    db = get_db()

    paciente_cpf = normalizar_cpf(
        session.get("cpf") or request.form.get("paciente_cpf") or ""
    )
    cargo = (request.form.get("cargo") or "").strip()
    medico_cpf = normalizar_cpf(request.form.get("medico_cpf") or "")
    data = request.form.get("data") or ""
    hora = request.form.get("hora") or ""
    tipo = request.form.get("tipo") or "Consulta"
    obs = request.form.get("observacoes") or ""

    if not paciente_cpf or not data or not hora or not cargo:
        flash(
            "Preencha Data, Hora e selecione um Cargo/Especialidade. Médico é opcional.",
            "erro",
        )
        return redirect(url_for("agendapaciente", paciente_cpf=paciente_cpf))

    cur = db.execute(
        "SELECT 1 FROM usuarios WHERE CPF = ? AND tipo = ?",
        (paciente_cpf, TIPO_PACIENTE),
    )
    if cur.fetchone() is None:
        flash("Paciente inválido.", "erro")
        return redirect(url_for("agendapaciente", paciente_cpf=paciente_cpf))

    medicos_do_cargo = db.execute(
        "SELECT * FROM usuarios WHERE tipo = ? AND cargo = ?",
        (TIPO_MEDICO, cargo),
    ).fetchall()

    if not medicos_do_cargo:
        flash("Não há médicos cadastrados para o cargo selecionado.", "erro")
        return redirect(url_for("agendapaciente", paciente_cpf=paciente_cpf))

    medico_escolhido = None

    if medico_cpf:
        medico_escolhido = next(
            (m for m in medicos_do_cargo if m["CPF"] == medico_cpf), None
        )
        if not medico_escolhido:
            flash("Médico inválido para o cargo selecionado.", "erro")
            return redirect(url_for("agendapaciente", paciente_cpf=paciente_cpf))
    else:
        medico_escolhido = medicos_do_cargo[0]
        medico_cpf = medico_escolhido["CPF"]

    db.execute(
        """
        INSERT INTO consultas
            (paciente_cpf, medico_cpf, data, hora, tipo, status, observacoes, cargo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (paciente_cpf, medico_cpf, data, hora, tipo, STATUS_SOLICITADA, obs, cargo),
    )
    db.commit()

    flash(
        f'Solicitação enviada! Médico atribuído: {medico_escolhido["nome"]}.',
        "ok",
    )
    adicionar_notificacao(
        paciente_cpf,
        "Sua consulta foi solicitada e aguarda aprovação.",
    )
    return redirect(url_for("agendapaciente", paciente_cpf=paciente_cpf))


# ---------------------------------------------------------------------
# Notificações (JSON para o front)
# ---------------------------------------------------------------------

@app.route("/notificacoes_count")
def notificacoes_count():
    cpf = session.get("cpf")
    if not cpf:
        return {"count": 0}

    db = get_db()
    cur = db.execute(
        """
        SELECT COUNT(*) AS qtd
          FROM notificacoes
         WHERE cpf = ?
           AND lida = 0
        """,
        (cpf,),
    )
    row = cur.fetchone()
    return {"count": row["qtd"] if row else 0}


@app.route("/notificacoes_lista")
def notificacoes_lista():
    cpf = session.get("cpf")
    if not cpf:
        return jsonify([])

    db = get_db()
    cur = db.execute(
        """
        SELECT texto, lida, data
          FROM notificacoes
         WHERE cpf = ?
         ORDER BY data DESC
        """,
        (cpf,),
    )
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


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

if __name__ == "__main__":
    with app.app_context():
        init_db()
        inicializar_usuarios_fixos()
    app.run(debug=True)
