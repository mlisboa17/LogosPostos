# Prompt — SPRINT 17B.1: reforçar a barreira da importação de OFX (sem enviar nada)

Repositório `C:\Projetos\LOGOS\LogosPostos`, branch `feature/cash-audit-fechamento` (sem trocar de branch, sem merge). **Nesta sprint NADA é enviado ao webPosto** (nem teste). `.env` só via `load_dotenv`, nunca imprimir nem editar. Sem reescrever arquivos inteiros. Testes sintéticos com cliente falso. Rodar só os testes de extratos durante o trabalho; bateria completa no final. Meta: ~25 min.

## O que aconteceu no teste de 11/10/2026 (incidente)

- Envio de 507 lançamentos (conta 86188 PAGBANK DOZE FILIAL, dia 10/10/2026): resposta 201, mas a tela de conciliação do webPosto mostra **Créditos R$ 132.804,13 e Débitos R$ 0,00** — os **8 débitos (R$ 64.847,35) entraram como crédito**. O campo `"tipo": "Débito"` não foi reconhecido.
- O `.env` do diretor **não tinha** a linha `LOGOS_OFX_IMPORTACAO` e mesmo assim o envio saiu → a trava foi ligada **no próprio comando** (variável de ambiente do processo). Isso não pode acontecer.
- O anti-reenvio bloqueia pelo **hash do arquivo inteiro** → impediria importar outro dia do mesmo arquivo; e não impede reenviar o mesmo dia a partir de outro arquivo.
- A leitura de volta pela API (`MOVIMENTOS_CONTA`) **não enxerga registros OFX**; o "sucesso" foi declarado só pelo status 201.

@WebPosto_API/src/modules/cash_reconciliation/adapters/webposto_escrita_ofx.py
@WebPosto_API/src/jobs/importar_ofx.py
@WebPosto_API/tests/unit/cash_reconciliation/test_webposto_escrita_ofx.py
@docs/regras-negocio/REGRAS_DE_NEGOCIO.md

## Correções

1. **Travas só do arquivo `.env`:** ler `WEBPOSTO_WRITES` e `LOGOS_OFX_IMPORTACAO` com `dotenv_values(<caminho do WebPosto_API/.env>)` — **ignorar variáveis de ambiente do processo** para essas duas travas. Se o nome aparecer duplicado no arquivo, **recusar** com mensagem ("trava duplicada no .env, linha X e Y"). Teste: variável no ambiente = 1 e arquivo sem a linha → bloqueado.
2. **Formato do débito BLOQUEADO até confirmação:** novo parâmetro de configuração `formato_tipo_debito_confirmado` (em `units.json` ou arquivo de config do módulo, **padrão ausente**). Enquanto não estiver definido, o envio **recusa qualquer lote que contenha débito** (créditos podem seguir) com a mensagem "formato de débito não confirmado pela Quality". Deixar preparadas as variantes possíveis (`tipo` "Débito"/"D"/"DEBIT", ou `valor` negativo) selecionáveis por essa configuração — sem escolher nenhuma.
3. **Anti-reenvio por conta + dia:** registro `data/importacoes_ofx/<empresa>/historico.json` passa a bloquear **(cdConta, dia)** já enviado, qualquer que seja o arquivo; o dia **10/10/2026 da conta 86188 fica marcado como "importado com débitos errados — aguardando correção"** e bloqueado para novo envio até o diretor liberar (`--liberar-dia` com confirmação explícita, registrado no histórico).
4. **Sucesso só com conferência:** depois de um envio, a CLI mostra "ENVIADO — CONFERIR NA TELA" (e não "sucesso") com os totais esperados de **créditos e débitos separados**, e pede ao diretor para confirmar na tela de conciliação; registrar a confirmação (`--confirmar-conferencia`) no histórico.
5. **Proibição mantida:** `EXCLUIR_DIAS_SISTEMA` e `IMPORTAR_DIAS_ARQUIVO` continuam proibidos (teste existente segue passando).
6. Remover os atalhos criados fora do lugar (`WebPosto_API/adapters/` e `src/jobs/` na raiz do repositório) se nada os importar; o comando oficial é `cd WebPosto_API; python -m src.jobs.importar_ofx ...`. Testes provam que nada quebrou.
7. Atualizar RN-ERP-002 no `REGRAS_DE_NEGOCIO.md` (as 4 correções e o incidente) e o `STATUS.md` (incidente continua aberto até a Quality responder).

Testes: travas só do arquivo; trava duplicada; débito bloqueado sem confirmação; crédito-only passa na prévia; anti-reenvio por conta+dia; dia 10/10/86188 bloqueado; mensagem "conferir na tela".
Commit: `fix(extratos): reforço da barreira de OFX após o incidente de 10/10`. Depois `git push`.
