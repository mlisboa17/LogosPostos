# 🔧 fix(models): Pydantic validators set computed fields correctly

## 📋 Descrição

Corrige validators em `models_auditoria.py` para que campos computados sejam aplicados corretamente durante inicialização do modelo Pydantic v2.

---

## ❌ Problema

Validators para campos calculados não eram aplicados durante `__init__`:
- `MovimentacaoEspecie.diferenca` retornava `0` em vez do valor calculado
- `MovimentacaoEspecie.variacao_percentual` retornava `0` em vez do valor calculado
- `FechamentoCaixa.quebra_caixa` retornava `0` em vez do valor calculado
- Warnings: _"A custom validator is returning a value other than `self`. Returning anything other than `self` from a top level model validator isn't supported when validating via `__init__`"_

---

## ✅ Solução

Alterar padrão de validators para usar `object.__setattr__` e retornar `self`:

```python
@model_validator(mode="after")
def calcular_diferenca_e_variacao(self) -> Self:
    diferenca = round(self.valor_esperado - self.valor_informado, 2)
    variacao = 0.0
    if self.valor_esperado > 0:
        variacao = round((diferenca / self.valor_esperado) * 100, 2)
    # Atualiza os atributos no próprio objeto e retorna self
    object.__setattr__(self, "diferenca", diferenca)
    object.__setattr__(self, "variacao_percentual", variacao)
    return self
```

Garante compatibilidade com Pydantic v2 durante inicialização.

---

## 🧪 Testes

| Teste | Status | Detalhes |
|-------|--------|---------|
| Unitários (`test_auditoria.py`) | ✅ 17/17 PASSED | Todos os cenários cobertos |
| Integração (API real) | ✅ 6/6 PASSED | Chave WebPosto validada |
| Linting (`ruff`) | ⚠️ 21 warnings | Arquivos com sintaxe inválida (não corrigíveis) |
| Formatação (`black`) | ✅ 64 arquivos | Código reformatado com sucesso |

### Como rodar testes localmente

```bash
# Unitários
pytest test_auditoria.py -v

# Integração (requer .env com WEBPOSTO_CHAVE válida)
pytest WebPosto_API/tests/integration/test_api_real.py -q

# Cobertura
pytest --cov
```

---

## 📝 Arquivos Alterados

| Arquivo | Tipo | Mudança |
|---------|------|--------|
| `models_auditoria.py` | Modificado | Corrigir 2 validators (MovimentacaoEspecie, FechamentoCaixa) |
| `CHANGELOG.md` | Novo | Entrada de changelog para v2026-05-08 |
| Vários | Formatado | `black` + `ruff --fix` aplicados |

---

## 🔍 Impacto

- **Escopo**: Correção de lógica em 2 modelos de domínio
- **Quebra de compatibilidade**: Não (apenas correção de bug)
- **Performance**: Nenhuma mudança
- **Cobertura de testes**: 100% dos validators afetados

---

## ✨ Validação Local

```bash
# 1. Clonar e fazer checkout da branch
git checkout fix/pydantic-validators

# 2. Rodar testes
pytest test_auditoria.py -v

# 3. Resultado esperado
# ✅ 17 passed
```

---

## 📌 Checklist de Merge

- [x] Testes passando localmente
- [x] Integração com API real validada
- [x] Código formatado (black)
- [x] Linting aplicado (ruff)
- [x] Changelog atualizado
- [x] Sem warnings críticos

---

**Branch**: `fix/pydantic-validators`  
**Tipo**: Bug fix  
**Data**: 2026-05-08  
**Autor**: mlisboa17
