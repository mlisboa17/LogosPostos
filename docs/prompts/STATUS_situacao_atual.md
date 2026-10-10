# Prompt — Relatório da situação atual do sistema (somente leitura)

> Cole no agente do VS Code com o workspace em `C:\Projetos\LOGOS\LogosPostos`. Reutilizável: rode sempre que quiser um retrato atualizado.

## Regras desta tarefa

- **Não altere nenhum arquivo de código, configuração ou teste. Não faça commit, push, merge nem troca de branch.** A única escrita permitida é o relatório final (item "Entrega").
- **Não chame APIs externas** (webPosto, PagBank, Mais Pagamentos, Premmia). Use apenas o repositório, os testes locais e os arquivos já gravados em `WebPosto_API/data/` (resultados do robô noturno).
- `.env`: só verificar **presença** de variáveis por nome (`bool(os.getenv("X"))` após `load_dotenv(".env")` a partir de `WebPosto_API`). Nunca imprimir valores.
- Datas no padrão Brasil (`dd/mm/aaaa HH:mm`, fuso America/Recife). Escreva para o sócio-diretor: linguagem clara, sem jargão desnecessário.
- Se algo não puder ser confirmado, escreva "não verificado" — não presuma.

## O que levantar

1. **Código e versões**
   - Branch atual, últimos 10 commits (data dd/mm/aaaa + mensagem), alterações **não commitadas** (lista de arquivos) e se há algo **não enviado** ao GitHub (`git status -sb`, `git log origin/main..HEAD` se o remoto existir localmente).
   - Branches locais relevantes (`feature/*`, `resgate/*`) e o que cada um contém, em uma linha.
2. **Testes**
   - `cd WebPosto_API && python -m pytest tests/unit/cash_reconciliation -q -o addopts=""` e os testes de frontend existentes (ex.: `node --test tests/frontend`). Informe totais, falhas e tempo.
3. **Funcionalidades prontas** (com a versão de regra quando houver: `FECHAMENTO_*`, `CARTOES_*`, `PLACAR_*`…)
   - Para cada uma: o que faz, endpoint(s), tela/menu, e se está validada com dados reais.
   - Itens esperados: auditoria de fechamento de caixa; conciliação de recebimentos (PagBank) com atribuição a frentista; tela "Auditoria de Caixa"; robô noturno; padrão Brasil de datas; placar de metas (se já iniciado); conciliação de depósitos (parada por decisão do negócio).
4. **Integrações por unidade** — tabela: unidade (empresaCodigo) × webPosto, PagBank, Mais Pagamentos, Rede, Cielo, Premmia → `ativo` / `pendente` / `credencial inválida` / `sem acesso`, conforme `config/units.json`, variáveis presentes e o último resultado gravado pelo robô (sem chamar a API).
5. **Robô noturno**
   - Existe tarefa agendada no Windows? (`Get-ScheduledTask -TaskName "LOGOS*"` — só consultar, não registrar.) Última execução registrada em `data/cash_audit/*/noturno.log` (data/hora, unidades processadas, falhas). Dias já gravados.
6. **Segurança (ARCH01)**
   - `.env` fora do Git (`git check-ignore`), nenhuma chave em código/testes/logs (varredura por padrões `CHAVE=`, tokens; reporte só contagem e arquivo, nunca o valor), pastas com dados reais ignoradas (`data/`, `snapshots/`).
   - Lista de **pendências do negócio**: chaves a trocar (webPosto VIP e Doze, `CONSUMER_TOKEN`, `ADMIN_TOKEN`), credencial PagBank da Conveniência 24h, documentação da Mais Pagamentos, EDI da Rede, credencial Cielo. Marque o que o código consegue confirmar e o que depende de ação externa.
7. **Arquitetura**
   - Módulos em `src/modules/`, aderência ao monólito modular (dependências cruzadas entre módulos? importações do legado?), ADRs existentes, débitos técnicos conhecidos (ex.: `.pyc` versionados, `snapshots/` não ignorado, rotas sem autenticação).
8. **Próximos passos**
   - Prompts em `docs/prompts/` já executados × pendentes (CASH_AUDIT_03, CASH_AUDIT_04, COMERCIAL_01…).
   - Decisões pendentes do sócio-diretor (ex.: quebra de caixa fechado e não consolidado: vermelho ou laranja; metas de Doze e Casa Caiada).

## Entrega

1. Salve o relatório em `docs/status/SITUACAO_<aaaa-mm-dd>.md` (não commitar).
2. Responda no chat com:
   - **Resumo executivo** (5 linhas no máximo): o que funciona hoje, o que está bloqueado e por quê, e a ação mais importante.
   - Tabela de integrações por unidade.
   - Lista de pendências separada em **"depende do sistema"** e **"depende do negócio/fornecedor"**.
   - Riscos em ordem de gravidade.
