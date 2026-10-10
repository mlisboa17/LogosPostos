import assert from "node:assert/strict";
import { test } from "node:test";

globalThis.window = { location: { origin: "http://localhost" } };
const {
  contarPendenciasAbertas,
  renderListaPendencias,
  renderPaginacaoPendencias,
} = await import("../../frontend/pages/pendencias.js");
const { apiClient } = await import("../../frontend/services/apiClient.js");

const pendencia = (overrides = {}) => ({
  id: "id-sintetico",
  unidade: 321,
  dia: "2026-10-06",
  tipo: "fechamento_falta_sem_desconto",
  severidade: "vermelho",
  valor: "25.50",
  referencia: "caixa:10",
  mensagem: "Falta sintética",
  status: "aberta",
  responsavel: null,
  criada_em: "2026-10-07T03:00:00-03:00",
  historico: [{
    id: 1,
    acao: "criada",
    status_anterior: null,
    status_novo: "aberta",
    usuario: "robô-noturno",
    justificativa: null,
    registrado_em: "2026-10-07T03:00:00-03:00",
  }],
  ...overrides,
});

test("fila mostra campos, histórico e ação disponível conforme papel", () => {
  const htmlGerente = renderListaPendencias([pendencia()], "gerente");
  assert.match(htmlGerente, /Falta sem desconto/);
  assert.match(htmlGerente, /06\/10\/2026/);
  assert.match(htmlGerente, /Justificar/);
  assert.match(htmlGerente, /robô-noturno/);
  assert.doesNotMatch(htmlGerente, /data-acao="aprovar"/);

  const htmlDiretor = renderListaPendencias([
    pendencia({ status: "justificada", mensagem: "<script>conteúdo</script>" }),
  ], "diretor");
  assert.match(htmlDiretor, /data-acao="aprovar"/);
  assert.match(htmlDiretor, /data-acao="recusar"/);
  assert.match(htmlDiretor, /&lt;script&gt;/);
  assert.doesNotMatch(htmlDiretor, /<script>/);
  assert.match(renderListaPendencias([
    pendencia({
      status: "justificada",
      historico: [{
        id: 2, acao: "justificada", status_novo: "justificada",
        usuario: "gerente", justificativa: "Texto anterior.",
        registrado_em: "2026-10-07T03:00:00-03:00",
      }],
    }),
  ], "gerente"), /Registrar correção/);
  assert.match(renderListaPendencias([], "auditor"), /Nenhuma pendência encontrada/);
  assert.match(renderPaginacaoPendencias(120, 50), /Página 2 de 3/);
  assert.equal(renderPaginacaoPendencias(20, 0), "");
});

test("contador consulta somente a contagem de pendências abertas", async (t) => {
  const get = t.mock.method(apiClient, "get", async () => ({ abertas: 4 }));
  assert.deepEqual(await contarPendenciasAbertas(), { abertas: 4 });
  assert.deepEqual(get.mock.calls[0].arguments, ["/api/v1/cash-audit/pendencias/contagem-abertas"]);
});

test("detalhe da pendência agrupada mostra alertas com conteúdo escapado", () => {
  const html = renderListaPendencias([pendencia({
    tipo: "caixa_alertas_laranja",
    severidade: "laranja",
    valor: "25.00",
    referencia: "caixa:106:laranja",
    mensagem: JSON.stringify({
      alertas: [
        { codigo: "SANGRIA_ALTERADA", mensagem: "Sangria <alterada>", valor: "10.00" },
        { codigo: "DESPESA_SEM_PLANO", mensagem: "Sem plano", valor: "15.00" },
      ],
    }),
  })], "auditor");
  assert.match(html, /Alertas laranja do caixa/);
  assert.match(html, /SANGRIA_ALTERADA/);
  assert.match(html, /Sangria &lt;alterada&gt;/);
  assert.match(html, /DESPESA_SEM_PLANO/);
  assert.doesNotMatch(html, /Sangria <alterada>/);
});
