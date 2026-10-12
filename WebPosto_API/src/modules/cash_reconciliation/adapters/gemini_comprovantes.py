"""Adaptador para extração de comprovantes e áudios via Google Gemini API."""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

import httpx

from ..domain.comprovante import DadosComprovante

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
MODELO_PADRAO = "gemini-2.5-flash"
MODELO_FALLBACK = "gemini-1.5-flash"

PROMPT_COMPROVANTE = """Você é um especialista em extração de comprovantes bancários brasileiros (PIX, TED, Boleto, Guia/Imposto).
Analise o documento anexo (imagem ou PDF) e extraia estritamente os campos com máxima precisão.

Campos a extrair:
- "valor": número decimal com o valor total pago em reais (ex: 650.00 ou 1850.50). Se não encontrar, retorne null.
- "data": data da realização do pagamento no formato YYYY-MM-DD (ex: "2026-09-17"). Se não encontrar, retorne null.
- "favorecido": nome completo da pessoa física ou razão social/nome fantasia da empresa que recebeu o pagamento.
- "cpf_cnpj": CPF ou CNPJ do favorecido/recebedor se visível.
- "chave_pix": chave PIX utilizada se constar no comprovante.
- "banco_origem": nome do banco de onde partiu o pagamento (ex: "PagBank", "Banco do Brasil", "Bradesco", "Itaú").
- "conta_origem": agência/conta do pagador se visível (ex: "9048-8").
- "descricao": descrição/mensagem/identificador informada no pagamento.
- "tipo_comprovante": "PIX", "Boleto", "TED", "Imposto" ou "Outros".

Regras obrigatórias:
1. NUNCA invente nem deduza dados que não estejam visíveis no documento.
2. Campos ilegíveis ou ausentes devem ser null ou vazios "".
3. Responda EXCLUSIVAMENTE em formato JSON compatível.
"""

PROMPT_AUDIO = """Você é um assistente financeiro de uma rede de postos de combustíveis.
Ouça o áudio gravado pelo diretor e extraia os detalhes da despesa informada.

Campos a extrair:
- "transcricao": transcrição fidedigna do que foi falado no áudio.
- "valor": valor numérico mencionado em reais (ex: 350.00), ou null se não falado.
- "favorecido": nome da pessoa ou fornecedor mencionado (ex: "Seu Antônio pedreiro", "Karleal"), ou vazio se não falado.
- "palavras_chave": lista de termos contábeis ou de contexto mencionados (ex: ["pedreiro", "piso", "pista"]).
- "contexto": breve resumo do serviço ou compra (ex: "piso da pista").

Responda EXCLUSIVAMENTE em formato JSON compatível.
"""


def _parse_data_segura(val: Any) -> date | None:
    if not val or not isinstance(val, str):
        return None
    val = val.strip()
    # YYYY-MM-DD
    m1 = re.match(r"^(\d{4})-(\d{2})-(\d{2})", val)
    if m1:
        try:
            return date(int(m1.group(1)), int(m1.group(2)), int(m1.group(3)))
        except ValueError:
            pass
    # DD/MM/YYYY
    m2 = re.match(r"^(\d{2})/(\d{2})/(\d{4})", val)
    if m2:
        try:
            return date(int(m2.group(3)), int(m2.group(2)), int(m2.group(1)))
        except ValueError:
            pass
    return None


def _parse_valor_seguro(val: Any) -> Decimal | None:
    if val is None or val == "":
        return None
    try:
        if isinstance(val, (int, float)):
            return Decimal(str(val))
        s = str(val).strip().replace("R$", "").replace(" ", "")
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        return Decimal(s)
    except Exception:
        return None


