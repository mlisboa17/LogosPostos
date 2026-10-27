"""
Exemplo de Uso - Extração de Despesas e Fechamentos Estruturados
"""

import asyncio
from datetime import datetime
from models_auditoria import (
    DespesaCaixa, FechamentoCaixa, MovimentacaoEspecie,
    CategoriaDesapesa, StatusJustificativa, TipoCaixa,
    EspecieFinanceira, StatusCaixa
)

# ============ EXEMPLO 1: Criar uma Despesa Estruturada ============
async def exemplo_criar_despesa():
    """Exemplo: registrar despesa com validação Pydantic"""
    print("\n=== EXEMPLO 1: Criar Despesa ===")

    despesa = DespesaCaixa(
        id="exp_novo_001",
        unidade_id=1,
        caixa_tipo=TipoCaixa.PISTA,
        horario=datetime.now(),
        categoria=CategoriaDesapesa.GELO,
        valor=150.75,
        operador="João Silva",
        descricao="Gelo para refrigeração",
        status_justificativa=StatusJustificativa.JUSTIFICADA,
        documento_anexo="/docs/gelo_nota_001.pdf",
        tem_documento=True
    )

    print(f"✓ Despesa criada: {despesa.id}")
    print(f"  Valor: R$ {despesa.valor}")
    print(f"  Categoria: {despesa.categoria.value}")
    print(f"  Justificada: {despesa.tem_documento}")

# ============ EXEMPLO 2: Criar Fechamento com Movimentações ============
async def exemplo_criar_fechamento():
    """Exemplo: estruturar fechamento completo com todas as espécies"""
    print("\n=== EXEMPLO 2: Criar Fechamento Completo ===")

    movimentacoes = [
        MovimentacaoEspecie(
            especie=EspecieFinanceira.DINHEIRO,
            valor_esperado=3500.00,
            valor_informado=3490.50  # Quebra de R$ 9.50
        ),
        MovimentacaoEspecie(
            especie=EspecieFinanceira.PIX,
            valor_esperado=2200.00,
            valor_informado=2200.00  # OK
        ),
        MovimentacaoEspecie(
            especie=EspecieFinanceira.CARTAO_DEBITO,
            valor_esperado=1100.00,
            valor_informado=1100.00  # OK
        ),
        MovimentacaoEspecie(
            especie=EspecieFinanceira.CARTAO_CREDITO,
            valor_esperado=1800.00,
            valor_informado=1800.00  # OK
        ),
        MovimentacaoEspecie(
            especie=EspecieFinanceira.FROTISTA,
            valor_esperado=500.00,
            valor_informado=500.00  # OK
        ),
    ]

    fechamento = FechamentoCaixa(
        id="fech_novo_001",
        unidade_id=1,
        caixa_tipo=TipoCaixa.PISTA,
        horario_abertura=datetime(2026, 4, 12, 7, 0),
        horario_fechamento=datetime(2026, 4, 12, 23, 0),
        faturamento_bruto=9100.00,
        despesas_caixa_total=250.00,
        movimentacoes=movimentacoes,
        saldo_esperado_dinheiro=3500.00,
        saldo_informado_dinheiro=3490.50,
        status=StatusCaixa.FECHADO,
        operador_fechamento="Maria Santos"
    )

    print(f"✓ Fechamento: {fechamento.id}")
    print(f"  Faturamento: R$ {fechamento.faturamento_bruto}")
    print(f"  Despesas: R$ {fechamento.despesas_caixa_total}")
    print(f"  Quebra Total: R$ {fechamento.quebra_caixa}")
    print(f"  Status: {fechamento.status.value}")
    print("\n  Movimentações por Espécie:")
    for mov in fechamento.movimentacoes:
        print(f"    {mov.especie.value.upper()}: R$ {mov.valor_esperado} → R$ {mov.valor_informado} (Δ R$ {mov.diferenca})")

# ============ EXEMPLO 3: Validação de Integridade ============
async def exemplo_validacoes():
    """Exemplo: o que Pydantic valida automaticamente"""
    print("\n=== EXEMPLO 3: Validações Automáticas Pydantic ===")

    # Teste 1: Valor negativo
    try:
        despesa_invalida = DespesaCaixa(
            id="exp_bad_001",
            unidade_id=1,
            caixa_tipo=TipoCaixa.PISTA,
            horario=datetime.now(),
            categoria=CategoriaDesapesa.LUZ,
            valor=-50.00,  # ❌ Inválido
            operador="Test"
        )
    except ValueError as e:
        print(f"✓ Validação capturada: {e}")

    # Teste 2: Valor arredondado
    despesa_ok = DespesaCaixa(
        id="exp_ok_001",
        unidade_id=1,
        caixa_tipo=TipoCaixa.PISTA,
        horario=datetime.now(),
        categoria=CategoriaDesapesa.LUZ,
        valor=99.999,  # Será arredondado para 100.00
        operador="Test"
    )
    print(f"✓ Valor arredondado: 99.999 → {despesa_ok.valor}")

    # Teste 3: Cálculo automático de diferença
    mov = MovimentacaoEspecie(
        especie=EspecieFinanceira.DINHEIRO,
        valor_esperado=1000.00,
        valor_informado=950.00
    )
    print(f"✓ Diferença calculada: {mov.valor_esperado} - {mov.valor_informado} = R$ {mov.diferenca}")
    print(f"  Variação: {mov.variacao_percentual}%")

# ============ EXEMPLO 4: Comparativo Entre Unidades ============
async def exemplo_comparativo():
    """Exemplo: insights estoicos - comparar unidades"""
    print("\n=== EXEMPLO 4: Insights Estoicos (Comparativo) ===")

        unidades = {
        "1": {
            "faturamento": 9100.00,
            "despesas": 250.00,  # 2.75% do faturamento
        },
        "2": {
            "faturamento": 3200.00,
            "despesas": 950.00,  # 29.69% do faturamento ⚠️
        },
        "3": {
            "faturamento": 6500.00,
            "despesas": 325.00,  # 5.00% do faturamento
        },
    }

    media_despesas = sum(u["despesas"] / u["faturamento"] * 100 for u in unidades.values()) / len(unidades)
    print(f"Média histórica de despesas: {media_despesas:.2f}%")
    print(f"Padrão esperado: 5.00%\n")

    for unidade, dados in unidades.items():
        pct = (dados["despesas"] / dados["faturamento"]) * 100
        desvio = pct - 5.0
        emoji = "⚠️" if abs(desvio) > 10 else "✓"

        print(f"{emoji} {unidade.upper()}")
        print(f"   Faturamento: R$ {dados['faturamento']:.2f}")
        print(f"   Despesas: R$ {dados['despesas']:.2f} ({pct:.2f}%)")
        print(f"   Desvio: {desvio:+.2f}%")

# ============ MAIN ============
async def main():
    print("╔════════════════════════════════════════════════════════╗")
    print("║  LOGOS AUDITORIA - Exemplos de Estruturação de Dados  ║")
    print("╚════════════════════════════════════════════════════════╝")

    await exemplo_criar_despesa()
    await exemplo_criar_fechamento()
    await exemplo_validacoes()
    await exemplo_comparativo()

    print("\n" + "="*60)
    print("Próximas etapas:")
    print("1. Integrar com API webPosto real")
    print("2. Criar banco de dados para persistência")
    print("3. Implementar dashboard React/Tailwind")
    print("4. Conectar Logos Eye para monitoramento em tempo real")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
