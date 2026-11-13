"""Teste manual da coleta do Premmia com o código do Logos Match, antes do instalador.

Lê os postos do Logos Match instalado (só leitura) e usa o usuário/senha do Premmia já guardados nele
(Gerenciador de Credenciais do Windows). Abre o navegador na sua frente, baixa as vendas de ontem
numa pasta separada (Documentos\\LogosMatch-teste-Premmia) e mostra quantas vendas e o total.
Não grava nada no Logos Match instalado. Faz um login de verdade no portal do Premmia.

Uso (na pasta WebPosto_API):  .venv\\Scripts\\python.exe scripts\\testar_premmia.py
"""
from __future__ import annotations

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

from apps.match import banco, explicar, unidades  # noqa: E402
from apps.match.premmia_tela import ETAPAS  # noqa: E402
from src.modules.cash_reconciliation.adapters import premmia_portal  # noqa: E402
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
    postos = [p for p in banco.listar_postos(con)
              if any(f["tipo"] == "premmia" and f["ativo"] for f in banco.fontes_do_posto(con, p["id"]))]
    if not postos:
        sys.exit("Nenhum posto com o Premmia ligado no Logos Match.")
    for i, p in enumerate(postos, 1):
        print(f"  {i}. {p['apelido'] or p['nome']}")
    escolha = input("Número do posto: ").strip()
    if not escolha.isdigit() or not 0 < int(escolha) <= len(postos):
        sys.exit("Número inválido.")
    posto = postos[int(escolha) - 1]
    definir_resolvedor(unidades.resolvedor(con))
    unidade = unidades.do_posto(con, posto)
    con.close()

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
    os.startfile(pasta)  # abre a pasta no Explorer


if __name__ == "__main__":
    main()
