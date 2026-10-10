import assert from "node:assert/strict";
import { test } from "node:test";

globalThis.window = { location: { origin: "http://localhost" } };
const { consultarPlacar, opcoesMeses, periodoPadraoPlacar, renderPlacarResultado } = await import("../../frontend/pages/commercialScore.js");
const { apiClient } = await import("../../frontend/services/apiClient.js");

const placar = {
  posto: 11495,
  mes: "2026-10",
  dia: "2026-10-09",
  parcial: true,
  dias_mes: 31,
  dias_restantes: 23,
  frentistas_ativos: 12,
  acumulado: "57697.488",
  realizado_dia: "3815.505",
  atendimentos: 7855,
  abastecimentos: 8409,
  atendimentos_fallback: 8409,
  ticket: "7.345",
  projecao: "205146.624",
  nivel_projetado: "ouro",
  percentual_aditivado: "12.5",
  niveis: {
    bronze: { meta: "183000", percentual: "31.5", faltante: "125302.512", meta_viva: "5450", media_exigida: "5903" },
    prata: { meta: "190000", percentual: "30.4", faltante: "132302.512", meta_viva: "5754", media_exigida: "6129" },
    ouro: { meta: "198000", percentual: "29.1", faltante: "140302.512", meta_viva: "6100", media_exigida: "6387" },
  },
  diario: [{
    dia: "2026-10-09", litros: "3815.505", acumulado: "57697.488",
    atendimentos: 514, abastecimentos: 546, fechado: false,
    niveis: { bronze: { meta_viva: "5450" }, prata: { meta_viva: "5754" }, ouro: { meta_viva: "6100" } },
  }],
  frentistas: [{
    codigo: 251934, nome: "<script>alert(1)</script>", litros: "6338.624", atendimentos: 731,
    abastecimentos: 750, ticket: "8.67", meta_ticket: "8", ganho_bico: "-0.67",
    abaixo_meta: false, impacto_projetado: "300", percentual_aditivado: "10",
    ranking_ticket: 1, ranking_volume: 2,
  }],
  mix: [{ produto: 1, nome: "Gasolina comum", litros: "50000", percentual: "86.6", aditivado: false }],
  proveniencia: { versao_regra: "PLACAR_V1", executado_em: "2026-10-09T12:00:00-03:00" },
};

test("consulta placar usa posto e mês e prazo compatível com o backend", async (t) => {
  const get = t.mock.method(apiClient, "get", async () => placar);
  assert.equal(await consultarPlacar(11495, "2026-10"), placar);
  assert.deepEqual(get.mock.calls[0].arguments, [
    "/api/v1/commercial/placar",
    { params: { posto: 11495, mes: "2026-10" }, timeout: 200000 },
  ]);
});

test("modo TV envia somente o marcador de sessão de exibição", async (t) => {
  const get = t.mock.method(apiClient, "get", async () => placar);
  await consultarPlacar(11495, "2026-10", { tv: true });

  assert.deepEqual(get.mock.calls[0].arguments[1].headers, { "X-Display-Mode": "true" });
});

test("mês padrão é calculado no fuso de Recife", () => {
  assert.equal(periodoPadraoPlacar(new Date("2026-10-01T01:00:00Z")), "2026-09");
  assert.equal(periodoPadraoPlacar(new Date("2026-10-09T12:00:00Z")), "2026-10");
});

test("seletor de mês apresenta rótulos em português e valores ISO", () => {
  const options = opcoesMeses(new Date("2026-10-09T12:00:00Z"));
  assert.match(options, /value="2026-10">outubro de 2026/);
  assert.match(options, /value="2026-09">setembro de 2026/);
});

test("placar renderiza metas, realizado, tabela de frentistas e datas pt-BR com escape", () => {
  const html = renderPlacarResultado(placar);
  assert.match(html, /Meta viva/);
  assert.match(html, /Meta Bronze/);
  assert.match(html, /Acumulado até 09\/10\/2026/);
  assert.match(html, /09\/10\/2026/);
  assert.match(html, /No ritmo atual: Ouro/);
  assert.match(html, /Atendimentos distintos/);
  assert.match(html, /Ganho exigido/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /09\/10\/2026 12:00/);
});

test("sem metas mostra realizado e não fabrica níveis", () => {
  const semMetas = renderPlacarResultado({ ...placar, niveis: {}, nivel_projetado: null });
  assert.match(semMetas, /Metas não cadastradas/);
  assert.doesNotMatch(semMetas, /Meta Bronze/);
  assert.match(semMetas, /57\.697,49 L/);
});
