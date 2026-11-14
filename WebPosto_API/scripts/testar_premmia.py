"""Teste manual da coleta do Premmia com o código do Logos Match, antes do instalador.

Lê os postos do Logos Match instalado (só leitura) e usa o usuário/senha do Premmia já guardados nele
(Gerenciador de Credenciais do Windows). Abre o navegador na sua frente, baixa as vendas de ontem
numa pasta separada (Documentos\\LogosMatch-teste-Premmia) e mostra quantas vendas e o total.
Não grava nada no Logos Match instalado. Faz um login de verdade no portal do Premmia.

Uso (na pasta WebPosto_API):  .venv\\Scripts\\python.exe scripts\\testar_premmia.py
"""
from __future__ import annotations

import getpass
import os
import shutil
import sqlite3
import sys
import threading
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.match import banco, credenciais, explicar, unidades  # noqa: E402
from apps.match.premmia_tela import ETAPAS  # noqa: E402
from src.modules.cash_reconciliation.adapters import premmia_portal  # noqa: E402
from src.modules.cash_reconciliation.domain.models import Unidade  # noqa: E402
from src.modules.cash_reconciliation.domain.tempo import agora  # noqa: E402
from src.shared.segredos import definir_resolvedor  # noqa: E402

os.environ.setdefault("LOGOS_NAVEGADOR_CANAL", "msedge")  # o mesmo navegador do Match instalado
BANCO = Path(os.getenv("LOCALAPPDATA", "")) / "LogosMatch" / "logosmatch.db"
SAIDA = Path.home() / "Documents" / "LogosMatch-teste-Premmia"


def main() -> None:
    if not BANCO.exists():
        sys.exit(f"Não achei o banco do Logos Match em {BANCO}. O Match está instalado neste usuário?")
    con = sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    postos = banco.listar_postos(con)
    print("Postos no Logos Match:" if postos else "Nenhum posto cadastrado no Logos Match.")
    for i, p in enumerate(postos, 1):
        f = next((f for f in banco.fontes_do_posto(con, p["id"]) if f["tipo"] == "premmia"), None)
        tem = credenciais.tem(f"{p['id']}/premmia/usuario") and credenciais.tem(f"{p['id']}/premmia/senha")
        situacao = ("Premmia ligado" if f and f["ativo"] else "Premmia desligado" if f else "sem Premmia")
        print(f"  {i}. {p['apelido'] or p['nome']} · {situacao} · "
              + ("usuário/senha guardados" if tem else "sem usuário/senha"))
    print("  0. Testar só com usuário e senha (sem posto)")
    escolha = input("Número: ").strip()
    if not escolha.isdigit() or not 0 <= int(escolha) <= len(postos):
        sys.exit("Número inválido.")
    if int(escolha) == 0:
        unidade = Unidade(empresa_codigo=0, nome="Teste Premmia", apelido="teste", destinos=(), chave_env="-",
                          premmia_ativo=True, premmia_usuario_env="TESTE_PREMMIA_USUARIO",
                          premmia_senha_env="TESTE_PREMMIA_SENHA")
        guardado = False
    else:
        posto = postos[int(escolha) - 1]
        unidade = unidades.do_posto(con, posto)
        guardado = (credenciais.tem(f"{posto['id']}/premmia/usuario")
                    and credenciais.tem(f"{posto['id']}/premmia/senha"))
    do_match = unidades.resolvedor(con)
    con.close()

    digitado: dict[str, str] = {}
    if not guardado:
        print()
        print("Usuário e senha do portal do Premmia (não ficam salvos; a senha não aparece):")
        digitado[unidade.premmia_usuario_env] = input("Usuário: ").strip()
        digitado[unidade.premmia_senha_env] = getpass.getpass("Senha: ")
    definir_resolvedor(lambda nome: digitado.get(nome) or do_match(nome))

    texto = input("Dia (dd/mm/aaaa, Enter = ontem): ").strip()
    if texto:
        d, m, a = (int(x) for x in texto.split("/"))
        dia = date(a, m, d)
    else:
        dia = agora().date() - timedelta(days=1)

    pasta = SAIDA / (unidade.apelido or "posto")
    shutil.rmtree(pasta, ignore_errors=True)  # cada teste começa do zero
    pasta.mkdir(parents=True)
    print(f"\n=== {unidade.apelido} · Premmia · {dia:%d/%m/%Y} ===")
    print("O navegador vai abrir. Se o portal pedir verificação ('não sou robô'), resolva na janela.\n")

    erro: list[BaseException] = []

    def rodar():
        try:
            premmia_portal.coletar_sync(unidade, [dia], visivel=True, diretorio=pasta)
        except BaseException as exc:  # noqa: BLE001 - mostrado abaixo
            erro.append(exc)

    t = threading.Thread(target=rodar, daemon=True)
    inicio, ultima = time.monotonic(), None
    t.start()
    while t.is_alive():
        etapa = premmia_portal.ETAPA_ATUAL.get(unidade.empresa_codigo)
        if etapa and etapa != ultima:
            print(f"  {time.monotonic() - inicio:5.0f}s  {ETAPAS.get(etapa, etapa)}…")
            ultima = etapa
        t.join(0.5)

    if erro:
        exc = erro[0]
        print(f"\nNÃO DEU CERTO: {explicar.erro_pt(exc)}")
        print(f"(tipo {type(exc).__name__}, etapa {getattr(exc, 'etapa', None) or '?'})")
        return

    transacoes = premmia_portal.buscar_transacoes(unidade, dia, pasta)
    validas = [t for t in transacoes if t.situacao is None]
    total = sum((t.valor for t in validas), Decimal(0))
    outras = len(transacoes) - len(validas)
    print(f"\n=== Resultado ({time.monotonic() - inicio:.0f}s) ===")
    print(f"{len(validas)} venda(s) processada(s), total {explicar.dinheiro(total)}"
          + (f" · {outras} com outra situação (cancelada/pendente)" if outras else ""))
    planilha = premmia_portal.caminho_mensal(unidade, dia, pasta)
    print(f"Planilha do mês: {planilha}")
    if unidade.empresa_codigo:
        comparar_com_webposto(unidade, dia, transacoes, pasta, digitado)
    else:
        print("\n(Sem posto escolhido: a comparação com o webPosto precisa do código da empresa.)")
    os.startfile(pasta)  # abre a pasta no Explorer


