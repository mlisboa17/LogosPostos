# Logos Match — módulo Notas Fiscais (design, 23/10/2026)

Status: aprovado pelo diretor em 23/10/2026 (fonte de NF-e = webPosto, ajustada após a sondagem do mesmo dia). Nada implementado.
Base: Logos Match v0.2 (`docs/superpowers/specs/2026-10-18-logos-match-design.md`). Este documento só descreve o que muda.

## 1. Intenção
Todo mês alguém precisa juntar as notas fiscais recebidas por cada CNPJ do grupo e mandar para o escritório de contabilidade de cada empresa. Hoje isso é manual. O diretor quer que o Logos Match **baixe sozinho todas as notas emitidas contra os CNPJs cadastrados** (produto, serviço e frete) e, no mês seguinte, **monte o pacote e envie a cada escritório**, ou só deixe pronto para baixar.

Pedido explícito: algo **leve**. Por isso é um módulo dentro do Logos Match (mesmo instalador, login, agendador e canais), não um app novo.

Sucesso: no dia 5 de novembro, cada escritório recebe por e-mail, sem ninguém tocar em nada, o pacote de outubro de cada empresa sua: XMLs, PDFs e planilha resumo. Se faltar algo, o envio é retido e o painel explica o motivo em português simples.

## 2. Objetivos, não objetivos, anti-objetivos
**Objetivos**
- Cadastro de **empresas** (CNPJ, razão social, município/UF, certificado A1) e de **escritórios de contabilidade** (nome, e-mails, empresas atendidas, preferências do pacote).
- Captura diária automática, por empresa, de documentos em que o CNPJ é destinatário ou tomador:
  - **NF-e** (modelo 55): **fonte principal é o webPosto**. `V1/NOTAS_MANIFESTACAO` lista as notas; `V1/NOTAS_ENTRADA/XML/{chave}` devolve o XML completo; `V1/NOTAS_ENTRADA` dá frete, placa e número do CT-e. O próprio webPosto consulta a SEFAZ e manifesta, então nós não fazemos isso. **Reserva**: Distribuição DF-e da SEFAZ, com ciência 210210 automática (autorizada pelo diretor em 23/10/2026), só para empresa sem chave webPosto ou quando o diretor ligar por empresa.
  - **NFS-e** pela API de distribuição do Ambiente de Dados Nacional (ADN) da NFS-e, para contribuintes.
  - **CT-e** (frete) pela Distribuição DF-e do CT-e, quando existir, ligado à NF-e transportada.
- **Importação manual**: arrastar XML ou ZIP (baixado do portal de uma prefeitura fora do ADN, ou de qualquer outro lugar). O documento entra igual aos capturados.
- **Consulta** com filtros: período (emissão ou competência), empresa, fornecedor (CNPJ ou nome), tipo (NF-e, NFS-e, CT-e), situação (autorizada, cancelada, só resumo), combustível sim/não, valor. Abrir XML ou PDF, baixar a seleção.
- **Pacote do mês** por empresa:
  - XMLs sempre separados;
  - PDFs **separados, unificados num arquivo, ou ambos** (escolha por escritório e também na hora de baixar);
  - planilha resumo .xlsx.
- **Envio programado** por escritório: dia do mês (padrão 5) e modo (**enviar por e-mail** ou **só gerar**). Envio manual e reenvio pelo painel.
- **Conferência antes do envio**: se faltar algo, retém o envio e pede aprovação na tela (seção 8).
- Perfil de acesso novo **Contabilidade**: vê só o módulo Notas Fiscais das empresas do seu escopo.

**Não objetivos**
- Emitir, cancelar ou corrigir notas.
- Manifestações conclusivas (confirmação, desconhecimento, operação não realizada). Só a ciência é automática.
- Notas de saída (vendas do posto).
- Escrita no webPosto: só GET, nenhuma manifestação ou entrada de nota pelo webPosto.
- Integração com o portal de cada prefeitura (o plano B é a importação manual).
- Escrituração ou lançamento contábil.

