# Runbook Operacional: Auditoria e Saneamento de Segredos (ARCH-01)

## 1. Objetivo

Orientar a identificação, classificação, contenção, rotação quando necessária e eventual remoção histórica de arquivos `.env` ou outros segredos rastreados no Git, sem expor valores durante a auditoria.

## 2. Quando usar

Use este runbook quando um arquivo sensível tiver sido rastreado, quando secret scanning emitir alerta ou quando houver dúvida sobre a presença histórica de credenciais.

## 3. Pré-requisitos e responsáveis

- Acesso local seguro ao repositório e aos provedores relacionados.
- Responsável técnico capaz de validar a operação após uma troca de credencial.
- Owner de cada segredo capaz de confirmar status, escopo e revogação.
- Coordenação com administradores do repositório antes de reescrever histórico.
- Canal seguro para evidências; nunca registrar valores de segredos em issues, chats, logs ou documentação.

## 4. Princípios obrigatórios

- **Não imprimir valores:** comandos e evidências devem expor apenas nomes, caminhos, fingerprints seguros ou status.
- **Conter antes de investigar em profundidade:** se houver indício de credencial ativa exposta, reduzir o risco imediatamente.
- **Não concluir prematuramente:** presença no Git não prova uso indevido; revogação alegada não substitui evidência.
- **Rotação proporcional:** não recomendar rotação de segredo comprovadamente revogado/inativo. Registrar a evidência e avaliar risco residual.
- **Reescrita coordenada:** `git-filter-repo` altera hashes e afeta clones, forks, branches, tags, PRs e CI/CD.

## 5. Matriz de severidade

| Nível | Classificação | Critério | Ação mínima |
|---|---|---|---|
| **P0** | Segredo real ativo exposto | Credencial válida ou plausivelmente válida em commit com alcance remoto, especialmente produção/homologação. | Conter e rotacionar imediatamente; revogar a antiga; avaliar acesso indevido; decidir expurgo histórico com urgência. |
| **P1** | Segredo histórico com status não confirmado ou risco residual | Material sensível no histórico cuja validade, revogação, alcance ou possibilidade de abuso não foi comprovada; inclui credencial inativa quando ainda existe risco residual verificável. | Confirmar status e alcance; rotacionar somente se ainda válida ou se a revogação não puder ser demonstrada; decidir expurgo após análise de risco e impacto. |
| **P2** | Falha de governança sem segredo real | Arquivo rastreado contendo apenas placeholders, valores locais não sensíveis ou exemplos comprovados. | Remover do índice, reforçar `.gitignore` e salvaguardas; sem rotação. |

> Uma credencial comprovadamente revogada/inativa, sem risco residual material, não exige rotação. Ainda pode exigir correção de governança e, conforme a exposição, decisão sobre preservação ou saneamento do histórico.

## 6. Procedimento

### 6.1. Identificar rastreamento sem mostrar valores

```bash
git ls-files | grep -E '(^|/)\.env($|\.)'
git log --all --name-only --oneline -- '.env' '*/.env' '.env.*' '*/.env.*'
```

Em PowerShell, para a árvore atual:

```powershell
git ls-files | Select-String -Pattern '(^|/)\.env($|\.)'
```

Registre apenas caminhos, commits e referências. Não copie o conteúdo para o chamado.

### 6.2. Classificar localmente

Inspecione somente os nomes das variáveis em ambiente seguro. Para arquivos simples no formato `CHAVE=valor`:

```bash
sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p' .env | sort -u
```

Classifique os tipos envolvidos, por exemplo: banco de dados, nuvem/storage, pagamentos, integrações legadas, criptografia, JWT ou tokens. Evite comandos que possam imprimir linhas completas em caso de formato inesperado.

### 6.3. Confirmar status e alcance

Para cada item, registre sem o valor:

1. tipo e owner;
2. ambiente e permissões;
3. primeira e última referência no Git;
4. presença em remoto, fork, mirror, artefato ou log;
5. status no provedor: ativo, revogado, expirado ou não confirmado;
6. evidência de revogação/expiração;
7. sinais de uso indevido, quando disponíveis.

### 6.4. Conter e rotacionar