def comparar_com_webposto(unidade, dia, transacoes, pasta: Path, digitado: dict) -> None:
    """Mesma comparação da coleta do Match, só leitura no webPosto. Mostra as ações sugeridas."""
    import asyncio

    from apps.match import relatorio_premmia, sugestoes
    from src.modules.cash_reconciliation.application import conciliar_cartoes
    from src.modules.cash_reconciliation.config import definir_provedor_unidades
    from src.shared.segredos import obter_segredo

    if not obter_segredo(unidade.chave_env):
        if input("\nComparar com o webPosto? Precisa da chave da API (s/N): ").strip().lower() != "s":
            return
        digitado[unidade.chave_env] = getpass.getpass("Chave do webPosto (não aparece): ")
    definir_provedor_unidades(lambda: {unidade.empresa_codigo: unidade})
    print(f"\n=== Comparando com o webPosto (empresa {unidade.empresa_codigo}, só leitura) ===")
    try:
        cartoes, abastecimentos, itens = asyncio.run(
            conciliar_cartoes.coletar_contexto_cartoes(unidade.empresa_codigo, dia))
    except Exception as exc:  # noqa: BLE001 - nunca str(exc): pode ter a chave
        print(f"NÃO DEU CERTO no webPosto: {explicar.erro_pt(exc)} (tipo {type(exc).__name__})")
        return
    cartoes = [c for c in cartoes if conciliar_cartoes.da_adquirente(c, "PREMMIA", unidade.administradoras)]
    resultado = conciliar_cartoes.conciliar(unidade.empresa_codigo, "PREMMIA", dia, transacoes, cartoes,
                                            abastecimentos, itens)
    oc = sugestoes.ocorrencias(resultado, abastecimentos)
    do_dia = [t for t in transacoes if t.situacao is None and t.momento.date() == dia]
    total_p = sum((t.valor for t in do_dia), Decimal(0))
    total_w = sum((c.valor for c in cartoes if c.momento.date() == dia), Decimal(0))
    cons = sugestoes.consolidar(oc, total_p, total_w)
    print(f"Premmia {explicar.dinheiro(total_p)} · webPosto {explicar.dinheiro(total_w)} · "
          f"diferença {explicar.dinheiro(cons.diferenca)}")
    print(f"{len(resultado.casados)} venda(s) batem · {len(oc)} ocorrência(s) · "
          f"{cons.nao_resolvidas} não resolvida(s)")
    for o in oc:
        print(f"\n  [{sugestoes.ACOES[o.acao]}] {explicar.dinheiro(o.valor)} · {o.funcionario}")
        print(f"    {o.explicacao}")
        print(f"    O que fazer: {o.correcao}")
        print(f"    Critérios: {'; '.join(o.criterios)}")
    rel = relatorio_premmia.Relatorio(
        {"apelido": unidade.apelido, "nome": unidade.nome}, dia, dia,
        [relatorio_premmia.Dia(dia, "ok", total_p, total_w, len(oc))], [(dia, o) for o in oc], cons, 0, [])
    arquivo = pasta / f"Conciliacao_Premmia_{dia:%Y%m%d}.xlsx"
    arquivo.write_bytes(relatorio_premmia.planilha(rel))
    print(f"\nPlanilha da conciliação: {arquivo}")


if __name__ == "__main__":
    main()