**Anti-objetivos (falhou mesmo se "funcionar")**
- Certificado, senha ou chave em texto puro em disco, log, planilha, export ou repo.
- Pacote enviado incompleto sem aviso, ou o mesmo pacote enviado duas vezes sem alguém pedir.
- Bloqueio na SEFAZ por consumo indevido (cStat 656) causado pelo app.
- Dois sistemas nossos (LOGOS e Match, ou duas máquinas) consultando o mesmo CNPJ.
- Duplicação permanente do código de DF-e. A duplicação é aceita só durante a transição (seção 4).
- Datas fora do padrão: fuso America/Recife, exibição dd/mm/aaaa HH:mm.

## 3. Restrições e fatos
- **Sondagem do webPosto (23/10/2026, somente GET, Doze Filial II 74014, setembro/2026)**, conforme a spec oficial `docs/external/webposto/openapi_integracao_2026-10-06.json`:
  - `V1/NOTAS_MANIFESTACAO` (200): lista as NF-e contra o CNPJ, com os campos `chaveDocumento`, `cnpjFornecedor`, `razaoSocialFornecedor`, `dataEmissao`, `valor`, `situacaoManifestacao`, `protocoloManifestacao`, `tipoProduto` (Combustível/Produto), `recebido` e `compraCodigo`; paginação por `ultimoCodigo`/`limite`.
  - `V1/NOTAS_ENTRADA/XML/{chaveNfe}` (200): **`nfeProc` completo, com `<transp>`**. Funciona também para chave vinda da lista de manifestação.
  - `V1/NOTAS_ENTRADA` (200): notas lançadas, com `tipoFrete`, `valorFrete`, `placaVeiculo`, `placaReboque`, `transportadorCodigo`, `cteNumero`, `cteDataEmissao` e impostos (inclusive CBS/IBS/IS).
  - `V1/NOTAS_SERVICO` (200): **0 notas** em setembro. As NFS-e tomadas não aparecem no webPosto, então a NFS-e continua pelo ADN e pela importação manual.
  - `V1/DFE_XMLS` (por modelo/número/série) existe, mas não foi testado.
  - **A validar pelo construtor:** se `NOTAS_MANIFESTACAO` traz **todas** as notas do CNPJ, inclusive as ainda não lançadas (comparar uma vez com a SEFAZ ou com a contabilidade); se o XML vem de nota cancelada; e o limite de requisições do webPosto.
- Chaves webPosto por empresa: já existem no `.env` do LOGOS (`WEBPOSTO_API_KEY_*`). No Match, entram pelo painel (Credential Manager), como a fonte `webposto` do posto.
- **Código de DF-e existente** (branch do OneDrive, mesmo GitHub `mlisboa17/LogosPostos`): `WebPosto_API/src/operational/dfe/` (parser, `pynfe_provider.py`, `xml_import.py`, `certificate_service.py`, `vault.py`) e `src/operational/dfe_sync/` (`sefaz_once.py`, leasing, inbox local), cerca de 6.300 linhas, com dependências `pynfe 0.6.5`, `cryptography`, `lxml`. Esse código **não está** no branch `feature/logos-match`.
- Relatório do Cursor (15/08/2026): o fluxo da SEFAZ funciona, mas parou com **cStat 656**; existe a regra de uma página por execução e de **só avançar o NSU depois de gravar**. Os dois fluxos (custo e operacional) têm parsers duplicados.
- **SEFAZ DistDFe**: quando não há documentos novos (cStat 137) ou o NSU chegou ao máximo, esperar **1 hora** antes de consultar o mesmo CNPJ. Excesso gera 656 e bloqueio temporário.
- **NF-e sem manifestação** vem só como resumo (`resNFe`). Depois da ciência, o XML completo aparece num ciclo seguinte.
- **ADN NFS-e (contribuintes)**: `GET /DFe/{NSU}` com mTLS (A1 do CNPJ). Com `lote=true`, devolve até 50 documentos depois do NSU. Fila vazia responde 404 `NENHUM_DOCUMENTO_LOCALIZADO`. Pesquisa de 23/10: o manual oficial confirma o endpoint unitário; o lote está confirmado só por projetos da comunidade, e **o construtor valida em produção restrita**. O PDF oficial (DANFSe) **não é mais gerado pela API desde 01/07/2026**: o app gera localmente.
- **Municípios dos postos (PE)**:
  - **Recife e Olinda**: confirmados no padrão nacional.
  - **Paulista (GISS), Abreu e Lima (Tributus) e Igarassu (Tinus)**: não confirmados. Validar no primeiro uso real comparando com notas conhecidas. Se não vierem pelo ADN, usar a importação manual.
