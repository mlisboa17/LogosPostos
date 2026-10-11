import assert from "node:assert/strict";
import { test } from "node:test";

globalThis.window = { location: { origin: "http://localhost" } };
const {
  contarPendenciasAbertas,
  renderListaPendencias,
  renderPaginacaoPendencias,
  renderPendencias,
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
  const htmlGerente = renderListaPendencias([
    pendencia({ id: "normal", aberta_ha_dias: 1 }),
    pendencia({ id: "vencida", vencida: true, aberta_ha_dias: 3 }),
  ], "gerente");
  assert.match(htmlGerente, /Falta sem desconto/);
  assert.match(htmlGerente, /06\/10\/2026/);
  assert.match(htmlGerente, /Aberta há<\/dt><dd>3 dias/);
  assert.match(htmlGerente, /VENCIDA/);
  assert.ok(htmlGerente.indexOf('data-pendencia="vencida"') < htmlGerente.indexOf('data-pendencia="normal"'));
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
        {
          codigo: "RECEBIMENTO_A_MAIOR", mensagem: "Sugestão: Funcionário A (7)",
          valor: "10.00", adquirente: "PREMMIA", hora: "10:01:00",
          forma: "Pix <teste>", nsu: "123456781",
        },
      ],
      historicos: [{
        codigo: "RECEBIMENTO_A_MAIOR_HISTORICO", mensagem: "Funcionário B (8)",
        valor: "20.00", adquirente: "PAGBANK", hora: "12:00:00", forma: "Pix",
        nsu: "123456782", classificacao_atual: "par provável",
      }],
    }),
  })], "auditor");
  assert.match(html, /Alertas laranja do caixa/);
  assert.match(html, /SANGRIA_ALTERADA/);
  assert.match(html, /Sangria &lt;alterada&gt;/);
  assert.match(html, /DESPESA_SEM_PLANO/);
  assert.doesNotMatch(html, /Sangria <alterada>/);
  assert.match(html, /10:01:00/);
  assert.match(html, /Pix &lt;teste&gt;/);
  assert.match(html, /NSU 123456781/);
  assert.match(html, /Sugestão: Funcionário A \(7\)/);
  assert.match(html, /Histórico: par provável \(fora do valor ativo\)/);
  assert.match(html, /12:00:00/);
});

test("filtro de vencidas é aplicado à consulta da fila", async (t) => {
  const html = renderListaPendencias([
    pendencia({ vencida: true, aberta_ha_dias: 3 }),
  ], "auditor");
  assert.match(html, /VENCIDA/);
  assert.match(html, /Aberta há<\/dt><dd>3 dias/);
  const anterior = window.location.search;
  window.location.search = "?view=pendencias&vencidas=true";
  const campos = {
    ".pendencias": null,
    "#peFiltros": { addEventListener() {} },
    "#peAtualizar": { addEventListener() {} },
    "#peLista": { addEventListener() {}, innerHTML: "" },
    "#peUnidade": { options: [], value: "" },
    "#peStatus": { value: "aberta" },
    "#peTipo": { value: "" },
    "#peVencidas": { checked: false },
    "#peErro": { classList: { add() {}, remove() {} } },
  };
  const chamadas = [];
  t.mock.method(apiClient, "get", async (url, options) => {
    chamadas.push([url, options]);
    return url.endsWith("/unidades") ? [{ empresa_codigo: 321, nome: "Unidade" }] : { items: [], total: 0 };
  });
  try {
    await renderPendencias({ innerHTML: "", querySelector: (selector) => campos[selector] }, { papel: "auditor" });
    const consulta = chamadas.find(([url]) => url === "/api/v1/cash-audit/pendencias");
    assert.equal(campos["#peVencidas"].checked, true);
    assert.equal(consulta[1].params.vencidas, true);
  } finally {
    window.location.search = anterior;
  }
});
