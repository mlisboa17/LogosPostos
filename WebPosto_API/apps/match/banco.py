"""Banco SQLite local do Logos Match (stdlib). Valores Decimal como TEXT."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from apps.match import VERSAO, caminhos

_SCHEMA_V1 = """
CREATE TABLE instalacao (
    id_instalacao TEXT PRIMARY KEY, criada_em TEXT NOT NULL, versao_app TEXT NOT NULL);
CREATE TABLE posto (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, apelido TEXT, cnpj TEXT,
    empresa_codigo_webposto INTEGER, ativo INTEGER NOT NULL DEFAULT 1, criado_em TEXT NOT NULL);
CREATE TABLE fonte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    posto_id INTEGER NOT NULL REFERENCES posto(id),
    tipo TEXT NOT NULL CHECK (tipo IN ('premmia','pagbank_edi','webposto')),
    ativo INTEGER NOT NULL DEFAULT 1, config_json TEXT NOT NULL DEFAULT '{}',
    ref_credencial TEXT, ultimo_teste_em TEXT, ultimo_teste_ok INTEGER);
CREATE TABLE coleta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte_id INTEGER NOT NULL REFERENCES fonte(id), dia TEXT NOT NULL,
    iniciada_em TEXT, terminada_em TEXT,
    situacao TEXT NOT NULL CHECK (situacao IN ('ok','sem_movimento','erro','verificacao_humana')),
    qtd INTEGER NOT NULL DEFAULT 0, total TEXT NOT NULL DEFAULT '0',
    hash_arquivo TEXT, erro_texto TEXT,
    UNIQUE (fonte_id, dia));
CREATE TABLE transacao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coleta_id INTEGER NOT NULL REFERENCES coleta(id),
    posto_id INTEGER NOT NULL REFERENCES posto(id),
    fonte TEXT NOT NULL, identificador TEXT NOT NULL, nsu TEXT, autorizacao TEXT,
    valor TEXT NOT NULL, momento TEXT NOT NULL, bandeira TEXT, forma TEXT,
    terminal TEXT, situacao TEXT,
    UNIQUE (posto_id, fonte, identificador));
CREATE TABLE caixa_webposto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    posto_id INTEGER NOT NULL REFERENCES posto(id), dia TEXT NOT NULL,
    caixa_codigo INTEGER, setor TEXT, centro_custo TEXT,
    frentista_codigo INTEGER, frentista_nome TEXT, totais_json TEXT);
CREATE TABLE divergencia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    posto_id INTEGER NOT NULL REFERENCES posto(id), dia TEXT NOT NULL,
    caixa_webposto_id INTEGER REFERENCES caixa_webposto(id),
    caixa_codigo INTEGER, responsavel TEXT,
    fonte TEXT NOT NULL, tipo TEXT NOT NULL, valor_esperado TEXT, valor_encontrado TEXT,
    nsu TEXT, explicacao_pt TEXT, correcao_pt TEXT,
    situacao TEXT NOT NULL DEFAULT 'aberta');
CREATE TABLE canal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL CHECK (tipo IN ('telegram','email','toast')),
    config_json TEXT NOT NULL DEFAULT '{}', ref_credencial TEXT, ativo INTEGER NOT NULL DEFAULT 1);
CREATE TABLE envio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canal_id INTEGER NOT NULL REFERENCES canal(id), dia TEXT NOT NULL,
    enviado_em TEXT, situacao TEXT, erro_texto TEXT);
CREATE TABLE usuario (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, login TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    perfil TEXT NOT NULL CHECK (perfil IN ('administrador','gerente','conferente')),
    ativo INTEGER NOT NULL DEFAULT 1, criado_em TEXT NOT NULL, ultimo_acesso_em TEXT,
    tentativas_falhas INTEGER NOT NULL DEFAULT 0, bloqueado_ate TEXT);
CREATE TABLE usuario_posto (
    usuario_id INTEGER NOT NULL REFERENCES usuario(id),
    posto_id INTEGER NOT NULL REFERENCES posto(id),
    PRIMARY KEY (usuario_id, posto_id));
CREATE TABLE log_acesso (
    id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER REFERENCES usuario(id),
    momento TEXT NOT NULL, acao TEXT NOT NULL, detalhe TEXT);