- **Certificados**: o cofre atual só tem A1 do CNPJ 02080237000155 (118508). Os CNPJs do Doze (52308604000101 e 52308604000284) ainda não têm certificado.
- **Windows Credential Manager** limita o tamanho do segredo (cerca de 2,5 KB) e não comporta o .pfx. Ver seção 6.
- **E-mail**: anexos acima de cerca de 20 MB são recusados pela maioria dos provedores (Gmail limita em 25 MB).

## 4. Decisões de arquitetura
**Princípio (diretor, 23/10/2026):** o LOGOS é o sistema principal e o Match é um subproduto dele. A forma escolhida é **um único consultor por CNPJ + acervo fiscal compartilhado**, para não prejudicar as empresas com bloqueio na SEFAZ e manter tudo funcionando.

**4.0 Fontes por tipo de documento (decisão do diretor, 23/10/2026, após a sondagem):**

| Documento | Fonte principal | Reserva | Consulta à SEFAZ ou ao ADN por nós |
|---|---|---|---|
| NF-e | **webPosto** (`NOTAS_MANIFESTACAO` + `NOTAS_ENTRADA/XML/{chave}` + `NOTAS_ENTRADA`) | SEFAZ DistDFe NF-e, ligada por empresa | Nenhuma, enquanto a empresa tiver chave webPosto |
| CT-e | SEFAZ DistDFe CT-e (o webPosto só informa o número) | importação manual | Sim, com as regras da seção 4.4 |
| NFS-e | ADN (distribuição para contribuintes) | importação manual | Sim, com as regras da seção 4.4 |

Consequências:
- Some o risco de 656 na NF-e.
- O conflito LOGOS × Match na NF-e da Conveniência 24h desaparece, porque os dois leem do webPosto, que só aceita GET.
- O certificado A1 passa a ser necessário **só para CT-e e NFS-e**. Empresa sem certificado ainda tem NF-e completa, e a conferência avisa que CT-e e NFS-e não estão sendo capturados.
- A leitura do webPosto não precisa de dono. Para evitar chamadas repetidas, cada máquina só lê as empresas dos postos que ela tem (trava do `registro_rede`).

**4.1 Biblioteca única, do LOGOS.** O núcleo do DF-e vira o pacote `WebPosto_API/src/modules/fiscal_docs/` no repo canônico. LOGOS e Match usam o mesmo pacote; não há segundo código de consulta.
- `webposto_notas.py`: novo. Lista `NOTAS_MANIFESTACAO`, baixa o XML por chave e lê `NOTAS_ENTRADA` (frete, placa, CT-e), sempre com GET e chave nunca logada. Segue o padrão de `adapters/webposto_*` do `cash_reconciliation`.
- `sefaz_dist.py`: DistDFe de CT-e e, como reserva, de NF-e (a partir de `pynfe_provider` e `sefaz_once`).
- `adn_nfse.py`: novo, distribuição do ADN.
- `parser.py`: parser único de NF-e, NFS-e e CT-e com Pydantic, unindo os dois parsers atuais.
- `manifestacao.py`: só ciência 210210.
- `controle_nsu.py`: NSU só avança depois de gravar.
- `limitador.py`: regras de proteção (4.4).
- `dono.py`: registro do dono da consulta (4.2).
- `acervo.py`: leitura e gravação do acervo compartilhado (4.3).
- `pdf.py`: DANFE, DANFSe e DACTE a partir do XML, mais a união de PDFs.