class GeminiExtractor:
    """Cliente para extração de dados via Gemini, com suporte a mock para testes."""

    def __init__(
        self,
        api_key: str | None = None,
        modelo: str = MODELO_PADRAO,
        mock_fn: Callable[[bytes, str, str], dict[str, Any]] | None = None,
    ):
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        self.modelo = modelo
        self.mock_fn = mock_fn

    async def extrair_comprovante(
        self,
        conteudo_bytes: bytes,
        mime_type: str,
        texto_adicional: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> DadosComprovante:
        """Extrai dados estruturados de imagem ou PDF de comprovante."""
        if self.mock_fn is not None:
            raw = self.mock_fn(conteudo_bytes, mime_type, texto_adicional)
            return self._normalizar_dados_comprovante(raw, observacao=texto_adicional)

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY não configurada no ambiente (.env).")

        prompt = PROMPT_COMPROVANTE
        if texto_adicional:
            prompt += f"\nObservação adicional enviada pelo diretor: '{texto_adicional}'."

        raw = await self._chamar_gemini(
            conteudo_bytes=conteudo_bytes,
            mime_type=mime_type,
            prompt=prompt,
            client=client,
        )
        return self._normalizar_dados_comprovante(raw, observacao=texto_adicional)

    async def extrair_audio(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/ogg",
        client: httpx.AsyncClient | None = None,
    ) -> tuple[str, DadosComprovante]:
        """Extrai transcrição e entidades a partir de áudio."""
        if self.mock_fn is not None:
            raw = self.mock_fn(audio_bytes, mime_type, "")
            transcricao = str(raw.get("transcricao") or "")
            dados = self._normalizar_dados_comprovante(raw, observacao=transcricao)
            return transcricao, dados

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY não configurada no ambiente (.env).")

        raw = await self._chamar_gemini(
            conteudo_bytes=audio_bytes,
            mime_type=mime_type,
            prompt=PROMPT_AUDIO,
            client=client,
        )
        transcricao = str(raw.get("transcricao") or "")
        dados = self._normalizar_dados_comprovante(raw, observacao=transcricao)
        return transcricao, dados

    async def _chamar_gemini(
        self,
        conteudo_bytes: bytes,
        mime_type: str,
        prompt: str,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        """Executa a chamada HTTP à API REST do Google Gemini com geração JSON."""
        b64_data = base64.b64encode(conteudo_bytes).decode("ascii")
        url = f"{GEMINI_API_BASE}/{self.modelo}:generateContent?key={self.api_key}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": b64_data,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        proprio_cliente = client is None
        http = client or httpx.AsyncClient(timeout=45.0)
        try:
            resp = await http.post(url, json=payload)
            if resp.status_code == 404 and self.modelo != MODELO_FALLBACK:
                # Tenta fallback para gemini-1.5-flash se 2.5 não estiver liberado
                url_fb = f"{GEMINI_API_BASE}/{MODELO_FALLBACK}:generateContent?key={self.api_key}"
                resp = await http.post(url_fb, json=payload)

            resp.raise_for_status()
            data = resp.json()
            cand = data.get("candidates", [{}])[0]
            part = cand.get("content", {}).get("parts", [{}])[0]
            txt = part.get("text", "{}")

            # Limpa possíveis blocos ```json ... ```
            txt = re.sub(r"^```(?:json)?\s*", "", txt.strip(), flags=re.IGNORECASE)
            txt = re.sub(r"\s*```$", "", txt.strip())
            return json.loads(txt)
        except Exception as exc:
            logger.error("Falha ao consultar Gemini: %s", exc)
            raise
        finally:
            if proprio_cliente:
                await http.aclose()

    def _normalizar_dados_comprovante(
        self,
        raw: dict[str, Any],
        observacao: str = "",
    ) -> DadosComprovante:
        """Converte dicionário cru em DadosComprovante validado e tipado."""
        v = _parse_valor_seguro(raw.get("valor"))
        d = _parse_data_segura(raw.get("data"))

        # Monta observação combinando contexto/palavras-chave se presentes
        obs = observacao
        if not obs and raw.get("contexto"):
            obs = str(raw["contexto"])

        return DadosComprovante(
            valor=v,
            data=d,
            data_hora_str=str(raw.get("data") or ""),
            favorecido=str(raw.get("favorecido") or "").strip(),
            cpf_cnpj=str(raw.get("cpf_cnpj") or "").strip(),
            chave_pix=str(raw.get("chave_pix") or "").strip(),
            banco_origem=str(raw.get("banco_origem") or "").strip(),
            conta_origem=str(raw.get("conta_origem") or "").strip(),
            descricao=str(raw.get("descricao") or "").strip(),
            tipo_comprovante=str(raw.get("tipo_comprovante") or "").strip() or "PIX",
            observacao_diretor=obs,
        )
