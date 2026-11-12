"""Acesso ao SQLite do módulo fiscal. Valores Decimal gravados como TEXT."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from apps.match.banco import _agora
from src.modules.fiscal_docs.modelos import DocumentoFiscal
from src.modules.fiscal_docs.webposto_notas import EntradaWebposto, NotaListada


def so_digitos(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


def _t(v) -> str | None:
    return None if v is None else str(v)


# ---------------------------------------------------------------- empresas e escritórios

def salvar_empresa(con, cnpj, razao_social, apelido, municipio, uf, posto_id,
                   empresa_id: int | None = None) -> int:
    dados = (so_digitos(cnpj), razao_social, apelido, municipio, uf, posto_id)
    if empresa_id is None:
        cur = con.execute("INSERT INTO empresa(cnpj, razao_social, apelido, municipio, uf, posto_id,"
                          " criado_em) VALUES (?,?,?,?,?,?,?)", (*dados, _agora()))
        con.commit()
        return cur.lastrowid
    con.execute("UPDATE empresa SET cnpj=?, razao_social=?, apelido=?, municipio=?, uf=?, posto_id=?"
                " WHERE id=?", (*dados, empresa_id))
    con.commit()
    return empresa_id


def listar_empresas(con, ids: list[int] | None = None) -> list:
    sql = "SELECT * FROM empresa"
    if ids is not None:
        if not ids:
            return []
        sql += f" WHERE id IN ({','.join('?' * len(ids))})"
    return con.execute(sql + " ORDER BY razao_social", ids or ()).fetchall()


def obter_empresa(con, empresa_id: int):
    return con.execute("SELECT * FROM empresa WHERE id=?", (empresa_id,)).fetchone()


def salvar_escritorio(con, nome, emails: list[str], dia_envio: int, modo: str, pdf: str,
                      empresas: list[int], escritorio_id: int | None = None) -> int:
    dados = (nome, json.dumps(emails), dia_envio, modo, pdf)
    if escritorio_id is None:
        escritorio_id = con.execute("INSERT INTO escritorio(nome, emails_json, dia_envio, modo, pdf, criado_em)"
                                    " VALUES (?,?,?,?,?,?)", (*dados, _agora())).lastrowid
    else:
        con.execute("UPDATE escritorio SET nome=?, emails_json=?, dia_envio=?, modo=?, pdf=? WHERE id=?",
                    (*dados, escritorio_id))
        con.execute("DELETE FROM escritorio_empresa WHERE escritorio_id=?", (escritorio_id,))
    con.executemany("INSERT INTO escritorio_empresa VALUES (?,?)", [(escritorio_id, e) for e in empresas])
    con.commit()
    return escritorio_id


def listar_escritorios(con, so_ativos: bool = False) -> list:
    sql = "SELECT * FROM escritorio" + (" WHERE ativo=1" if so_ativos else "")
    return con.execute(sql + " ORDER BY nome").fetchall()


def empresas_do_escritorio(con, escritorio_id: int) -> list:
    return con.execute("SELECT e.* FROM empresa e JOIN escritorio_empresa x ON x.empresa_id=e.id"
                       " WHERE x.escritorio_id=? ORDER BY e.razao_social", (escritorio_id,)).fetchall()


# ---------------------------------------------------------------- documentos

def _frete(entrada: EntradaWebposto | None) -> tuple[str | None, str | None]:
    if entrada is None:
        return None, None
    return entrada.cte_numero, json.dumps(entrada.model_dump(mode="json"), ensure_ascii=False)


def _gravar_detalhes(con, doc_id: int, doc: DocumentoFiscal) -> None:
    con.execute("DELETE FROM documento_item WHERE documento_id=?", (doc_id,))
    con.executemany(
        "INSERT INTO documento_item VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [(doc_id, i.n_item, i.codigo, i.descricao, i.ncm, i.cfop, i.cprod_anp, _t(i.quantidade),
          i.unidade, _t(i.valor_unitario), _t(i.valor_total), _t(i.icms_mono)) for i in doc.itens])
    con.execute("DELETE FROM documento_transporte WHERE documento_id=?", (doc_id,))
    t = doc.transporte
    if t is not None:
        con.execute("INSERT INTO documento_transporte VALUES (?,?,?,?,?,?,?,?,?)",
                    (doc_id, t.mod_frete, t.mod_frete_texto, t.transportadora_cnpj,
                     t.transportadora_nome, t.placa, t.uf_placa, _t(t.volumes), _t(t.peso_bruto)))


def gravar_documento(con, empresa_id: int, doc: DocumentoFiscal, xml_path: Path, xml_hash: str,
                     origem: str, entrada: EntradaWebposto | None = None) -> bool:
    """True se inseriu ou completou um `so_resumo`; False se o documento já existia completo."""
    atual = con.execute("SELECT id, situacao, cte_numero FROM documento WHERE chave=?", (doc.chave,)).fetchone()
    cte, frete = _frete(entrada)
    campos = (empresa_id, doc.tipo, doc.numero, doc.serie, doc.emissao_em.isoformat(), doc.competencia,
              doc.emitente_cnpj, doc.emitente_nome, doc.destinatario_cnpj, _t(doc.valor_total),
              doc.impostos.model_dump_json(), doc.situacao, origem, int(doc.combustivel),
              doc.descricao_servico, str(xml_path), xml_hash)
    if atual is None:
        cur = con.execute(
            "INSERT INTO documento(empresa_id, tipo, numero, serie, emissao_em, competencia, emitente_cnpj,"
            " emitente_nome, destinatario_cnpj, valor_total, impostos_json, situacao, origem, combustivel,"
            " descricao_servico, xml_path, xml_hash, chave, capturado_em, cte_numero, frete_json)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (*campos, doc.chave, _agora(), cte, frete))
        _gravar_detalhes(con, cur.lastrowid, doc)
        con.commit()
        return True
    if atual["situacao"] == "so_resumo" and doc.situacao != "so_resumo":
        con.execute(
            "UPDATE documento SET empresa_id=?, tipo=?, numero=?, serie=?, emissao_em=?, competencia=?,"
            " emitente_cnpj=?, emitente_nome=?, destinatario_cnpj=?, valor_total=?, impostos_json=?,"
            " situacao=?, origem=?, combustivel=?, descricao_servico=?, xml_path=?, xml_hash=?,"
            " capturado_em=?, cte_numero=COALESCE(?, cte_numero), frete_json=COALESCE(?, frete_json)"
            " WHERE id=?", (*campos, _agora(), cte, frete, atual["id"]))
        _gravar_detalhes(con, atual["id"], doc)
        con.commit()
        return True
    if entrada is not None:
        atualizar_frete(con, doc.chave, entrada)
    return False


def atualizar_frete(con, chave: str, entrada: EntradaWebposto) -> None:
    """Grava frete/CT-e informados pelo webPosto se ainda não estavam no documento."""
    cte, frete = _frete(entrada)
    con.execute("UPDATE documento SET cte_numero=COALESCE(cte_numero, ?), frete_json=COALESCE(frete_json, ?)"
                " WHERE chave=?", (cte, frete, chave))
    con.commit()


def registrar_so_resumo(con, empresa_id: int, nota: NotaListada) -> bool:
    if con.execute("SELECT 1 FROM documento WHERE chave=?", (nota.chave,)).fetchone():
        return False
    con.execute(
        "INSERT INTO documento(empresa_id, tipo, chave, numero, emissao_em, competencia, emitente_cnpj,"
        " emitente_nome, valor_total, situacao, origem, capturado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (empresa_id, "nfe", nota.chave, nota.chave[25:34].lstrip("0") if len(nota.chave) == 44 else "",
         nota.emissao.isoformat(), nota.emissao.strftime("%Y-%m"), nota.emitente_cnpj,
         nota.emitente_nome, _t(nota.valor), "so_resumo", "webposto", _agora()))
    con.commit()
    return True


@dataclass
class FiltroDocs:
    empresas: list[int] = field(default_factory=list)
    inicio: date | None = None
    fim: date | None = None
    fornecedor: str | None = None
    tipo: str | None = None
    situacao: str | None = None
    combustivel: bool | None = None
    valor_min: Decimal | None = None
    valor_max: Decimal | None = None
    competencia: str | None = None
    texto: str | None = None  # busca rápida: número, prestador (nome/CNPJ) ou descrição do serviço


def _norm(v) -> str:
    """Minúsculas sem acento ('SERVIÇOS' -> 'servicos'), para a busca rápida."""
    t = unicodedata.normalize("NFKD", str(v or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _preparar(con) -> None:
    con.create_function("norm", 1, _norm, deterministic=True)


def _onde(f: FiltroDocs, sem: tuple[str, ...] = ()) -> tuple[list[str], list]:
    """Condições SQL do filtro. `sem` ignora campos (para contar as opções de um filtro)."""
    onde = [f"d.empresa_id IN ({','.join('?' * len(f.empresas))})"]
    args: list = list(f.empresas)
    if f.texto and f.texto.strip() and "texto" not in sem:
        t = _norm(f.texto.strip())
        dig = so_digitos(t)
        partes = ["norm(d.emitente_nome) LIKE ?", "norm(d.descricao_servico) LIKE ?", "ltrim(d.numero,'0') = ?"]
        args += [f"%{t}%", f"%{t}%", t.lstrip("0") or t]
        if len(dig) >= 4:
            partes.append("d.emitente_cnpj LIKE ?"); args.append(f"%{dig}%")
        onde.append("(" + " OR ".join(partes) + ")")
    if f.inicio and "periodo" not in sem:
        onde.append("substr(d.emissao_em,1,10) >= ?"); args.append(f.inicio.isoformat())
    if f.fim and "periodo" not in sem:
        onde.append("substr(d.emissao_em,1,10) <= ?"); args.append(f.fim.isoformat())
    if f.competencia:
        onde.append("d.competencia = ?"); args.append(f.competencia)
    if f.fornecedor and f.fornecedor.strip():
        dig = so_digitos(f.fornecedor)
        if dig and len(dig) >= 8:
            onde.append("d.emitente_cnpj LIKE ?"); args.append(f"{dig}%")
        else:
            onde.append("lower(d.emitente_nome) LIKE ?"); args.append(f"%{f.fornecedor.strip().lower()}%")
    if f.tipo and "tipo" not in sem:
        onde.append("d.tipo = ?"); args.append(f.tipo)
    if f.situacao:
        onde.append("d.situacao = ?"); args.append(f.situacao)
    if f.combustivel is not None:
        onde.append("d.combustivel = ?"); args.append(int(f.combustivel))
    if f.valor_min is not None:
        onde.append("CAST(d.valor_total AS REAL) >= ?"); args.append(float(f.valor_min))
    if f.valor_max is not None:
        onde.append("CAST(d.valor_total AS REAL) <= ?"); args.append(float(f.valor_max))
    return onde, args


def buscar_documentos(con, f: FiltroDocs) -> list:
    if not f.empresas:
        return []
    _preparar(con)
    onde, args = _onde(f)
    sql = ("SELECT d.*, e.apelido AS empresa_apelido, e.razao_social AS empresa_nome FROM documento d"
           " JOIN empresa e ON e.id = d.empresa_id WHERE " + " AND ".join(onde) +
           " ORDER BY d.emissao_em, d.numero")
    return con.execute(sql, args).fetchall()


def contar_por(con, f: FiltroDocs, campo: str) -> dict[str, int]:
    """Quantas notas cada opção de um filtro teria, mantendo os outros filtros.
    campo: 'empresa' | 'tipo' | 'mes'. Para 'empresa', passe em `f.empresas` todas as visíveis."""
    if not f.empresas:
        return {}
    expr, sem = {"empresa": ("d.empresa_id", ()), "tipo": ("d.tipo", ("tipo",)),
                 "mes": ("substr(d.emissao_em,1,7)", ("periodo",))}[campo]
    _preparar(con)
    onde, args = _onde(f, sem)
    sql = f"SELECT {expr}, COUNT(*) FROM documento d WHERE {' AND '.join(onde)} GROUP BY 1"
    return {str(k): n for k, n in con.execute(sql, args).fetchall()}


def resumo_prestadores(docs) -> list[dict]:
    """Prestadores das notas listadas, do maior total para o menor (canceladas não somam)."""
    grupos: dict[str, dict] = {}
    for d in docs:
        chave = d["emitente_cnpj"] or d["emitente_nome"] or "?"
        g = grupos.setdefault(chave, {"cnpj": d["emitente_cnpj"] or "", "nome": d["emitente_nome"] or "—",
                                      "qtd": 0, "total": Decimal(0)})
        g["qtd"] += 1
        if d["situacao"] != "cancelada":
            g["total"] += Decimal(d["valor_total"])
    return sorted(grupos.values(), key=lambda g: (-g["total"], g["nome"]))


def documentos_da_competencia(con, empresa_id: int, competencia: str) -> list:
    return buscar_documentos(con, FiltroDocs(empresas=[empresa_id], competencia=competencia))


def itens_do_documento(con, documento_id: int) -> list:
    return con.execute("SELECT * FROM documento_item WHERE documento_id=? ORDER BY n_item",
                       (documento_id,)).fetchall()


def transporte_do_documento(con, documento_id: int):
    return con.execute("SELECT * FROM documento_transporte WHERE documento_id=?", (documento_id,)).fetchone()


# ---------------------------------------------------------------- capturas e pacotes

def registrar_captura(con, empresa_id: int, fonte: str, iniciada_em: str, situacao: str,
                      qtd_novas: int, qtd_pendentes: int, erro_texto: str | None) -> int:
    cur = con.execute("INSERT INTO captura(empresa_id, fonte, iniciada_em, terminada_em, situacao,"
                      " qtd_novas, qtd_pendentes, erro_texto) VALUES (?,?,?,?,?,?,?,?)",
                      (empresa_id, fonte, iniciada_em, _agora(), situacao, qtd_novas, qtd_pendentes,
                       erro_texto))
    con.commit()
    return cur.lastrowid


def capturas_recentes(con, empresa_id: int, desde: datetime) -> list:
    return con.execute("SELECT * FROM captura WHERE empresa_id=? AND iniciada_em >= ? ORDER BY id DESC",
                       (empresa_id, desde.isoformat())).fetchall()


def ultima_captura(con, empresa_id: int, fonte: str | None = None):
    filtro, args = (" AND fonte=?", (empresa_id, fonte)) if fonte else ("", (empresa_id,))
    return con.execute(f"SELECT * FROM captura WHERE empresa_id=?{filtro} ORDER BY id DESC LIMIT 1", args).fetchone()


def ultima_data_lida(con, empresa_id: int) -> date | None:
    r = con.execute("SELECT ultima_data_lida FROM leitura_webposto WHERE empresa_id=?", (empresa_id,)).fetchone()
    return date.fromisoformat(r[0]) if r and r[0] else None


def salvar_ultima_data_lida(con, empresa_id: int, dia: date) -> None:
    con.execute("INSERT INTO leitura_webposto VALUES (?,?) ON CONFLICT(empresa_id)"
                " DO UPDATE SET ultima_data_lida=excluded.ultima_data_lida", (empresa_id, dia.isoformat()))
    con.commit()


_CAMPOS_PACOTE = {"situacao", "motivo_retencao", "enviado_em", "aprovado_por", "arquivos_json",
                  "partes_enviadas", "gerado_em"}


def salvar_pacote(con, empresa_id: int, competencia: str, situacao: str, arquivos: list[str],
                  motivo: str | None = None, complementar: bool = False) -> int:
    cur = con.execute("INSERT INTO pacote(empresa_id, competencia, complementar, gerado_em, arquivos_json,"
                      " situacao, motivo_retencao) VALUES (?,?,?,?,?,?,?)",
                      (empresa_id, competencia, int(complementar), _agora(), json.dumps(arquivos),
                       situacao, motivo))
    con.commit()
    return cur.lastrowid


def atualizar_pacote(con, pacote_id: int, **campos) -> None:
    if not campos or set(campos) - _CAMPOS_PACOTE:
        raise ValueError(f"campos inválidos: {sorted(set(campos) - _CAMPOS_PACOTE)}")
    sets = ", ".join(f"{k}=?" for k in campos)
    con.execute(f"UPDATE pacote SET {sets} WHERE id=?", (*campos.values(), pacote_id))
    con.commit()


def obter_pacote(con, pacote_id: int):
    return con.execute("SELECT * FROM pacote WHERE id=?", (pacote_id,)).fetchone()


def pacotes(con, empresa_ids: list[int], competencia: str | None = None) -> list:
    if not empresa_ids:
        return []
    sql = (f"SELECT p.*, e.apelido, e.razao_social, e.cnpj FROM pacote p JOIN empresa e ON e.id=p.empresa_id"
           f" WHERE p.empresa_id IN ({','.join('?' * len(empresa_ids))})")
    args: list = list(empresa_ids)
    if competencia:
        sql += " AND p.competencia=?"; args.append(competencia)
    return con.execute(sql + " ORDER BY p.competencia DESC, p.id DESC", args).fetchall()


def vincular_documentos(con, pacote_id: int, documento_ids: list[int]) -> None:
    con.execute("DELETE FROM pacote_documento WHERE pacote_id=?", (pacote_id,))
    con.executemany("INSERT INTO pacote_documento VALUES (?,?)", [(pacote_id, d) for d in documento_ids])
    con.commit()


def documentos_ja_enviados(con, empresa_id: int, competencia: str, exceto: int | None = None) -> set[int]:
    """Notas que já estão em algum pacote enviado, em envio ou entregue para baixar (menos `exceto`)."""
    return {r[0] for r in con.execute(
        "SELECT pd.documento_id FROM pacote_documento pd JOIN pacote p ON p.id = pd.pacote_id"
        " WHERE p.empresa_id=? AND p.competencia=? AND p.id != ?"
        " AND p.situacao IN ('enviado','enviando','erro','gerado')",
        (empresa_id, competencia, exceto or -1))}


def nsu_de(con, empresa_id: int, fonte: str = "adn") -> dict:
    r = con.execute("SELECT ultimo_nsu, proxima_consulta_em FROM fila_fiscal WHERE empresa_id=? AND fonte=?",
                    (empresa_id, fonte)).fetchone()
    return dict(r) if r else {"ultimo_nsu": 0, "proxima_consulta_em": None}


def salvar_nsu(con, empresa_id: int, nsu: int, proxima: datetime | None, fonte: str = "adn") -> None:
    con.execute("INSERT INTO fila_fiscal(empresa_id, fonte, ultimo_nsu, proxima_consulta_em) VALUES (?,?,?,?)"
                " ON CONFLICT(empresa_id, fonte) DO UPDATE SET ultimo_nsu=excluded.ultimo_nsu,"
                " proxima_consulta_em=excluded.proxima_consulta_em",
                (empresa_id, fonte, nsu, proxima.isoformat() if proxima else None))
    con.commit()


def marcar_cancelada(con, chave: str) -> None:
    con.execute("UPDATE documento SET situacao='cancelada' WHERE chave=?", (chave,))
    con.commit()


def empresa_por_cnpj(con, cnpj: str):
    return con.execute("SELECT * FROM empresa WHERE cnpj=?", (so_digitos(cnpj),)).fetchone()