Escopo da extração (decisão minha): só esse núcleo. `service.py`, `store.py`, `manifestation_inbox.py`, `registration_analysis.py`, `barcode_identity.py`, `pre_register.py` e o cofre Fernet ficam no LOGOS, porque atendem o cadastro de produtos (ACT-03).

**4.2 Um único dono da consulta por CNPJ** (vale para as consultas à SEFAZ e ao ADN: CT-e, NFS-e e a reserva de NF-e). Registro em `<pasta da rede>\fiscal\donos.json`, por CNPJ, com:
- sistema (`logos` ou `match`);
- máquina e `id_instalacao`;
- desde quando;
- último NSU de cada fila (NF-e, CT-e, NFS-e);
- ciência ligada (sim/não).

Regras:
- Antes de qualquer consulta, LOGOS e Match leem o registro. **Quem não é dono não consulta**, só lê o acervo.
- CNPJ sem dono: o primeiro sistema que tiver o certificado e for autorizado no painel vira dono.
- **"Assumir consulta"** (botão no Match; função ou CLI no LOGOS): transfere a posse levando o último NSU de cada fila. O novo dono continua do mesmo ponto, sem baixar tudo de novo.
- A gravação do registro reaproveita o mecanismo de `registro_rede.py` do Match (escrita atômica, conflito resolvido pelo "Assumir").
- O lease local do LOGOS (`dfe_sync/lease.py`) continua valendo para evitar duas execuções na mesma máquina.

**Situação inicial:**
- **02080237000155 (Conveniência 24h, 118508):** dono = LOGOS na fila NF-e de reserva (último NSU 30858), que fica **desligada** porque a NF-e vem do webPosto. CT-e e NFS-e: sem dono até alguém cadastrar o certificado e assumir.
- **Demais CNPJs:** ninguém consulta hoje. O dono passa a ser o Match quando o certificado for cadastrado nele.

**4.3 Acervo fiscal compartilhado.** O dono grava cada documento em `<pasta da rede>\fiscal\<cnpj>\<AAAA-MM>\<tipo>\<chave>.xml`, mais um índice `indice.jsonl` (append-only: chave, tipo, emissão, emitente, valor, situação, origem, hash).
- O Match importa do acervo para o SQLite dele, mesmo nos CNPJs de que não é dono.
- O LOGOS lê o acervo para cadastro de produtos e custo.
- Importações manuais (XML ou ZIP) também entram no acervo.
- O acervo é a fonte única do pacote da contabilidade.
- Sem pasta da rede configurada, o Match usa uma pasta local e só funciona como dono.

**4.4 Proteção contra bloqueio.** O webPosto também consulta a SEFAZ e não temos controle sobre isso.
- Uma página por chamada.
- Com cStat 137 ou NSU no máximo, a próxima consulta só depois de 1 h.
- No máximo 24 consultas por CNPJ e por fila a cada 24 h.
- Com cStat 656, o CNPJ fica pausado por 6 h, gera aviso no painel e por e-mail ao administrador, e não há nova tentativa automática antes disso.
- A carga inicial (cerca de 3 meses disponíveis na SEFAZ) segue as mesmas regras, distribuída ao longo do dia.

**4.5 Ciência 210210.** Autorizada pelo diretor em 23/10/2026, mas **só é usada na reserva de NF-e pela SEFAZ**. Com o webPosto como fonte, quem manifesta é o próprio webPosto, e nós não manifestamos.
- Quando a reserva estiver ligada, a ciência é uma configuração do CNPJ, guardada no registro de donos, e quem executa é o dono.
- O LOGOS continua sem manifestar até passar a usar o pacote.

**4.6 Certificado.** Cada sistema guarda o certificado no próprio cofre: o Match usa DPAPI e Credential Manager (seção 6); o LOGOS usa o cofre Fernet atual. Assumir a consulta exige que o novo dono tenha o certificado cadastrado.

