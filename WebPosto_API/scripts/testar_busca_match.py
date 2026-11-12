"""Teste de ponta a ponta da busca de NFS-e com o código do próprio Logos Match, antes do instalador.

Usa um banco de teste separado (não mexe no Match instalado): cria a empresa pelo certificado,
busca no sistema nacional igual ao botão "Buscar agora" e baixa XML (zip) e PDF (um arquivo só)
para a pasta Documentos\\LogosMatch-teste-NFSe. Somente leitura no sistema nacional.

Uso (na pasta WebPosto_API):  .venv\\Scripts\\python.exe scripts\\testar_busca_match.py
"""
from __future__ import annotations

import getpass
import os
import shutil
import sys
import threading
import time
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PASTA_CERTS = Path(r"C:\Projetos\LogosCertificados")
SAIDA = Path.home() / "Documents" / "LogosMatch-teste-NFSe"


def escolher_arquivo() -> Path:
    arquivos = sorted(p for p in PASTA_CERTS.iterdir() if p.suffix.lower() in (".pfx", ".p12")) if PASTA_CERTS.exists() else []
    for i, p in enumerate(arquivos, 1):
        print(f"  {i}. {p.name}")
    escolha = input("Número do certificado (ou caminho completo): ").strip().strip('"')
    return arquivos[int(escolha) - 1] if escolha.isdigit() and 0 < int(escolha) <= len(arquivos) else Path(escolha)


def main() -> None:
    arquivo = escolher_arquivo()
    senha = getpass.getpass("Senha do certificado (não aparece): ")

    dados = SAIDA / "dados"
    shutil.rmtree(dados, ignore_errors=True)  # cada teste começa do zero
    os.environ["LOGOS_MATCH_DIR"] = str(dados)

    from apps.match import banco
    from apps.match.fiscal import captura_nfse, certificados
    from src.modules.fiscal_docs import pdf
    from src.modules.fiscal_docs.parser import ler

    con = banco.conectar(dados / "teste.db")
    try:
        empresa_id, info = certificados.criar_empresa_pelo_certificado(con, arquivo.read_bytes(), senha)
    except certificados.CertificadoInvalido as exc:
        sys.exit(f"Certificado recusado: {exc}")
    finally:
        senha = ""
    print(f"\nEmpresa: {info.titular} · CNPJ {info.cnpj} · certificado vale até {info.valido_ate:%d/%m/%Y}")

    fim = threading.Event()

    def mostrar_andamento():
        while not fim.wait(2):
            a = captura_nfse._ANDAMENTO
            if a:
                print(f"  consultando {a.get('empresa')} (CNPJ {a.get('cnpj')}): "
                      f"{a.get('lidos', 0)} lido(s), {a.get('novas', 0)} nova(s)")

    print("\n=== Buscando no sistema nacional (igual ao botão Buscar agora) ===")
    t = threading.Thread(target=mostrar_andamento, daemon=True)
    t.start()
    inicio = time.monotonic()
    r = captura_nfse.buscar_empresa(con, empresa_id, forcar=True)
    fim.set()
    print(f"Resultado: {r.situacao} · {r.mensagem} ({time.monotonic() - inicio:.0f}s)")

    docs = con.execute("SELECT * FROM documento WHERE empresa_id=? AND tipo='nfse' ORDER BY emissao_em",
                       (empresa_id,)).fetchall()
    print(f"\n=== Guardadas: {len(docs)} nota(s) de serviço ===")
    for comp, n in sorted(Counter(d["competencia"] for d in docs).items()):
        print(f"  competência {comp}: {n}")
    if not docs:
        con.close()
        return

    baixados = SAIDA / "baixados"
    shutil.rmtree(baixados, ignore_errors=True)
    baixados.mkdir(parents=True)
    zip_xml = baixados / f"NFSe_{info.cnpj}_xml.zip"
    with zipfile.ZipFile(zip_xml, "w", zipfile.ZIP_DEFLATED) as z:
        for d in docs:
            z.write(d["xml_path"], f"{d['chave']}.xml")
    pdfs, falhas = [], 0
    for d in docs:
        xml = Path(d["xml_path"]).read_bytes()
        try:
            pdfs.append(pdf.gerar_pdf(xml, ler(xml)))
        except Exception:  # noqa: BLE001 - conta e segue
            falhas += 1
    arq_pdf = baixados / f"NFSe_{info.cnpj}.pdf"
    if pdfs:
        arq_pdf.write_bytes(pdf.unir(pdfs))
    con.close()

    print("\n=== Download ===")
    print(f"XML: {zip_xml.name} · {len(docs)} arquivo(s) · {zip_xml.stat().st_size // 1024} KB")
    if pdfs:
        print(f"PDF: {arq_pdf.name} · {len(pdfs)} nota(s) · {arq_pdf.stat().st_size // 1024} KB")
    if falhas:
        print(f"PDF não gerado para {falhas} nota(s).")
    print(f"Pasta: {baixados}")
    os.startfile(baixados)  # abre a pasta no Explorer


if __name__ == "__main__":
    main()
