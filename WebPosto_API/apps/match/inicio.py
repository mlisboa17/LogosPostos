"""Tela de Início: resumo do dia e primeiros passos, só com o que o usuário pode ver."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from apps.match import acesso, banco
from apps.match.acesso import Acao, Perfil
from apps.match.fiscal import certificados, repositorio as repo
from src.modules.fiscal_docs.modelos import FUSO

_MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
          "outubro", "novembro", "dezembro")


@dataclass
class Cartao:
    rotulo: str
    valor: str
    detalhe: str
    estado: str = ""          # "", ok, alerta, critico
    estado_texto: str = ""
    link: str = ""
    link_texto: str = ""


@dataclass
class Passo:
    feito: bool
    titulo: str
    detalhe: str
    link: str = ""
    botao: str = ""


@dataclass
class Resumo:
    saudacao: str
    cartoes: list[Cartao] = field(default_factory=list)
    passos: list[Passo] = field(default_factory=list)

    @property
    def passos_pendentes(self) -> bool:
        return any(not p.feito for p in self.passos)


def _saudacao(nome: str, agora: datetime) -> str:
    hora = agora.hour
    periodo = "Bom dia" if hora < 12 else "Boa tarde" if hora < 18 else "Boa noite"
    return f"{periodo}, {nome.split()[0] if nome else ''}".rstrip(", ")


def _proximo_envio(dia_envio: int, hoje: date) -> date:
    este = hoje.replace(day=dia_envio)
    if este >= hoje:
        return este
    proximo = (hoje.replace(day=28) + timedelta(days=4)).replace(day=1)
    return proximo.replace(day=dia_envio)


def _cartoes_fiscais(con, empresas: list[int], hoje: date, agora: datetime) -> list[Cartao]:
    cartoes = []
    marcas = ",".join("?" * len(empresas)) or "NULL"
    mes_passado = hoje.replace(day=1) - timedelta(days=1)
    total = con.execute(f"SELECT COUNT(*) FROM documento WHERE empresa_id IN ({marcas}) AND competencia = ?",
                        (*empresas, mes_passado.strftime("%Y-%m"))).fetchone()[0]
    novas = con.execute(f"SELECT COUNT(*) FROM documento WHERE empresa_id IN ({marcas}) AND capturado_em >= ?",
                        (*empresas, (agora - timedelta(days=1)).isoformat())).fetchone()[0]
    cartoes.append(Cartao(f"Notas de {_MESES[mes_passado.month - 1]} (mês passado)", str(total),
                          f"{novas} nova(s) nas últimas 24 horas" if novas else "nenhuma nova nas últimas 24 horas",
                          link="/notas", link_texto="Ver notas"))
    escritorios = repo.listar_escritorios(con, so_ativos=True)
    if escritorios:
        proximo = min(_proximo_envio(o["dia_envio"], hoje) for o in escritorios)
        n_emp = len({e["id"] for o in escritorios for e in repo.empresas_do_escritorio(con, o["id"])
                     if e["id"] in empresas})
        problemas = sum(1 for p in repo.pacotes(con, empresas) if p["situacao"] in ("retido", "erro"))
        cartoes.append(Cartao("Próximo envio ao contador", proximo.strftime("%d/%m"),
                              f"Pacote do mês · {n_emp} empresa(s)",
                              "alerta" if problemas else "ok",
                              f"{problemas} pacote(s) precisam de atenção" if problemas else "Tudo certo",
                              link="/pacotes", link_texto="Ver pacotes"))
    infos = [(e, certificados.situacao(con, e["id"])) for e in repo.listar_empresas(con, empresas)]
    if infos:
        validos = [(e, c) for e, c in infos if c and c.dias_restantes >= 0]
        perto = min(validos, key=lambda x: x[1].dias_restantes, default=None)
        sem = len(infos) - len(validos)
        if sem:
            estado, texto = "critico", f"{sem} empresa(s) sem certificado válido"
        elif perto and perto[1].dias_restantes <= 30:
            estado, texto = "alerta", "Renovar em breve"
        else:
            estado, texto = "ok", "Em dia"
        detalhe = (f"{perto[0]['apelido'] or perto[0]['razao_social']} vence em {perto[1].dias_restantes} dias"
                   if perto else "Nenhum certificado enviado")
        cartoes.append(Cartao("Certificados", f"{len(validos)} de {len(infos)}", detalhe, estado, texto,
                              link="/comecar", link_texto="Ver certificados"))
    return cartoes


def _cartao_caixa(con, postos: list[int], ontem: date) -> Cartao | None:
    if not postos:
        return None
    total = sum(len(banco.divergencias_do_dia(con, pid, ontem)) for pid in postos)
    return Cartao(f"Conferência de caixa ({ontem:%d/%m})", str(total),
                  "divergência(s) entre os postos" if total else "nenhuma divergência",
                  "critico" if total else "ok", "Ver o que houve" if total else "Tudo certo",
                  link="/caixa", link_texto="Abrir conferência")


def _passos(con, usuario, empresas: list[int]) -> list[Passo]:
    passos = []
    lista = repo.listar_empresas(con, empresas)
    com_cert = [e for e in lista if certificados.situacao(con, e["id"])]
    passos.append(Passo(bool(com_cert), "Enviar o certificado de uma empresa",
                        "Com ele o Logos Match busca as notas de serviço sozinho." if not com_cert
                        else f"Feito: {com_cert[0]['apelido'] or com_cert[0]['razao_social']}",
                        "/comecar", "Enviar agora"))
    faltam = [e for e in lista if e not in com_cert]
    if com_cert and faltam:
        nomes = ", ".join((e["apelido"] or e["razao_social"]) for e in faltam[:4])
        passos.append(Passo(False, "Enviar o certificado das outras empresas", nomes, "/comecar", "Enviar agora"))
    tem_email = any(c["tipo"] == "email" and c["ativo"] for c in banco.listar_canais(con))
    passos.append(Passo(tem_email, "Configurar o e-mail que o Logos Match usa para enviar",
                        "Para mandar o pacote ao contador e os códigos de senha.", "/canais", "Configurar"))
    tem_contador = bool(repo.listar_escritorios(con, so_ativos=True))
    passos.append(Passo(tem_contador, "Cadastrar o e-mail do contador",
                        "Para o pacote do mês sair sozinho no dia 5.", "/escritorios", "Cadastrar"))
    passos.append(Passo(bool(usuario["email"]), "Cadastrar o seu e-mail",
                        "Para recuperar a senha se esquecer.", "/usuarios", "Cadastrar"))
    return passos


def montar(con, usuario_id: int, agora: datetime | None = None) -> Resumo:
    agora = agora or datetime.now(timezone.utc)
    usuario = acesso.carregar_usuario(con, usuario_id)
    local = agora.astimezone(FUSO)
    resumo = Resumo(_saudacao(usuario["nome"], local))
    empresas = acesso.empresas_visiveis(con, usuario)
    if acesso.pode(usuario, Acao.VER_FISCAL):
        resumo.cartoes += _cartoes_fiscais(con, empresas, local.date(), agora)
    if acesso.pode(usuario, Acao.VER):
        caixa = _cartao_caixa(con, acesso.postos_visiveis(con, usuario), local.date() - timedelta(days=1))
        if caixa:
            resumo.cartoes.append(caixa)
    if usuario["perfil"] == Perfil.ADMINISTRADOR.value:
        resumo.passos = _passos(con, usuario, empresas)
    return resumo