**4.7 Ordem de entrega (decisão minha), no branch `feature/logos-match`:**
1. `fiscal_docs` com parser, `webposto_notas`, acervo, planilha e PDF, com testes. Isso já entrega **NF-e completa pelo webPosto**, sem nenhuma consulta à SEFAZ. O LOGOS segue com o código antigo nessa etapa (duplicação temporária aceita).
2. Módulo Notas Fiscais do Match: empresas, escritórios, consulta, pacote, envio e conferência (seções 5 a 9), já funcionando com NF-e.
3. Registro de donos, com o LOGOS respeitando `donos.json` antes de consultar (uma checagem curta em `sefaz_once`, `AutoDfeSyncWorker`, `scripts/dfe_cost_sync_118508.py` e `autopilot/orchestrator.py`). **É pré-requisito para qualquer consulta do Match à SEFAZ ou ao ADN.**
4. CT-e (SEFAZ) e NFS-e (ADN) com certificado, seguindo as regras da seção 4.4.
5. Depois, numa entrega própria, o LOGOS troca os imports pelo pacote e remove o código duplicado, mantendo verdes `test_dfe_safety_baseline` e `test_dfe_cost_sync`.

**Dentro do Match** (`apps/match/`):
```
fiscal/
  empresas.py      cadastro de empresa + certificado
  escritorios.py   escritórios de contabilidade e preferências do pacote
  captura.py       ciclo diário por empresa (NF-e, CT-e, NFS-e), respeita cooldown e trava entre máquinas
  pacote.py        monta pacote do mês (XML, PDFs, xlsx, zip)
  conferencia.py   checagens antes do envio (seção 8)
  planilha.py      xlsx do resumo (seção 7)
painel/            novas telas (seção 9)
```
Reaproveita: `banco.py` (migrações), `agendador.py`, `canais/email_smtp.py`, `acesso.py` (perfis), `registro_rede.py` (trava entre máquinas), `credenciais.py`.

**Bibliotecas** (escolha final do construtor):
- geração de DANFE e DACTE offline (ex.: `brazilfiscalreport`);
- DANFSe pelo leiaute nacional, com template próprio se a biblioteca não cobrir;
- `pypdf` para unir PDFs;
- `openpyxl` (já usado).

Tudo precisa funcionar empacotado no PyInstaller.

**Versão**: Logos Match **0.3.0**.

## 5. Modelo de dados (SQLite, migração nova)
- `empresa(id, cnpj UNIQUE, razao_social, municipio, uf, posto_id NULL, ativo, criado_em)`: `posto_id` liga ao posto do Match quando for o mesmo estabelecimento.
- `certificado(id, empresa_id, arquivo_ref, titular_cnpj, validade_inicio, validade_fim, situacao, criado_em)`
- `escritorio(id, nome, emails_json, dia_envio DEFAULT 5, modo ∈ {enviar, so_gerar}, pdf ∈ {separados, unificado, ambos}, ativo)`
- `escritorio_empresa(escritorio_id, empresa_id)`
- `leitura_webposto(empresa_id, ultimo_codigo_manifestacao, ultima_leitura_em, ultimo_erro)`: cursor do `NOTAS_MANIFESTACAO`.
- `nsu(empresa_id, fonte ∈ {nfe, cte, nfse}, ultimo_nsu, max_nsu, proxima_consulta_em, ultimo_cstat, ultimo_erro)`
- `documento(id, empresa_id, tipo ∈ {nfe, cte, nfse}, chave UNIQUE, numero, serie, emissao_em, competencia NULL, emitente_cnpj, emitente_nome, valor_total, situacao ∈ {autorizada, cancelada, so_resumo}, origem ∈ {webposto, sefaz, adn, importado}, combustivel BOOL, xml_path, xml_hash, capturado_em, ciencia_em NULL)`
- `documento_item(documento_id, n_item, codigo, descricao, ncm, cprod_anp NULL, quantidade, unidade, valor_unitario, valor_total, icms_json)`: para NF-e.
- `documento_transporte(documento_id, mod_frete, transportadora_cnpj, transportadora_nome, placa, uf_placa, volumes, peso_bruto)`: para NF-e.
- `frete_vinculo(cte_documento_id, nfe_chave)`: da lista de NF-e transportadas dentro do CT-e.
- `evento(documento_id, tipo, protocolo, momento)`: cancelamentos e ciência.
- `pacote(id, empresa_id, competencia 'AAAA-MM', gerado_em, arquivo_path, hash, situacao ∈ {gerado, retido, aprovado, enviado, erro}, motivo_retencao, enviado_em, aprovado_por)`