- **P0:** emitir nova credencial, atualizar o runtime/cofre, validar a operação e revogar a antiga. Se possível, restrinja ou revogue a credencial antiga antes da análise completa.
- **P1:** confirmar o estado primeiro. Rotacionar se estiver válida, se a revogação não puder ser comprovada ou se o risco residual justificar a troca.
- **P2:** não rotacionar; corrigir rastreamento e prevenção.

### 6.5. Remover o rastreamento atual

Exemplo para um `.env` na raiz, após confirmar o caminho correto:

```bash
git rm --cached -- .env
```

Atualize o `.gitignore` por revisão normal para cobrir `.env`, variantes locais e permitir somente exemplos sanitizados. Confirme:

```bash
git status
git check-ignore -v .env
```

Não apague a cópia local necessária ao runtime sem planejar sua substituição segura.

### 6.6. Decidir sobre saneamento histórico

`git-filter-repo` não é automático para todo incidente:

- **P0:** uso obrigatório quando a remoção histórica for tecnicamente justificável e aprovada como parte da resposta. A rotação/revogação continua sendo a contenção principal; reescrever o Git não invalida um segredo copiado.
- **P1:** usar somente após análise documentada de risco e impacto.
- **P2:** em regra, não reescrever; exceções exigem justificativa.

Antes da decisão, avaliar:

- exposição pública ou privada e tempo de exposição;
- forks, mirrors, caches, clones e artefatos;
- branches protegidos, tags, releases e pull requests;
- integrações, pipelines e referências por hash;
- quantidade de colaboradores e plano de reclone;
- exigências legais, contratuais ou de retenção;
- benefício real do expurgo após revogação.

### 6.7. Executar `git-filter-repo`, se aprovado

Somente após backup verificável, janela coordenada e plano de comunicação. Exemplo a adaptar ao caminho confirmado:

```bash
git filter-repo --invert-paths --path .env --force
git log --all --name-only --oneline -- '.env' '*/.env'
```

Depois, um administrador deve coordenar a atualização do remoto, proteção temporária contra pushes antigos, tratamento de forks/mirrors e reclone dos colaboradores. Nunca force o push sem aprovação explícita do owner do repositório.

### 6.8. Salvaguardas

1. Secret scanning no provedor Git.
2. Scanner em pre-commit/CI, como `gitleaks` ou `detect-secrets`, após escolha da equipe.
3. `.env.example` sanitizado, sem valores reais.
4. Segredos injetados por cofre, plataforma ou variáveis de ambiente protegidas.
5. Revisão periódica de permissões e expiração.

## 7. Validação e encerramento

- Serviços locais, homologação e produção operam com as credenciais corretas.
- Credenciais substituídas foram formalmente revogadas.
- O arquivo sensível não está mais rastreado na árvore atual.
- Scanners e `.gitignore` estão ativos.
- Se houve reescrita, remoto, branches, tags, forks conhecidos e CI/CD foram verificados.
- O incidente foi registrado sem valores sensíveis.

## 8. Rollback e recuperação

- Para troca de credencial, mantenha um plano de rollback que não reative a credencial exposta. Prefira corrigir a configuração da nova credencial ou emitir outra.
- Para reescrita de histórico, preserve backup offline e referência do estado anterior pelo período aprovado. Restaurar o histórico antigo no remoto pode reintroduzir o material sensível e exige nova decisão do responsável de segurança.
- Se a operação ficar indisponível, acione o owner do serviço e o responsável de segurança; não publique valores em canais de incidente.

## 9. Registro de evidência

- **Data/hora:** [AAAA-MM-DD HH:MM fuso]
- **Responsável:** [nome/função]
- **Repositório e referências:** [sem URLs sensíveis]
- **Classificação final:** [P0/P1/P2]
- **Tipos auditados:** [sem valores]
- **Status no provedor e evidência:** [ativo/revogado/expirado/não confirmado]
- **Rotação/revogação:** [ação e horário, sem valor]
- **Decisão sobre histórico:** [realizada/não realizada e justificativa]
- **Impactos coordenados:** [forks, CI, clones, tags]
- **Validação operacional:** [resultado e horário]
- **Ações preventivas:** [scanner, ignore, cofre, owners]