"""

_SCHEMA_V2 = """
ALTER TABLE instalacao ADD COLUMN hora_coleta TEXT DEFAULT '06:00';
ALTER TABLE instalacao ADD COLUMN hora_repescagem TEXT DEFAULT '10:00';
"""

_SCHEMA_V3 = """
CREATE TABLE execucao (
    id INTEGER PRIMARY KEY AUTOINCREMENT, iniciada_em TEXT NOT NULL, terminada_em TEXT,
    origem TEXT NOT NULL CHECK (origem IN ('agendada','repescagem','recuperacao','painel','bandeja')),
    usuario_id INTEGER REFERENCES usuario(id), dia TEXT NOT NULL,
    situacao TEXT NOT NULL CHECK (situacao IN ('em_andamento','concluida','falhou')));
CREATE TABLE execucao_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execucao_id INTEGER NOT NULL REFERENCES execucao(id),
    posto_id INTEGER NOT NULL, fonte TEXT NOT NULL,
    situacao TEXT NOT NULL CHECK (situacao IN
        ('aguardando','coletando','ok','sem_movimento','sem_comparacao','erro','verificacao_humana')),
    mensagem TEXT, iniciada_em TEXT, terminada_em TEXT,
    UNIQUE (execucao_id, posto_id, fonte));