Valores em Decimal (armazenados como texto). XMLs e PDFs em `%LOCALAPPDATA%\LogosMatch\fiscal\<cnpj>\<AAAA-MM>\`, nunca no repo. Retenção: **5 anos** para XML fiscal, por exigência legal. É exceção aos 13 meses do Match (decisão minha).

## 6. Segredos e certificado
- O .pfx é cifrado com **DPAPI do usuário Windows** e gravado em `%LOCALAPPDATA%\LogosMatch\certs\<empresa_id>.bin`. A senha fica no Credential Manager (`LogosMatch/empresa/<id>/a1`). O SQLite guarda só a referência.
- No cadastro, o app valida offline: titular = CNPJ da empresa (raiz igual é aceita para filial **somente se** o certificado for e-CNPJ da matriz e a SEFAZ aceitar), validade e cadeia ICP-Brasil. Certificado com CNPJ diferente é recusado e nunca usado.
- Aviso de vencimento: 30, 15 e 7 dias antes, no painel e por e-mail ao administrador.
- A senha SMTP já existe nos canais do Match e é reaproveitada.

## 7. Planilha resumo do mês (.xlsx, uma por empresa)
1. **Notas**: data de emissão, tipo, número, série, chave, emitente (CNPJ e nome), valor total, ICMS, ICMS-ST, IPI, ISS, retenções (IR, PIS, COFINS, CSLL, INSS), situação e origem.
2. **Combustível** (uma linha por item de NF-e com `cProdANP`): data de emissão e saída, nota, distribuidora, produto, código ANP, litros, preço por litro, valor, ICMS monofásico. Transporte: modalidade CIF ou FOB, transportadora (CNPJ e nome), placa, UF da placa e **CT-e vinculado** (número e valor do frete), quando houver.
3. **Fretes (CT-e)**: emissão, número, transportadora, valor do frete, ICMS, notas transportadas.
4. **Totais**: por fornecedor, por tipo, litros e valor por produto, frete total, quantidade de canceladas.
5. **Pendências**: documentos só com resumo, canceladas no mês e lacunas (seção 8).

## 8. Fluxo
**Diário (07:00, depois a cada 1 h só para as filas com documentos pendentes):**
1. **NF-e pelo webPosto**, para as empresas dos postos desta máquina: lê `NOTAS_MANIFESTACAO` a partir do cursor; para cada chave nova, baixa o XML por `NOTAS_ENTRADA/XML/{chave}`; completa frete, placa e número do CT-e com `NOTAS_ENTRADA`; grava no acervo (4.3). Nota listada sem XML disponível fica como `so_resumo` e é tentada de novo no ciclo seguinte.
2. **CT-e e NFS-e**, para as empresas de que **este Match é dono** (4.2) e com certificado válido, com as regras da seção 4.4. Nas outras, só importa do acervo.
3. Reserva SEFAZ NF-e (se ligada): para cada `resNFe` sem ciência, envia 210210, registra o evento e o XML completo entra num ciclo seguinte.
4. Eventos de cancelamento atualizam a situação do documento.

**Mensal (dia de envio de cada escritório, 08:00), para cada empresa do escritório e competência = mês anterior:**
1. **Conferência**. Retém o pacote se houver:
   - qualquer consulta com erro nos últimos 3 dias;
   - NF-e ainda só com resumo há mais de 48 h;
   - leitura do webPosto com erro, ou sem chave webPosto e sem reserva SEFAZ ligada;
   - CT-e citado em `NOTAS_ENTRADA` (`cteNumero`) sem o XML do CT-e no acervo, como aviso e não como retenção;
   - certificado vencido ou ausente (aviso: sem CT-e e NFS-e automáticos);
   - empresa sem captura de NFS-e por estar fora do ADN e sem importação manual no mês.
   A explicação vai em português simples, com o botão "Enviar mesmo assim" (perfil administrador ou contabilidade).
2. Gera o pacote: `<CNPJ>_<AAAA-MM>.zip` com `xml/`, `pdf/` (separados ou unificado conforme o escritório) e `Resumo_<apelido>_<mm-aaaa>.xlsx`.
3. Modo **enviar**: e-mail para o escritório. Se passar de 20 MB, divide em partes numeradas, uma por e-mail. Modo **só gerar**: fica no painel para baixar e avisa o administrador.
4. Registra o envio. Um pacote já enviado só sai de novo por "Reenviar".
5. Nota que chega depois do envio (emitida no mês anterior) entra num **pacote complementar**, listado no painel e enviado no próximo ciclo diário.

## 9. Painel (novas telas)
- **Notas Fiscais**: a consulta com filtros da seção 2, totais da seleção e os botões "Baixar XML", "Baixar PDFs (separados ou unificado)" e "Exportar planilha".
- **Empresas**: cadastro; chave webPosto ("Testar conexão"); certificado ("Enviar certificado", validade); situação de cada fonte (última leitura do webPosto, último NSU, próxima consulta, último erro).
- **Escritórios**: cadastro, empresas atendidas, dia de envio, modo e formato dos PDFs.
- **Pacotes**: por mês e empresa, com situação (gerado, retido, enviado), motivo, "Aprovar e enviar", "Reenviar" e "Baixar".
- **Importar**: arrastar XML ou ZIP.

Perfil **Contabilidade**: Notas Fiscais, Pacotes (aprovar e baixar), só para as empresas do seu escopo. Não vê Postos, Coleta, Canais nem Usuários. A matriz de acesso do Match (seção 7A) ganha esta coluna.

## 10. Testes
Unitários offline:
- parser (XMLs anonimizados de NF-e de combustível com transporte, NFS-e nacional, CT-e com NF-e vinculada, evento de cancelamento);
- controle de NSU (não avança sem gravar; respeita cooldown; 656 suspende);
- conferência;
- planilha;
- divisão do e-mail;
- PDFs unificados;
- cadastro de certificado (recusa CNPJ diferente);
- migração do banco.

Também `webposto_notas` (paginação por `ultimoCodigo`, XML por chave, nota sem XML vira `so_resumo`, chave nunca logada). webPosto, SEFAZ e ADN mockados por HTTP. Nenhum documento real no repo.

## 11. Decisões minhas (o construtor pode seguir; o diretor pode mudar)
- Captura às 07:00 e retentativa de hora em hora, só onde há pendência.
- Envio no dia 5, às 08:00; competência = mês anterior.
- Pacote complementar para notas atrasadas, em vez de reenviar o pacote inteiro.
- Retenção de 5 anos para XML.
- Limite de e-mail de 20 MB por mensagem.
- Notas de saída fora do escopo.
- O .pfx cifrado com DPAPI em arquivo, e não no Credential Manager.
- A empresa pode existir sem um posto do Match (ex.: CNPJ só administrativo).

## 12. Deixado para o construtor
Layout das telas, nomes internos, biblioteca exata de DANFE/DACTE/DANFSe, estrutura do zip além da descrita, detalhes da migração e a ordem de mover o código de DF-e. Verificar `cStat` e os prazos da SEFAZ e do ADN na documentação vigente.

## 13. Decisões do diretor (23/10/2026)
- O LOGOS é o sistema principal; o Match é subproduto dele.
- Um único consultor por CNPJ para SEFAZ e ADN, e acervo fiscal compartilhado (seção 4).
- Ciência automática autorizada (usada só na reserva SEFAZ).
- NF-e vem do webPosto (sondagem de 23/10/2026); SEFAZ só como reserva.
- Captura de CT-e de frete autorizada.
- Escritórios diferentes, cada um com o seu e-mail.
- XMLs sempre separados; PDFs separados, unificados ou os dois; planilha resumo com o transporte.
