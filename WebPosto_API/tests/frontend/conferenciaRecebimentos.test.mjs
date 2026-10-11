import assert from "node:assert/strict";
import { test } from "node:test";
globalThis.window = { location: { origin: "http://localhost" } };
const { renderConferencia, textoCorrecao, periodoConferencia, validarPeriodoConferencia } = await import("../../frontend/pages/conferenciaRecebimentos.js");

const item = { id: "a", grupo: 2, valor: "50", momento: "2026-10-02T10:00:00-03:00",
  adquirente: "PREMMIA", forma: "Pix", de: "PAGBANK", para: "PREMMIA Pix",
  responsavel: "Funcionário sintético (7)", regra: "RN-CARTAO-010",
  motivo: "<script>não executar</script>", evidencias: ["NSU final 1234"],
  reincidente: true, reincidencia_quantidade: 3, reincidencia_total: "163.90",
  lancamento: 1, venda: 2, caixa: 3, certeza: "Confirmar comprovante", proposta_status: "proposta" };
const total = (nome, webposto, recebido) => ({ adquirente: nome, webposto, recebido, diferenca: String(Number(recebido)-Number(webposto)) });
const dados = { unidade: 321, inicio: "2026-10-02", fim: "2026-10-02",
  conferidos: { quantidade: 2, total: "100" }, itens: [item], avisos: ["Fonte incompleta <b>"],
  formas: [{ adquirente: "PREMMIA", resumo: { forma: "Pix",
    portal: { quantidade: 1, total: "150" }, webposto: { quantidade: 1, total: "100" }, diferenca: "50" } }],
  diario: [{ dia: "2026-10-02", adquirentes: [total("PREMMIA", "100", "150"), total("PAGBANK", "150", "100")],
    diferenca: "0", compensacao: "compensacao identificada" }],
  totais_adquirentes: [total("PREMMIA", "100", "150"), total("PAGBANK", "150", "100")], diferenca_periodo: "0" };

test("quatro grupos e proposta mostram valores, frentista, regra e reincidente", () => {
  const html = renderConferencia(dados, { papel: "gerente" });
  for (const rotulo of ["LANÇAR NO WEBPOSTO", "ALTERAR NO WEBPOSTO", "APURAR", "CONFERIR À MÃO", "REINCIDENTE", "RN-CARTAO-010", "Funcionário sintético (7)", "Correções prontas"]) {
    assert.ok(html.includes(rotulo));
  }
  assert.ok(html.includes("data-decisao=\"executada pelo gerente\""));
  assert.ok(!html.includes("<script>"));
  assert.ok(html.includes("&lt;script&gt;"));
});
test("tabela diaria tem blocos webPosto/adquirente/dif e total", () => {
  const html = renderConferencia(dados);
  assert.ok(html.includes("<th>Webposto PREMMIA</th><th>PREMMIA</th><th>Dif.</th>"));
  assert.ok(html.includes("<th>Webposto PAGBANK</th><th>PAGBANK</th><th>Dif.</th>"));
  assert.ok(html.includes("Diferença do dia") && html.includes("Total do período"));
});
test("pendente nao fabrica zero e leitura nao permite marcar nada", () => {
  const html = renderConferencia({ ...dados, itens: [{ ...item, grupo: 4 }],
    totais_adquirentes: [{ adquirente: "MAIS PAGAMENTOS", diferenca: null }] },
  { papel: "diretor", somenteLeitura: true });
  assert.ok(html.includes("pendente"));
  assert.ok(!html.includes("data-decisao"));
});
test("auditor nao decide e proposta copiavel contem referencia e evidencia", () => {
  assert.ok(!renderConferencia(dados, { papel: "auditor" }).includes("data-decisao"));
  const texto = textoCorrecao(item);
  assert.ok(texto.includes("NÃO executada pelo Logos"));
  assert.ok(texto.includes("NSU final 1234") && texto.includes("venda: 2"));
});
test("periodo padrao D-2 com sete dias e recusas explicitas", () => {
  const hoje = new Date("2026-10-11T12:00:00-03:00");
  assert.deepEqual(periodoConferencia(hoje), { inicio: "2026-10-03", fim: "2026-10-09" });
  assert.deepEqual(validarPeriodoConferencia("03/10/2026", "09/10/2026", hoje), periodoConferencia(hoje));
  for (const fim of ["11/10/2026", "10/10/2026"]) assert.throws(() => validarPeriodoConferencia("05/10/2026", fim, hoje), /anteontem/);
  assert.throws(() => validarPeriodoConferencia("02/10/2026", "09/10/2026", hoje), /7 dias/);
});
test("grupo tem uma linha por pagamento e campos ausentes sem inventar dados", () => {
  const pagamento = { momento: item.momento, valor: "25", adquirente: "PREMMIA", forma: "Pix", nsu: "…1234", terminal: "…9876",
    responsaveis: [{ codigo: 7, nome: "Funcionário sintético", identificacao: "provável: sugestão", nota: 77, motivos: ["valor igual"] }],
    abastecimento: { momento: item.momento, valor: "25", bico: 2, venda_item_codigo: 9 }, forma_venda: "Dinheiro" };
  const html = renderConferencia({ ...dados, itens: [{ ...item, pagamentos: [pagamento, pagamento], tipo_inclusao: "Manualmente" }] });
  assert.equal(html.split("…9876").length - 1, 2);
  assert.ok(html.includes("nota 77") && html.includes("valor igual") && html.includes("Manualmente"));
  assert.ok(html.includes("02/10/2026 10:00") && !html.includes("2026-10-02"));
});
