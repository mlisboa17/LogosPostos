# ADR-006: LOGOS Vision Tunnel — agente local e HTTPS só de saída

## Status

**Proposed — 27/11/2026.** Decisões de produto desta ADR foram aprovadas pelo CTO na sessão TUN-00.1. Isso não é aceite de governança.

Não está **Accepted**. ADR-001 condiciona o efeito oficial ao registro na branch canônica de `mlisboa17/LogosPostos`. Esta cópia está em `logos-vision-pdv` porque o checkout canônico, em 27/11/2026, está em `feature/cash-audit-fechamento`, com conflitos, e não deve receber este arquivo. A sequência verificada no canônico é ADR-001 a ADR-005. ADR-006 estava livre. Não substitui `VISION-INTEGRATION-01`, que continua inexistente e não foi criado.

Relaciona-se com ADR-001 item 5, DIRECTIVE §6.4 e §7, CURRENT_ARCHITECTURE_STATE §3 e ADR-003 (ERP em leitura para este produto).

## Contexto

- `logos-vision-pdv` já é um processo à parte do monólito: lê o WebPosto, calcula nota heurística e grava evidência local. Não há túnel, câmera nem fila de vídeo.
- A empresa piloto é 118508, CONVENIENCIA_24H. PDVs autorizados: 92635 e 92801. Hardware previsto: NVR PoE e duas Intelbras VIP 3430 D IA 2,8 mm. O modelo do NVR não está confirmado. Nenhum equipamento foi acessado.
- S4.1-B permanece `PARTIAL_FIELD_EVIDENCE`. `dataHora` não tem semântica medida. A calibração 6/6 é simulação. O `--date` do worker substitui o UUID da ocorrência.
- A chave do WebPosto enxerga a rede inteira. ADR-003 mantém a escrita no ERP desligada para este fluxo.

## Problema

Investigar divergência entre o que o caixa registrou e o que aconteceu no balcão, nos dois sentidos, sem publicar câmera ou NVR na internet, sem VPN permanente e sem levar credencial de ERP ou de Gemini para a loja.

## Decisão

1. Comunicação operacional da V1: o agente da loja abre HTTPS só de saída. A central não disca para a loja. Não há VPN permanente. Tailscale, WireGuard e Cloudflare Tunnel ficam fora da V1.
2. Nenhuma porta de entrada na loja. Câmera e NVR permanecem na rede local. Quem grava é o NVR. Sobe só evidência seletiva, quando uma tarefa autorizada pedir.
3. O Edge Agent roda em dispositivo autorizado da unidade. WebPosto, a chave e o Gemini existem só na central. ERP deste produto é GET only. Zero escrita.
4. O agente não contém regra de negócio, nota de risco nem prompt de modelo. Não importa `webposto_client`, `scoring_engine` nem `vlm_auditor`.
5. Detecção híbrida é direção futura, não capacidade desta ADR. Sem evidência visual real, nada se declara validado.
6. Contratos da V1 usam consulta periódica iniciada pelo agente. WebSocket e conexão persistente ficam fora até a consulta se mostrar insuficiente.
7. `task_id` e `evidence_id` nascem uma vez e não são reemitidos por reprocessamento de data. `occurrence_id` não entra em vínculo persistente enquanto o `--date` substituir o UUID da ocorrência.
8. Organização: o agente futuro mora em `logos-vision-pdv`, sem repositório novo e sem código no monólito. Pacote previsto, não criado agora: `src/edge/`. A central continua nos módulos já existentes.

### Fronteiras

| Lado | Responsabilidade |
|---|---|
| Central | Chave WebPosto, GET, regras, autorização de tarefa, recepção, integridade, Gemini, auditor humano |
| Edge Agent | Identidade, credencial revogável, heartbeat, relógio, dispositivos autorizados, fila, consulta e validação de tarefa, recuperação futura de evidência, transferência, retry, cota de disco |
| NVR | Gravação local e entrega do trecho só na medida em que isso for comprovado no modelo real |

### Identidade

Não há relação 1:1 entre PDV e câmera. O vínculo é uma linha com vigência: empresa, PDV, NVR, canal e câmera.

| Id | Escopo | Estabilidade |
|---|---|---|
| `empresaCodigo` | Tenant no ERP. Piloto: 118508 | O código do ERP. Não é gerado pelo agente |
| `agent_id` | Uma instalação do agente | UUID na matrícula. Não muda com data |
| `device_id` | O computador do agente | O aparelho, não a câmera |
| `camera_id` | Uma câmera física | Independente do canal |
| `nvr_id` | Um gravador | Independente das câmeras |
| `channel_id` | Canal daquele NVR | Só é único junto de `nvr_id` |
| `pdvCodigo` | Caixa no ERP. Autorizados: 92635 e 92801 | O código do ERP |
| `task_id` | Uma ordem da central | UUID imutável |
| `evidence_id` | Um arquivo produzido pelo agente | UUID imutável, distinto da ocorrência |
| `occurrence_id` | Ocorrência já gravada pelo worker | Instável hoje. Proibido como chave de tarefa ou evidência até o gate abaixo |

