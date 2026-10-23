# MASTER-DATA-06 — Conferência visual sanitizada da conta 27173

**Data da análise:** 23/10/2026  
**Escopo:** Conta ERP `27173`, empresa `5555`, filial AP CASA CAIADA  
**Modo:** evidência local e visual; sem chamadas externas e sem escrita no ERP

## Resultado executivo

As três capturas fornecidas pelo proprietário fortalecem materialmente a associação da conta descrita no retorno oficial do ERP como `BANCO DO BRASIL (56816-3)` à filial AP CASA CAIADA.

A conferência visual confirma:

- conta ativa e marcada como conta bancária;
- descrição `BANCO DO BRASIL (56816-3)`;
- banco `001 - Banco do Brasil S.A.`;
- agência exibida como `2365`;
- número da conta exibido como `568163`, compatível com `56816-3`;
- cedente `0428493900186`, compatível com o CNPJ sanitizado `04.284.939/0001-86`;
- vínculo selecionado exclusivamente com `AP CASA CAIADA` entre as filiais visíveis.

## Confronto das fontes

| Dimensão | Retorno oficial ERP já registrado | Capturas da interface | Avaliação |
|---|---|---|---|
| Empresa | `empresaCodigo: 5555` | código não aparece | Confirmada pelo retorno ERP, não pela tela |
| Código da conta | `contaCodigo: 27173` | código não aparece | Confirmado pelo retorno ERP, não pela tela |
| Banco | descrição Banco do Brasil | `001 - Banco do Brasil S.A.` | Confirmado |
| Agência | ausente no endpoint | `2365` | Parcial; dígito `5` não aparece na tela |
| Conta | `56816-3` na descrição | `568163` e `56816-3` | Confirmado |
| Titular | ausente no endpoint | razão social não aparece | Não confirmado nominalmente pela tela |
| CNPJ | ausente no endpoint | cedente `0428493900186` | Compatível com `04.284.939/0001-86` |
| Filial | empresa `5555` no endpoint | somente AP CASA CAIADA selecionada | Forte compatibilidade por combinação de fontes |
| Situação | `ativo: true` | opção `Ativo` marcada | Confirmado |

## Integridade das evidências

As imagens não foram copiadas para o repositório porque exibem informação financeira sensível. Foram preservados apenas os hashes SHA-256 e os fatos cadastrais necessários à auditoria:

- configuração bancária: `C4013F38FCDB7056ECBAC7F1AE0374006DD3230DAF4C44F82605A701EEDC375F`;
- dados gerais: `4B72A5BF80C0DA7941C965923D0552A06F8A7B4BF0E102B1DAF879B3862F84B8`;
- filiais vinculadas: `C424F57D0BD0E792F67A57BC099D4CB44DCC39917D00BD18F399B1D42A8DEF62`.

Valores de saldo visíveis nas capturas foram deliberadamente omitidos deste registro.

## Limitações e decisão de governança

As telas não exibem diretamente `contaCodigo 27173`, `empresaCodigo 5555`, a razão social completa do titular nem o dígito da agência. A associação depende, portanto, do confronto entre o retorno oficial já registrado, a descrição idêntica da conta, o CNPJ do cedente e o vínculo exclusivo com AP CASA CAIADA.

O requisito de conferência visual solicitado pelo proprietário foi materialmente atendido. Isso não equivale a autorização para alterar dados.

- **ACCOUNT 27173:** `BLOCKED / READY_FOR_HUMAN_DECISION`
- **CASA CAIADA PILOT:** `BLOCKED`
- **Reclassificação:** não executada e não autorizada
- **Lançamento de despesa:** não executado e não autorizado
- **Escritas no ERP:** zero
- **Chamadas externas nesta etapa:** zero

## Verificação local pós-análise

Consulta SQLite aberta explicitamente em modo somente leitura confirmou que a linha `27173` permanece com `empresa_codigo = NULL`, `tipo_conta = TRANSITORIA`, `permite_debito_despesa = 0` e `ativo = 1`. Nenhuma mutação foi realizada.