ALTER TABLE envio ADD COLUMN execucao_id INTEGER;
"""

_SCHEMA_V4 = """
ALTER TABLE instalacao ADD COLUMN pasta_rede TEXT;
"""

_MIGRACOES = [(1, _SCHEMA_V1), (2, _SCHEMA_V2), (3, _SCHEMA_V3), (4, _SCHEMA_V4)]


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrar(con: sqlite3.Connection) -> None:
    con.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
    atual = con.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0]
    for versao, sql in _MIGRACOES:
        if versao > atual:
            con.executescript(sql)
            con.execute("INSERT INTO schema_version(version) VALUES (?)", (versao,))
    id_instalacao(con)  # garante a linha de configuração (horários da rotina)
    con.commit()


def conectar(caminho: Path | None = None) -> sqlite3.Connection:
    caminho = caminho or (caminhos.raiz() / "logosmatch.db")
    con = sqlite3.connect(str(caminho), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    _migrar(con)
    return con


def _txt(v) -> str | None:
    return None if v is None else str(v)


def inserir_posto(con, nome, apelido, cnpj, empresa_codigo_webposto, *, ativo: bool = True) -> int:
    cur = con.execute(
        "INSERT INTO posto(nome, apelido, cnpj, empresa_codigo_webposto, criado_em, ativo)"
        " VALUES (?,?,?,?,?,?)", (nome, apelido, cnpj, empresa_codigo_webposto, _agora(), int(ativo)))
    con.commit()
    return cur.lastrowid


def listar_postos(con, so_ativos: bool = True) -> list[sqlite3.Row]:
    sql = "SELECT * FROM posto" + (" WHERE ativo=1" if so_ativos else "") + " ORDER BY nome"
    return con.execute(sql).fetchall()


def salvar_fonte(con, posto_id: int, tipo: str, ativo: bool, config: dict) -> int:
    cfg = json.dumps(config, ensure_ascii=False)
    row = con.execute("SELECT id FROM fonte WHERE posto_id=? AND tipo=?", (posto_id, tipo)).fetchone()
    if row:
        con.execute("UPDATE fonte SET ativo=?, config_json=? WHERE id=?", (int(ativo), cfg, row["id"]))
        fid = row["id"]
    else:
        fid = con.execute(
            "INSERT INTO fonte(posto_id, tipo, ativo, config_json) VALUES (?,?,?,?)",
            (posto_id, tipo, int(ativo), cfg)).lastrowid
    con.commit()
    return fid


def fontes_do_posto(con, posto_id: int) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM fonte WHERE posto_id=? ORDER BY id", (posto_id,)).fetchall()


def registrar_coleta(con, fonte_id, dia, situacao, qtd, total, erro_texto) -> int:
    agora = _agora()
    con.execute(
        "INSERT INTO coleta(fonte_id, dia, iniciada_em, terminada_em, situacao, qtd, total, erro_texto)"
        " VALUES (?,?,?,?,?,?,?,?)"
        " ON CONFLICT(fonte_id, dia) DO UPDATE SET terminada_em=excluded.terminada_em,"
        " situacao=excluded.situacao, qtd=excluded.qtd, total=excluded.total,"
        " erro_texto=excluded.erro_texto",
        (fonte_id, str(dia), agora, agora, situacao, qtd, str(total), erro_texto))
    con.commit()
    return con.execute("SELECT id FROM coleta WHERE fonte_id=? AND dia=?",
                       (fonte_id, str(dia))).fetchone()["id"]


def gravar_transacoes(con, coleta_id, posto_id, fonte, transacoes) -> int:
    novas = 0
    for t in transacoes:
        cur = con.execute(
            "INSERT OR IGNORE INTO transacao(coleta_id, posto_id, fonte, identificador, nsu,"
            " autorizacao, valor, momento, bandeira, forma, terminal, situacao)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (coleta_id, posto_id, fonte, t.identificador, t.nsu, t.autorizacao, str(t.valor),
             t.momento.isoformat(), t.bandeira, t.bandeira, t.terminal, t.situacao))
        novas += cur.rowcount
    con.commit()
    return novas


def gravar_divergencias(con, posto_id, dia, fonte, itens: list[dict]) -> None:
    con.execute("DELETE FROM divergencia WHERE posto_id=? AND dia=? AND fonte=?",
                (posto_id, str(dia), fonte))
    for i in itens:
        con.execute(
            "INSERT INTO divergencia(posto_id, dia, caixa_codigo, responsavel, fonte, tipo,"
            " valor_esperado, valor_encontrado, nsu, explicacao_pt, correcao_pt)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (posto_id, str(dia), i.get("caixa_codigo"), i.get("responsavel"), fonte, i["tipo"],
             _txt(i.get("valor_esperado")), _txt(i.get("valor_encontrado")), i.get("nsu"),
             i.get("explicacao_pt"), i.get("correcao_pt")))
    con.commit()


def id_instalacao(con) -> str:
    row = con.execute("SELECT id_instalacao FROM instalacao LIMIT 1").fetchone()
    if row:
        return row["id_instalacao"]
    novo = str(uuid.uuid4())
    con.execute("INSERT INTO instalacao(id_instalacao, criada_em, versao_app) VALUES (?,?,?)",
                (novo, _agora(), VERSAO))
    con.commit()
    return novo


def inserir_canal(con, tipo: str, config: dict, ativo: bool = True) -> int:
    cur = con.execute("INSERT INTO canal(tipo, config_json, ativo) VALUES (?,?,?)",
                      (tipo, json.dumps(config, ensure_ascii=False), int(ativo)))
    con.commit()
    return cur.lastrowid


def registrar_envio(con, canal_id: int, dia, situacao: str, erro_texto: str | None,
                    execucao_id: int | None = None) -> int:
    cur = con.execute(
        "INSERT INTO envio(canal_id, dia, enviado_em, situacao, erro_texto, execucao_id)"
        " VALUES (?,?,?,?,?,?)", (canal_id, str(dia), _agora(), situacao, erro_texto, execucao_id))
    con.commit()
    return cur.lastrowid


def obter_posto(con, posto_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM posto WHERE id=?", (posto_id,)).fetchone()


def atualizar_posto(con, posto_id: int, nome, apelido, cnpj, empresa_codigo_webposto) -> None:
    con.execute("UPDATE posto SET nome=?, apelido=?, cnpj=?, empresa_codigo_webposto=? WHERE id=?",
                (nome, apelido, cnpj, empresa_codigo_webposto, posto_id))
    con.commit()


def definir_posto_ativo(con, posto_id: int, ativo: bool) -> None:
    con.execute("UPDATE posto SET ativo=? WHERE id=?", (int(ativo), posto_id))
    con.commit()


def marcar_teste_fonte(con, fonte_id: int, ok: bool) -> None:
    con.execute("UPDATE fonte SET ultimo_teste_em=?, ultimo_teste_ok=? WHERE id=?",
                (_agora(), int(ok), fonte_id))
    con.commit()


def ultima_coleta(con, fonte_id: int) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM coleta WHERE fonte_id=? ORDER BY dia DESC LIMIT 1",
                       (fonte_id,)).fetchone()


def divergencias_do_dia(con, posto_id: int, dia) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM divergencia WHERE posto_id=? AND dia=? AND situacao='aberta'"
                       " ORDER BY fonte, id", (posto_id, str(dia))).fetchall()


def ultimas_coletas(con, postos: list[int], limite: int = 30) -> list[sqlite3.Row]:
    if not postos:
        return []
    marcas = ",".join("?" * len(postos))
    return con.execute(
        "SELECT c.*, f.tipo, f.posto_id, p.nome AS posto_nome, p.apelido AS posto_apelido FROM coleta c"
        " JOIN fonte f ON f.id = c.fonte_id JOIN posto p ON p.id = f.posto_id"
        f" WHERE f.posto_id IN ({marcas}) ORDER BY c.iniciada_em DESC, c.id DESC LIMIT ?",  # noqa: S608
        (*postos, limite)).fetchall()


def ultimos_envios(con, limite: int = 30) -> list[sqlite3.Row]:
    return con.execute("SELECT e.*, c.tipo FROM envio e JOIN canal c ON c.id = e.canal_id"
                       " ORDER BY e.enviado_em DESC, e.id DESC LIMIT ?", (limite,)).fetchall()


def listar_canais(con) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM canal ORDER BY id").fetchall()


def atualizar_canal(con, canal_id: int, config: dict, ativo: bool) -> None:
    con.execute("UPDATE canal SET config_json=?, ativo=? WHERE id=?",
                (json.dumps(config, ensure_ascii=False), int(ativo), canal_id))
    con.commit()


def salvar_horarios(con, hora_coleta: str, hora_repescagem: str) -> None:
    id_instalacao(con)
    con.execute("UPDATE instalacao SET hora_coleta=?, hora_repescagem=?", (hora_coleta, hora_repescagem))
    con.commit()


def pasta_rede(con) -> Path | None:
    id_instalacao(con)
    valor = con.execute("SELECT pasta_rede FROM instalacao LIMIT 1").fetchone()[0]
    return Path(valor) if valor else None


def salvar_pasta_rede(con, caminho: str | None) -> None:
    id_instalacao(con)
    con.execute("UPDATE instalacao SET pasta_rede=?", (caminho or None,))
    con.commit()


def ultima_coleta_em(con) -> str | None:
    """Maior `terminada_em` (ISO UTC) entre as coletas, ou None."""
    return con.execute("SELECT MAX(terminada_em) FROM coleta").fetchone()[0]


_FINAIS = ("ok", "sem_movimento", "sem_comparacao", "erro", "verificacao_humana")


def abrir_execucao(con, origem: str, usuario_id: int | None, dia) -> int:
    cur = con.execute(
        "INSERT INTO execucao(iniciada_em, origem, usuario_id, dia, situacao)"
        " VALUES (?,?,?,?,'em_andamento')", (_agora(), origem, usuario_id, str(dia)))
    con.commit()
    return cur.lastrowid


def item_execucao(con, execucao_id: int, posto_id: int, fonte: str, situacao: str,
                  mensagem: str | None = None) -> None:
    agora = _agora()
    inicio = agora if situacao == "coletando" else None
    fim = agora if situacao in _FINAIS else None
    con.execute(
        "INSERT INTO execucao_item(execucao_id, posto_id, fonte, situacao, mensagem,"
        " iniciada_em, terminada_em) VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(execucao_id, posto_id, fonte) DO UPDATE SET situacao=excluded.situacao,"
        " mensagem=excluded.mensagem, iniciada_em=COALESCE(excluded.iniciada_em, iniciada_em),"
        " terminada_em=excluded.terminada_em",
        (execucao_id, posto_id, fonte, situacao, mensagem, inicio, fim))
    con.commit()


def fechar_execucao(con, execucao_id: int, situacao: str) -> None:
    con.execute("UPDATE execucao SET situacao=?, terminada_em=? WHERE id=?",
                (situacao, _agora(), execucao_id))
    con.commit()


def execucao_atual(con) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM execucao WHERE situacao='em_andamento'"
                       " ORDER BY id DESC LIMIT 1").fetchone()


def itens_execucao(con, execucao_id: int) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM execucao_item WHERE execucao_id=? ORDER BY id",
                       (execucao_id,)).fetchall()


def ultimas_execucoes(con, limite: int = 30) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM execucao ORDER BY id DESC LIMIT ?", (limite,)).fetchall()


def envios_da_execucao(con, execucao_id: int) -> list[sqlite3.Row]:
    return con.execute("SELECT e.*, c.tipo FROM envio e JOIN canal c ON c.id = e.canal_id"
                       " WHERE e.execucao_id=? ORDER BY e.id", (execucao_id,)).fetchall()