Gate obrigatório: corrigir a substituição de UUID do `--date` antes de qualquer integração persistente entre evidência e ocorrência.

### Contratos

Nomes novos. O mapa de contextos não tinha porta para isso. Não são endpoints e não serão implementados nesta ADR. Todo contrato exige TLS com validação do certificado do servidor, identidade do agente e `empresaCodigo` igual ao da matrícula. Log sem segredo, sem URL com chave e sem corpo de credencial.

| Contrato | Direção | Efeito |
|---|---|---|
| `AGENT_ENROLLMENT` | Agente → central | Troca um segredo de matrícula, de uso único e prazo curto, pela credencial do agente |
| `AGENT_HEARTBEAT` | Agente → central | Informa relógio, fila e estado. Repetir não cria outro agente |
| `TASK_POLL` | Agente → central | Lê tarefas já autorizadas para aquele agente. Não gera tarefa |
| `TASK_ACK` | Agente → central | Confirma o recebimento da mesma `task_id` |
| `TASK_RESULT` | Agente → central | Encerra a tarefa com sucesso, falha ou expiração |
| `EVIDENCE_UPLOAD` | Agente → central | Envia o arquivo já limitado, com hash |
| `EVIDENCE_RECEIPT` | Central → agente, na resposta | Confirma o hash daquela `evidence_id` |
| `AGENT_REVOCATION` | Central, observada em qualquer resposta | Credencial morta. O agente para e não tenta de novo |

Autorização: a central só emite tarefa da empresa e dos dispositivos matriculados naquele agente. O agente só aceita `task_id` que ele mesmo recebeu no poll, de tipo presente na allowlist, nomeando `camera_id`, `nvr_id` e `channel_id` já configurados. Endereço, URL e caminho de arquivo vêm da configuração local, nunca do payload. Tarefa fora disso é rejeitada e auditada.

Estados do agente: `ENROLLING`, `ACTIVE`, `DEGRADED_CLOCK`, `OFFLINE`, `REVOKED`. Estados da tarefa: `AUTHORIZED`, `DELIVERED`, `ACKED`, `SUCCEEDED`, `FAILED`, `EXPIRED`, `CANCELLED`. Estados da evidência: `PENDING`, `UPLOADED`, `RECEIVED`, `REJECTED`.

Idempotência: matrícula repetida com o mesmo segredo devolve o mesmo `agent_id`. Heartbeat repetido não duplica sessão. Poll não tem efeito colateral. Ack, result, upload e receipt da mesma identidade são uma única linha. Upload com o mesmo `evidence_id` e hash diferente é rejeitado. Revogação repetida continua revogada.

Erro: 401 e revogação encerram. 403 não tem retry. Rede, 429 e 5xx entram em backoff com teto. Os segundos do backoff não ficam fixados aqui. Auditoria: quem matriculou, quem revogou, qual `task_id`, qual hash, qual resultado. Sem segredo no log.

Allowlist inicial de tipos de tarefa: vazia para câmera e arquivo. `EXTRACT_EVIDENCE` só pode ser acrescentado quando o NVR real tiver playback comprovado. TUN-01 não executa tarefa de dispositivo.

### Segurança

Autenticação individual por agente. Matrícula presencial ou por segredo de uso único, amarrado à empresa, entregue fora do binário. Rotação emite credencial nova e aposenta a anterior. Revogação é imediata no próximo contato. TLS valida o certificado do servidor. Não há criptografia própria.

Tarefa tem emissor, `empresaCodigo`, `agent_id`, `task_id`, tipo, prazo e nonce. Fora do prazo ou repetida, não executa. Limite de duração e de bytes é obrigatório antes de qualquer upload. Os valores numéricos esperam a medição temporal. Não se copia a janela de 15 s das regras.

Credencial do agente fica no cofre do sistema operacional, não no repositório e não no mesmo lugar da chave do ERP. A central guarda hash da credencial, não o segredo em log. Não há shell remoto. Não há comando livre.

### Implantação

1. Aceite desta ADR na branch canônica, ou recusa explícita.
2. TUN-01, ainda não autorizada a começar por este arquivo: identidade, configuração local, relógio, heartbeat local, fila mínima, estados e testes. Sem central, câmera, NVR, ERP, Gemini e vídeo.
3. Canal real só depois do TUN-01 aceito em teste.
4. Câmera e NVR só com modelo do gravador e ensaio de playback.
5. Correlação com ocorrência só depois do gate do UUID.
6. Piloto limitado a 118508 e aos PDVs 92635 e 92801.

Rollback: revogar a credencial, parar de emitir tarefa, desinstalar o agente. O NVR segue gravando. Não há escrita no ERP para desfazer.

