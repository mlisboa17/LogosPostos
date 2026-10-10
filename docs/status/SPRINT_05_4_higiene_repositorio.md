# Sprint 5.4 — Higiene do repositório

- Removidos do índice Git 15 arquivos Python compilados (`.pyc`) com
  `git rm -r --cached`; os arquivos locais foram mantidos no disco.
- Reforçadas as regras do `.gitignore` para bytecode e diretórios
  `__pycache__` em qualquer nível.
- Preservados os 28 snapshots já versionados; nenhum foi removido ou alterado
  nesta sprint.
- Validação final: 158 testes backend e 25 testes frontend aprovados; `git
  diff --check` sem erros. Tela de Pendências conferida no navegador com
  usuário temporário, sem criar pendências ou alterar dados operacionais.
- Nenhum push, merge ou troca de branch.
