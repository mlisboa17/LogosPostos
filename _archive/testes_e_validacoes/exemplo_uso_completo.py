# 💻 EXEMPLOS DE CÓDIGO — Como usar seu token

**Arquivo:** `exemplo_uso_completo.py`  
**Token:** Carregado de `WEBPOSTO_CHAVE` no `.env`

---

## 🔧 Instalação

```bash
pip install httpx python-dotenv pydantic
```

---

## 📋 Arquivo `.env`

```
WEBPOSTO_BASE_URL=https://api.webposto.com.br
WEBPOSTO_CHAVE=seu_token_aqui
WEBPOSTO_API_BASE=http://localhost:8000
WEBPOSTO_USUARIO=seu-usuario
```

---

## 🚀 CÓDIGO COMPLETO

```python
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from enum import Enum

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator

# Carregar variáveis de ambiente
load_dotenv()

WEBPOSTO_BASE_URL = os.getenv("WEBPOSTO_BASE_URL", "https://api.webposto.com.br")
WEBPOSTO_CHAVE = os.getenv("WEBPOSTO_CHAVE")
WEBPOSTO_API_BASE = os.getenv("WEBPOSTO_API_BASE", "http://localhost:8000")
WEBPOSTO_USUARIO = os.getenv("WEBPOSTO_USUARIO", "sistema")

# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class TipoTitulo(str, Enum):
    RECEBER = "RECEBER"
    PAGAR = "PAGAR"


class StatusTitulo(str, Enum):
    PENDENTE = "pendente"
    PAGO = "pago"
    VENCIDO = "vencido"
    CANCELADO = "cancelado"


class TituloFinanceiro(BaseModel):
    """Modelo para um título financeiro"""

    tipo: TipoTitulo
    valor: float = Field(..., gt=0)
    data_vencimento: datetime
    descricao: str = Field(..., min_length=3, max_length=255)
    cliente_fornecedor: str = Field(..., min_length=3, max_length=255)
    categoria: str

    @validator("valor")
    def valor_positivo(cls, v):
        if v <= 0:
            raise ValueError("Valor deve ser maior que zero")
        return v


class TituloUpdate(BaseModel):
    """Modelo para atualização parcial de título"""

    valor: Optional[float] = None
    pago: Optional[bool] = None
    data_pagamento: Optional[datetime] = None
    descricao: Optional[str] = None


class ClienteFinanceiro(BaseModel):
    """Modelo para criar cliente"""

    razao_social: str
    nome_fantasia: str
    cnpj: str
    contato: str
    telefone: str
    email: str
    endereco: str
    cidade: str
    estado: str
    credito_limite: float = 0.0


class AbastecimentoCreate(BaseModel):
    """Modelo para criar abastecimento"""

    cliente_id: str
    data: datetime
    valor: float
    litros: float
    produto_id: str
    bomba: str
    combustivel: str
    placa_veiculo: str


class CaixaMovimento(BaseModel):
    """Modelo para movimento de caixa"""

    descricao: str
    valor: float
    tipo: str  # entrada ou saida
    categoria: str
    referencia: Optional[str] = None


# ============================================================================
# CLIENTE HTTP ASSÍNCRONO
# ============================================================================


class WebPostoClient:
    """Cliente para chamar a API webPosto com seu token"""

    def __init__(self, chave: str = WEBPOSTO_CHAVE, base_url: str = WEBPOSTO_BASE_URL):
        self.chave = chave
        self.base_url = base_url
        self.usuario = WEBPOSTO_USUARIO
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Fechar sessão HTTP"""
        await self.client.aclose()

    def _build_params(self, **kwargs) -> Dict[str, Any]:
        """Adicionar CHAVE automaticamente a todos os requests"""
        params = {"CHAVE": self.chave}
        params.update(kwargs)
        return params

    # ========================================================================
    # MÉTODOS GET — CONSULTAR
    # ========================================================================

    async def listar_abastecimentos(
        self,
        data_inicio: str,
        data_fim: str,
        pagina: int = 1,
        limite: int = 100,
    ) -> Dict[str, Any]:
        """
        GET /INTEGRACAO/ABASTECIMENTO

        **Exemplo:**
        ```python
        async with WebPostoClient() as client:
            resultado = await client.listar_abastecimentos(
                data_inicio="2026-05-01",
                data_fim="2026-05-08",
                pagina=1,
                limite=100
            )
            print(f"Total: {len(resultado['data'])} abastecimentos")
        ```
        """
        url = f"{self.base_url}/INTEGRACAO/ABASTECIMENTO"
        params = self._build_params(
            data_inicio=data_inicio,
            data_fim=data_fim,
            pagina=pagina,
            limite=limite,
        )
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def listar_clientes(
        self,
        pagina: int = 1,
        limite: int = 100,
    ) -> Dict[str, Any]:
        """GET /INTEGRACAO/CLIENTE"""
        url = f"{self.base_url}/INTEGRACAO/CLIENTE"
        params = self._build_params(pagina=pagina, limite=limite)
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def listar_produtos(
        self,
        pagina: int = 1,
        limite: int = 100,
    ) -> Dict[str, Any]:
        """GET /INTEGRACAO/PRODUTO"""
        url = f"{self.base_url}/INTEGRACAO/PRODUTO"
        params = self._build_params(pagina=pagina, limite=limite)
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def listar_titulos_receber(
        self,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        status: Optional[str] = None,
        pagina: int = 1,
        limite: int = 100,
    ) -> Dict[str, Any]:
        """GET /INTEGRACAO/TITULO_RECEBER"""
        url = f"{self.base_url}/INTEGRACAO/TITULO_RECEBER"
        params = self._build_params(pagina=pagina, limite=limite)
        if data_inicio:
            params["data_inicio"] = data_inicio
        if data_fim:
            params["data_fim"] = data_fim
        if status:
            params["status"] = status
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def listar_titulos_pagar(
        self,
        pagina: int = 1,
        limite: int = 100,
    ) -> Dict[str, Any]:
        """GET /INTEGRACAO/TITULO_PAGAR"""
        url = f"{self.base_url}/INTEGRACAO/TITULO_PAGAR"
        params = self._build_params(pagina=pagina, limite=limite)
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def listar_caixa(
        self,
        data_inicio: str,
        data_fim: str,
    ) -> Dict[str, Any]:
        """GET /INTEGRACAO/CAIXA"""
        url = f"{self.base_url}/INTEGRACAO/CAIXA"
        params = self._build_params(data_inicio=data_inicio, data_fim=data_fim)
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def relatorio_vendas_combustivel(
        self,
        data_inicio: str,
        data_fim: str,
    ) -> Dict[str, Any]:
        """GET /INTEGRACAO/RELATORIO/VENDA_COMBUSTIVEL"""
        url = f"{self.base_url}/INTEGRACAO/RELATORIO/VENDA_COMBUSTIVEL"
        params = self._build_params(data_inicio=data_inicio, data_fim=data_fim)
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # MÉTODOS POST — CRIAR
    # ========================================================================

    async def criar_titulo(
        self,
        titulo: TituloFinanceiro,
        motivo: str = "Criação via API",
    ) -> Dict[str, Any]:
        """
        POST /api/v1/financeiro

        **Exemplo:**
        ```python
        async with WebPostoClient() as client:
            novo_titulo = TituloFinanceiro(
                tipo=TipoTitulo.RECEBER,
                valor=5000.00,
                data_vencimento=datetime(2026, 6, 8),
                descricao="Venda de combustível",
                cliente_fornecedor="Transportadora ABC",
                categoria="Vendas"
            )
            resultado = await client.criar_titulo(novo_titulo)
            print(f"Título criado: {resultado['dados']['id']}")
        ```
        """
        url = f"{WEBPOSTO_API_BASE}/api/v1/financeiro"
        headers = {
            "Content-Type": "application/json",
            "X-Usuario": self.usuario,
            "X-Motivo": motivo,
        }
        response = await self.client.post(
            url,
            json=titulo.dict(),
            headers=headers,
        )
        response.raise_for_status()
        return response.json()

    async def criar_cliente(
        self,
        cliente: ClienteFinanceiro,
        motivo: str = "Criação via API",
    ) -> Dict[str, Any]:
        """POST /api/v1/clientes"""
        url = f"{WEBPOSTO_API_BASE}/api/v1/clientes"
        headers = {
            "Content-Type": "application/json",
            "X-Usuario": self.usuario,
            "X-Motivo": motivo,
        }
        response = await self.client.post(
            url,
            json=cliente.dict(),
            headers=headers,
        )
        response.raise_for_status()
        return response.json()

    async def criar_movimento_caixa(
        self,
        movimento: CaixaMovimento,
        motivo: str = "Criação via API",
    ) -> Dict[str, Any]:
        """POST /api/v1/caixa/movimentos"""
        url = f"{WEBPOSTO_API_BASE}/api/v1/caixa/movimentos"
        headers = {
            "Content-Type": "application/json",
            "X-Usuario": self.usuario,
            "X-Motivo": motivo,
        }
        response = await self.client.post(
            url,
            json=movimento.dict(),
            headers=headers,
        )
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # MÉTODOS PUT — ATUALIZAR
    # ========================================================================

    async def atualizar_titulo(
        self,
        titulo_id: str,
        atualizacao: TituloUpdate,
        motivo: str = "Atualização via API",
    ) -> Dict[str, Any]:
        """
        PUT /api/v1/financeiro/{titulo_id}

        **Exemplo:**
        ```python
        async with WebPostoClient() as client:
            atualizacao = TituloUpdate(
                pago=True,
                data_pagamento=datetime.now(),
                valor=5200.00
            )
            resultado = await client.atualizar_titulo("TIT_ABC123", atualizacao)
            print(f"Título atualizado: {resultado['dados']}")
        ```
        """
        url = f"{WEBPOSTO_API_BASE}/api/v1/financeiro/{titulo_id}"
        headers = {
            "Content-Type": "application/json",
            "X-Usuario": self.usuario,
            "X-Motivo": motivo,
        }
        response = await self.client.put(
            url,
            json=atualizacao.dict(exclude_none=True),
            headers=headers,
        )
        response.raise_for_status()
        return response.json()

    # ========================================================================
    # MÉTODOS DELETE — DELETAR
    # ========================================================================

    async def deletar_titulo(
        self,
        titulo_id: str,
        motivo: str = "Deleção via API",
    ) -> Dict[str, Any]:
        """
        DELETE /api/v1/financeiro/{titulo_id}

        **Exemplo:**
        ```python
        async with WebPostoClient() as client:
            resultado = await client.deletar_titulo(
                "TIT_ABC123",
                motivo="Duplicata removida"
            )
            print(f"Título deletado: {resultado['dados']['status']}")
        ```
        """
        url = f"{WEBPOSTO_API_BASE}/api/v1/financeiro/{titulo_id}"
        headers = {
            "Content-Type": "application/json",
            "X-Usuario": self.usuario,
            "X-Motivo": motivo,
        }
        response = await self.client.delete(url, headers=headers)
        response.raise_for_status()
        return response.json()


# ============================================================================
# CONTEXT MANAGER PARA USAR "async with"
# ============================================================================


class WebPostoClientContext:
    """Context manager para simplificar uso"""

    def __init__(self):
        self.client = None

    async def __aenter__(self):
        self.client = WebPostoClient()
        return self.client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.close()


# ============================================================================
# EXEMPLOS DE USO
# ============================================================================


async def exemplo_1_listar_abastecimentos():
    """Exemplo 1: Consultar abastecimentos de hoje"""
    print("\n" + "=" * 60)
    print("EXEMPLO 1: Listar Abastecimentos de Hoje")
    print("=" * 60)

    async with WebPostoClientContext() as client:
        hoje = datetime.now().strftime("%Y-%m-%d")
        resultado = await client.listar_abastecimentos(
            data_inicio=hoje,
            data_fim=hoje,
            pagina=1,
            limite=50,
        )

        print(f"\nTotal de abastecimentos: {len(resultado.get('data', []))}")
        if resultado.get("data"):
            for abastecimento in resultado["data"][:3]:  # Mostrar 3 primeiros
                print(f"  - Cliente: {abastecimento.get('cliente_id')}")
                print(f"    Valor: R$ {abastecimento.get('valor', 0):.2f}")
                print(f"    Litros: {abastecimento.get('litros', 0):.2f}")
                print()


async def exemplo_2_criar_titulo():
    """Exemplo 2: Criar novo título a receber"""
    print("\n" + "=" * 60)
    print("EXEMPLO 2: Criar Título a Receber")
    print("=" * 60)

    async with WebPostoClientContext() as client:
        # Criar título com vencimento em 30 dias
        data_vencimento = datetime.now() + timedelta(days=30)

        titulo = TituloFinanceiro(
            tipo=TipoTitulo.RECEBER,
            valor=5000.00,
            data_vencimento=data_vencimento,
            descricao="Venda de combustível - Pedido #12345",
            cliente_fornecedor="Transportadora ABC Ltda",
            categoria="Vendas",
        )

        resultado = await client.criar_titulo(
            titulo,
            motivo="Venda realizada - Pedido #12345",
        )

        if resultado.get("status") == "success":
            titulo_id = resultado["dados"]["id"]
            print(f"\n✅ Título criado com sucesso!")
            print(f"   ID: {titulo_id}")
            print(f"   Valor: R$ {resultado['dados']['valor']:.2f}")
            print(f"   Status: {resultado['dados']['status']}")
        else:
            print(f"\n❌ Erro ao criar título: {resultado}")


async def exemplo_3_atualizar_titulo():
    """Exemplo 3: Marcar título como pago"""
    print("\n" + "=" * 60)
    print("EXEMPLO 3: Atualizar Título (Marcar como Pago)")
    print("=" * 60)

    async with WebPostoClientContext() as client:
        # Buscar um título pendente
        titulos = await client.listar_titulos_receber(
            status="pendente",
            pagina=1,
            limite=1,
        )

        if titulos.get("titulos") and len(titulos["titulos"]) > 0:
            titulo_id = titulos["titulos"][0]["id"]
            print(f"\nAtualizando título: {titulo_id}")

            # Atualizar para pago
            atualizacao = TituloUpdate(
                pago=True,
                data_pagamento=datetime.now(),
            )

            resultado = await client.atualizar_titulo(
                titulo_id,
                atualizacao,
                motivo="Recebimento confirmado via transferência",
            )

            if resultado.get("status") == "success":
                print(f"\n✅ Título atualizado com sucesso!")
                print(f"   Pago: {resultado['dados'].get('pago')}")
                print(f"   Data Pagamento: {resultado['dados'].get('data_pagamento')}")
            else:
                print(f"\n❌ Erro ao atualizar: {resultado}")
        else:
            print("\n⚠️ Nenhum título pendente encontrado para atualizar")


async def exemplo_4_relatorio_vendas():
    """Exemplo 4: Gerar relatório de vendas do mês"""
    print("\n" + "=" * 60)
    print("EXEMPLO 4: Relatório de Vendas de Combustível")
    print("=" * 60)

    async with WebPostoClientContext() as client:
        # Relatório do mês atual
        hoje = datetime.now()
        primeiro_dia = hoje.replace(day=1).strftime("%Y-%m-%d")
        ultimo_dia = hoje.strftime("%Y-%m-%d")

        print(f"\nPeríodo: {primeiro_dia} a {ultimo_dia}")

        resultado = await client.relatorio_vendas_combustivel(
            data_inicio=primeiro_dia,
            data_fim=ultimo_dia,
        )

        if "vendas_por_produto" in resultado:
            total_valor = resultado.get("total_valor", 0)
            total_quantidade = resultado.get("total_quantidade", 0)

            print(f"\n📊 RESUMO DO MÊS:")
            print(f"   Total de Vendas: R$ {total_valor:,.2f}")
            print(f"   Total de Litros: {total_quantidade:,.2f}L")

            print(f"\n   Por Produto:")
            for produto in resultado["vendas_por_produto"][:5]:
                print(
                    f"   - {produto['produto']}: "
                    f"{produto['quantidade']:,.0f}L "
                    f"(R$ {produto['valor']:,.2f}) "
                    f"({produto.get('percentual', '0%')})"
                )
        else:
            print(f"\nResultado: {resultado}")


async def exemplo_5_sincronizar_dados():
    """Exemplo 5: Sincronizar dados com banco local"""
    print("\n" + "=" * 60)
    print("EXEMPLO 5: Sincronizar Dados Localmente")
    print("=" * 60)

    async with WebPostoClientContext() as client:
        print("\n1️⃣  Sincronizando clientes...")
        clientes = await client.listar_clientes(pagina=1, limite=1000)
        total_clientes = len(clientes.get("clientes", []))
        print(f"   ✅ {total_clientes} clientes sincronizados")

        print("\n2️⃣  Sincronizando produtos...")
        produtos = await client.listar_produtos(pagina=1, limite=1000)
        total_produtos = len(produtos.get("produtos", []))
        print(f"   ✅ {total_produtos} produtos sincronizados")

        print("\n3️⃣  Sincronizando abastecimentos de hoje...")
        hoje = datetime.now().strftime("%Y-%m-%d")
        abastecimentos = await client.listar_abastecimentos(
            data_inicio=hoje,
            data_fim=hoje,
            pagina=1,
            limite=1000,
        )
        total_abastecimentos = len(abastecimentos.get("data", []))
        print(f"   ✅ {total_abastecimentos} abastecimentos sincronizados")

        print(f"\n✅ Sincronização completa!")
        print(f"   Total de registros: {total_clientes + total_produtos + total_abastecimentos}")


# ============================================================================
# EXECUTAR EXEMPLOS
# ============================================================================


async def main():
    """Executar todos os exemplos"""
    print("\n" + "=" * 60)
    print("🚀 EXEMPLOS DE USO — WebPosto API")
    print("=" * 60)

    # Exemplo 1: Consultar
    await exemplo_1_listar_abastecimentos()

    # Exemplo 2: Criar
    await exemplo_2_criar_titulo()

    # Exemplo 3: Atualizar
    await exemplo_3_atualizar_titulo()

    # Exemplo 4: Relatório
    await exemplo_4_relatorio_vendas()

    # Exemplo 5: Sincronizar
    await exemplo_5_sincronizar_dados()

    print("\n" + "=" * 60)
    print("✅ Exemplos finalizados!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
```