### Critérios de aceite desta decisão

- A ADR permanece Proposed até o registro canônico.
- Nenhuma implementação nasce deste arquivo.
- O desenho não abre porta na loja, não instala VPN e não coloca chave de ERP ou Gemini no agente.
- `task_id` e `evidence_id` são independentes de `occurrence_id`.
- Regra de negócio permanece num único lugar: a central.

## Justificativa

HTTPS de saída atravessa NAT e CGNAT sem IP público e sem porta publicada. A VPN resolveria manutenção humana, não a detecção, e aproximaria as lojas umas das outras. O NVR já é o gravador. Subir o dia inteiro seria o maior custo, ainda sem taxa de bits medida. Separar central e agente evita que a chave global e o modelo saiam do controle do Vision.

## Alternativas avaliadas

- **Tailscale na V1:** adiada. Preço público em 27/11/2026: Personal US$ 0 até 6 usuários e 50 recursos etiquetados. Útil para técnico, fora do plano de evidência.
- **Cloudflare Tunnel na V1:** rejeitado. Publicar o NVR contradiz o isolamento. 1.000 túneis inclusos; excedente US$ 4,50 por túnel/mês, changelog de 16/10/2026.
- **WireGuard operado por nós:** rejeitado. Sem licença, com endpoint público e gestão de chaves. É uma VPN própria.
- **Híbrido na V1:** rejeitado. Dois planos de controle antes de uma loja.
- **Vídeo contínuo:** rejeitado como padrão. Clipe seletivo é a transferência da V1.
- **WebSocket desde já:** rejeitado. Polling iniciado pelo agente é suficiente e mais simples de revogar.

## Consequências

- O Vision continua isolado do núcleo. Um deployable de loja, quando existir, precisa desta ADR Accepted. DIRECTIVE §7 exige esse registro para extrair workload por hardware e por isolamento de falha. Esta proposta não cumpre esse registro sozinha.
- A central passa a ser a única dona de tarefa, regra, ERP e Gemini.
- O agente pode operar sem internet: a fila espera e o NVR grava. Nada disso foi ensaiado.
- Produção continua não autorizada.

## Limites

- Não prova conectividade, playback do NVR, semântica de `dataHora` nem contagem visual.
- Não define bitrate, preço de instalação nem US$ por clipe. A tarifa Gemini de entrada de vídeo foi consultada na TUN-00 e não vira orçamento aqui.
- Não cria `VISION-INTEGRATION-01`, endpoint, serviço, firewall nem código.
- Piloto só da 118508. Outra empresa é outra autorização.

## Dependências

- Aceite canônico desta ADR antes do agente ir a campo.
- S4.1-B, ou sucessora, com vendas reais, antes de fixar janela de clipe.
- Modelo do NVR e ensaio de exportação histórica antes de `EXTRACT_EVIDENCE`.
- NTP no PC, na câmera e no NVR antes de correlacionar tempo.
- Correção do UUID do `--date` antes de ligar evidência a ocorrência.
- ADR-003 permanece: este fluxo não escreve no ERP.

## Riscos

Risco de implementação, enquanto não houver loja ligada: copiar a chave para o agente, aceitar comando livre, ou gravar evidência com id que uma reexecução troca.

Risco de operação real, mesmo com o desenho seguido: tempo não medido, NVR que não devolve histórico, retenção de vídeo ainda sem política, custo mensal desconhecido, IA embarcada limitada por H.265, disco cheio e rede caída. Os dois últimos o desenho tolera. Os primeiros bloqueiam produção.

| Nível | Risco | Quando impede |
|---|---|---|
| P0 | Chave global no agente ou em log | Implementação e operação |
| P0 | Tarefa de outra empresa executada | Implementação e operação |
| P0 | Comando remoto arbitrário | Implementação e operação |
| P0 | Evidência presa a `occurrence_id` instável | Integração persistente. Não a TUN-01 |
| P0 | Retenção de vídeo indefinida | Produção. Não a TUN-01 |
| P0 | Janela temporal sem semântica de `dataHora` | Extração real. Não a TUN-01 |
| P0 | Playback do NVR não comprovado | Extração real. Não a TUN-01 |
| P1 | Custo mensal desconhecido | Escala |
| P1 | IA da câmera e H.265 | Evento local |
| P1 | Disco, rede e CPU da loja | Operação do agente em campo |

## TUN-01, fora desta ADR

Quando for autorizada, a primeira implementação contém apenas: identidade do agente, configuração local validada, saúde do relógio, heartbeat local, persistência mínima, estados, contrato de tarefa em memória ou arquivo local, e testes. Sem central real, câmera, NVR, ERP, Gemini e vídeo. Esta ADR não autoriza começar.

## Rollback

Revogar credencial, cessar tarefas, remover o agente. Gravação do NVR e dados do ERP permanecem como estavam. Não há migração para desfazer.
