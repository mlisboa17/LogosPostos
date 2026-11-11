"""Teste manual, somente leitura, da busca de NFS-e no sistema nacional (ADN) com um certificado A1.

Pede o arquivo e a senha no terminal (a senha não aparece), consulta e mostra só um resumo:
quantos documentos, tipos, faixa de NSU, quantas notas por CNPJ tomador e, se der erro, a resposta
do sistema nacional. Não grava nada.

Uso (na pasta WebPosto_API):  .venv\\Scripts\\python.exe scripts\\testar_nfse_adn.py
"""
from __future__ import annotations

import getpass
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.hazmat.primitives.serialization import pkcs12  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from src.modules.fiscal_docs import adn_nfse as adn  # noqa: E402
from src.modules.fiscal_docs.modelos import XmlInvalido  # noqa: E402
from src.modules.fiscal_docs.parser import ler  # noqa: E402

PASTA = Path(r"C:\Projetos\LogosCertificados")
MAX_CHAMADAS = 20


def escolher_arquivo() -> Path:
    arquivos = sorted(p for p in PASTA.iterdir() if p.suffix.lower() in (".pfx", ".p12")) if PASTA.exists() else []
    for i, p in enumerate(arquivos, 1):
        print(f"  {i}. {p.name}")
    escolha = input("Número do certificado (ou caminho completo): ").strip().strip('"')
    return arquivos[int(escolha) - 1] if escolha.isdigit() and 0 < int(escolha) <= len(arquivos) else Path(escolha)


def resumo_resposta(r) -> str:
    try:
        j = r.json()
    except ValueError:
        return " ".join(r.text.split())[:300]
    lote = j.get("LoteDFe") or []
    nsus = [d.get("NSU") for d in lote]
    return (f"{j.get('StatusProcessamento')} · {j.get('TipoConsulta')} · {len(lote)} documento(s)"
            + (f" · NSU {min(nsus)}..{max(nsus)}" if nsus else "") + (f" · Erros {j.get('Erros')}" if j.get("Erros") else ""))


def main() -> None:
    arquivo = escolher_arquivo()
    pfx = arquivo.read_bytes()
    senha = getpass.getpass("Senha do certificado (não aparece): ")
    try:
        _, cert, _ = pkcs12.load_key_and_certificates(pfx, senha.encode())
    except Exception:
        sys.exit("Senha errada ou arquivo inválido.")
    cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    cnpj = cn.rsplit(":", 1)[-1] if ":" in cn else "?"
    print(f"\nCertificado de: {cn.split(':')[0]} (CNPJ {cnpj}), vale até {cert.not_valid_after_utc:%d/%m/%Y}")
    try:
        cliente = adn.cliente(pfx, senha)
    finally:
        senha = ""
    try:
        print("\n=== Onde a fila começa (só leitura) ===")
        for caminho, params in [("/DFe/0", {"cnpjConsulta": cnpj}), ("/DFe/0", {"lote": "true", "cnpjConsulta": cnpj}),
                                ("/DFe/1", {"lote": "true", "cnpjConsulta": cnpj})]:
            try:
                r = cliente.get(caminho, params=params)
                print(f"GET {caminho} {params} -> HTTP {r.status_code} · {resumo_resposta(r)}")
            except Exception as exc:  # noqa: BLE001
                print(f"GET {caminho} {params} -> falha {type(exc).__name__}")

        print("\n=== Busca completa (lote, a partir do NSU 0) ===")
        tipos, nsus, por_tomador, ilegiveis, nsu = Counter(), [], Counter(), 0, 0
        for _ in range(MAX_CHAMADAS):
            try:
                lote = adn.distribuir(cliente, nsu, cnpj)
            except adn.AdnErro as exc:
                print(f"ERRO ({exc.tipo}) no NSU {nsu}: {exc.detalhe or 'sem detalhe'}")
                break
            if lote.vazio:
                print(f"Fim da fila depois do NSU {nsu}.")
                break
            for d in lote.documentos:
                tipos[d.tipo or "?"] += 1
                nsus.append(d.nsu)
                nsu = max(nsu, d.nsu)
                if d.xml and "EVENTO" not in d.tipo:
                    try:
                        por_tomador[ler(d.xml).destinatario_cnpj or "sem tomador"] += 1
                    except (XmlInvalido, ValueError, ArithmeticError):
                        ilegiveis += 1
        else:
            print(f"Parei após {MAX_CHAMADAS} chamadas (há mais documentos).")
    finally:
        cliente.close()
    print("\n=== Resumo ===")
    print(f"Documentos: {sum(tipos.values())} {dict(tipos)}")
    if nsus:
        print(f"NSU de {min(nsus)} a {max(nsus)}")
    for tomador, n in por_tomador.most_common():
        marca = " <- esta empresa" if tomador == cnpj else (" <- mesma raiz" if tomador[:8] == cnpj[:8] else "")
        print(f"  tomador {tomador}: {n} nota(s){marca}")
    if ilegiveis:
        print(f"Ilegíveis: {ilegiveis}")


if __name__ == "__main__":
    main()
