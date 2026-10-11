# ADR-004: Grupos, unidades e setores (várias redes no mesmo Logos)

## Status

**Proposed — 11/10/2026** (debatido com o sócio-diretor; vira Accepted quando a primeira unidade de outro dono for cadastrada ou quando a separação por setor for implementada). Complementa o ARCH-02 (Platform Contracts), adiado pela ADR-002.

## Context

- Hoje o Logos atende **uma rede, de um dono** (Doze 74014, VIP 11495, Casa Caiada 5555, Conveniência 24h 118508), com o sócio-diretor como diretor de todas.
- O diretor informou (11/10/2026) que **outras unidades virão, de outras pessoas**: cada dono terá seus diretores, responsáveis, regras e limites.
- No **Posto VIP, um mesmo CNPJ** cobre **pista e conveniência**; a Conveniência 24h e a conveniência do VIP têm o **FOOD** como subdivisão.
- A **base oficial é o webPosto**: a separação deve usar os **centros de custo ativos** cadastrados lá. VIP (11/10/2026): `01.0.1 PISTA` (7295), `03.0.1 FECHAMENTO` (18713), `04.0.1 LOJA` (21650), `05.0.1 CONVENIÊNCIA` (22310), `09.0.1 FOOD` (24423). A API também devolve centros inativos/duplicados (PISTA_GNV, LUBRIFICANTE(S), GRUPO A, CONVENIENCIA sem acento) — devem ser ignorados.
- `03.0.1 FECHAMENTO` foi criado pelo diretor para **ajustes de notas fiscais que não são despesa real**.
- Já existe: configuração por unidade (`units.json`), login por perfil (diretor/gerente/auditor) e escopo do gerente por unidade.

## Decision

1. **Hierarquia:** `Grupo (dono) → Unidade (empresaCodigo / CNPJ) → Setor → Subdivisão`.
   - Exemplo: `Rede Marcio → Posto VIP (11495) → PISTA | CONVENIÊNCIA → FOOD`.
2. **Setor é definido por centros de custo do webPosto**, por configuração (nunca no código):
   - VIP: PISTA = {7295}; CONVENIÊNCIA = {21650, 22310} (o diretor vai unificar LOJA e CONVENIÊNCIA depois — basta trocar a configuração); FOOD = {24423}, subdivisão da CONVENIÊNCIA.
   - `FECHAMENTO` (18713) = **ajuste de NF**: fica fora de despesas e limites, exibido à parte.
   - Unidade sem separação (ex.: Doze, Casa Caiada hoje) = um setor único.
3. **Tudo que tem centro de custo é separado por setor:** despesas, vales, vendas, recebimentos, fechamento de caixa, metas (metas de litros só no setor PISTA).
4. **Cada setor tem:** responsável(is), adquirentes, limites e prazos próprios (herdando os padrões do grupo quando não definidos).
5. **Isolamento entre grupos:** cada usuário pertence a um grupo; diretor vê as unidades do seu grupo; responsável vê só a(s) sua(s) unidade(s)/setor(es). Nenhum dado, regra ou nome de funcionário atravessa grupos.
6. **Núcleo × configuração:** o que é igual para todos (casar NSU, ler Premmia/EDI, classificar recebimentos) fica no núcleo; o que muda por dono/unidade/setor (limites, prazos, responsáveis, centros, adquirentes) é configuração versionada.
7. **Regra para as próximas sprints:** não amarrar regra ao diretor atual nem a códigos de unidade no código; usar configuração.

## Consequences

- Prepara o Logos para novos donos sem refazer as regras de auditoria.
- Exige, quando implementado: campo `grupo` nas unidades e usuários, escopo por grupo no login e nas consultas, e mapa de setores por centro de custo.
- A troca de LOJA + CONVENIÊNCIA por um centro único (planejada pelo diretor) não exige código.
- Credenciais continuam por unidade no `.env` (nomes de variáveis na configuração, nunca valores).

## Alternatives considered

- **Uma instalação do Logos por dono:** isola tudo, mas multiplica manutenção e impede ganhos de escala nas regras.
- **Separar pista/conveniência por PDV:** o VIP tem dois PDVs (56764 e 54193), mas o centro de custo é a classificação oficial do webPosto e também cobre despesas e vales; PDV fica como evidência secundária.