---

## 🎯 COMO USAR ESTE ARQUIVO

### 1️⃣ Salvar como `exemplo_uso_completo.py`

```bash
cp exemplo_uso_completo.py /seu/projeto/
```

### 2️⃣ Executar um exemplo específico

```bash
# Executar tudo
python exemplo_uso_completo.py

# Ou importar em seu código
from exemplo_uso_completo import WebPostoClient

async def minha_funcao():
    async with WebPostoClient() as client:
        titulos = await client.listar_titulos_receber()
        print(titulos)
```

### 3️⃣ Estender com seus próprios métodos

```python
class MeuClienteWebPosto(WebPostoClient):
    async def listar_titulos_vencidos(self):
        """Método customizado"""
        titulos = await self.listar_titulos_receber(status="vencido")
        return titulos
```

---

## 🔍 REFERÊNCIA RÁPIDA DE MÉTODOS

| Método | HTTP | O que faz |
|--------|------|----------|
| `listar_abastecimentos()` | GET | Lista abastecimentos por período |
| `listar_clientes()` | GET | Lista todos os clientes |
| `listar_produtos()` | GET | Lista todos os produtos |
| `listar_titulos_receber()` | GET | Lista títulos a receber |
| `listar_titulos_pagar()` | GET | Lista títulos a pagar |
| `listar_caixa()` | GET | Lista movimentos de caixa |
| `relatorio_vendas_combustivel()` | GET | Gera relatório de vendas |
| `criar_titulo()` | POST | Cria novo título |
| `criar_cliente()` | POST | Cria novo cliente |
| `criar_movimento_caixa()` | POST | Cria movimento de caixa |
| `atualizar_titulo()` | PUT | Atualiza título existente |
| `deletar_titulo()` | DELETE | Deleta título (soft delete) |

---

**Pronto para começar!** 🚀
