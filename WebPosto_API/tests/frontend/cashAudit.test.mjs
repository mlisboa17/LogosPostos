import assert from "node:assert/strict";
import { test } from "node:test";

globalThis.window = { location: { origin: "http://localhost" } };
const { diasDoPeriodo, rankingFrentistas, renderRecebimentos, periodoPadrao } = await import("../../frontend/pages/cashAudit.js");
const { formatDate, formatTime, formatDateTime, recifeDateISO } = await import("../../frontend/services/format.js");

const candidato = (frentista) => ({
  abastecimento: { frentista }, pontos: 80,
  motivos: ["valor igual", "<script>nao executar</script>"],
});
const investigacao = (atribuicao, frentista, candidatos) => ({
  atribuicao, frentista, candidatos,
  transacao: { momento: "2026-01-02T10:00:00", valor: "10.15", bandeira: "PIX" },
});
const atribuido = investigacao("atribuido", 7, [candidato(7)]);
const sugestao = investigacao("sugestao", null, [candidato(8), candidato(8), candidato(9)]);
const dia = {
  dia: "2026-01-02",
  adquirentes: [{
    adquirente: "PAGBANK", situacao: "ok", casados: { quantidade: 2, total: "20.30" },
    a_maior: [atribuido], a_menor: [{ valor: "5", momento: "2026-01-02T12:00:00", administradora: "PIX" }],
    pares_provaveis: [{ investigacao: sugestao, cartao: { momento: "2026-01-02T15:00:00", valor: "10.15" } }],
    proveniencia: { versao_regra: "CARTOES_V1", executado_em: "2026-01-03T03:00:00" },
  }],
};

test("periodo inclusivo ate 31 dias e rejeicao de datas invalidas", () => {
  assert.equal(diasDoPeriodo("2026-01-01", "2026-01-31").length, 31);
  assert.deepEqual(diasDoPeriodo("2026-01-02", "2026-01-02"), ["2026-01-02"]);
  for (const datas of [["2026-01-01", "2026-02-01"], ["2026-01-03", "2026-01-02"],
    ["invalido", "2026-01-02"], ["2026-02-30", "2026-03-03"]]) {
    assert.throws(() => diasDoPeriodo(...datas), /período/);
  }
});

test("ranking separa atribuidos e sugestoes e deduplica candidatos por recebimento", () => {
  assert.deepEqual(rankingFrentistas([dia]), [
    { frentista: 7, atribuidos: 1, sugestoes: 0 },
    { frentista: 8, atribuidos: 0, sugestoes: 1 },
    { frentista: 9, atribuidos: 0, sugestoes: 1 },
  ]);
});

test("pendencias e credenciais invalidas nao exibem KPIs ficticios", () => {
  const html = renderRecebimentos([{
    dia: "2026-01-02", adquirentes: [
      { adquirente: "MAIS_PAGAMENTOS", situacao: "pendente" },
      { adquirente: "PAGBANK", situacao: "credencial inválida", erro: "credencial inválida" },
    ],
  }]);
  assert.match(html, /pendente/);
  assert.match(html, /credencial inválida/);
  assert.doesNotMatch(html, /class="ca-kpi/);
  assert.match(html, /Nenhum dado estimado/);
});

test("divergencias tem cores, motivos escapados, proveniencia e alerta de periodo parcial", () => {
  const html = renderRecebimentos([dia], ["03/01/2026: timeout"]);
  for (const tom of ["vermelho", "laranja", "amarelo"]) assert.match(html, new RegExp(`ca-row--${tom}`));
  assert.match(html, /Frentista #7 · atribuído/);
  assert.match(html, /Sugestão \(3 candidatos\)/);
  assert.match(html, /CARTOES_V1/);
  assert.match(html, /Totais e ranking são parciais/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
  assert.doesNotMatch(html, /2026-01-\d{2}/);
  assert.match(html, /02\/01\/2026/);
  assert.match(html, /10:00/);
  assert.doesNotMatch(html, /10:00:00/);
});

test("datas e horas sempre Recife independente do fuso do navegador", () => {
  assert.equal(formatDateTime("2026-10-08T01:00:00Z"), "07/10/2026 22:00");
  assert.equal(formatTime("2026-10-05T03:28:48Z"), "00:28");
  assert.equal(formatDate("2026-10-05"), "05/10/2026");
  assert.equal(formatDateTime("2026-10-07T14:05:00"), "07/10/2026 14:05");
  assert.equal(recifeDateISO(new Date("2026-10-08T01:00:00Z")), "2026-10-07");
  assert.deepEqual(periodoPadrao(new Date("2026-10-08T01:00:00Z")), {
    inicio: "2026-10-01", fim: "2026-10-07",
  });
});
