import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { formatarData, formatarDataHora } from "../../frontend/utils/datas.js";

globalThis.window = { location: { origin: "http://localhost", search: "" } };
class Node {
  constructor() {
    this.innerHTML = ""; this.dataset = {}; this.style = {}; this.nodes = new Map(); this.events = {}; this.options = [];
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  querySelector(selector) {
    if (!this.nodes.has(selector)) this.nodes.set(selector, new Node());
    return this.nodes.get(selector);
  }
  querySelectorAll() { return []; }
  addEventListener(event, fn) { this.events[event] = fn; }
  appendChild(node) { this.nodes.set(`#${node.id}`, node); }
}
globalThis.document = { createElement: () => new Node() };
const source = path => readFileSync(new URL(`../../frontend/${path}`, import.meta.url), "utf8");
const brOnly = html => {
  assert.ok(html.includes("01/10/2026"));
  assert.ok(!html.includes("2026-10-01") && !html.includes("10/01/2026"));
};

for (const [page, fn, field] of [
  ["accountsPayable", "renderAccountsPayable", "vencimento"],
  ["expenses", "renderExpenses", "data"],
]) {
  test(`${page}: coluna de data renderiza dd/mm/aaaa`, async () => {
    const { [fn]: render } = await import(`../../frontend/pages/${page}.js`);
    const node = new Node();
    render(node, { data: [{ [field]: "2026-10-01", valor: "20" }] });
    brOnly(node.querySelector("#table").innerHTML);
  });
}
test("sales: venda renderiza dd/mm/aaaa", async () => {
  const { renderSales } = await import("../../frontend/pages/sales.js");
  const node = new Node();
  renderSales(node, { data: [{ data: "2026-10-01", totalVenda: "20" }] });
  brOnly(node.querySelector("#salesSubContent").querySelector("#table").innerHTML);
});
test("stock: data tecnica do arquivo usa relogio Recife, sem data americana na tabela", async () => {
  const { renderStock } = await import("../../frontend/pages/stock.js");
  const node = new Node();
  renderStock(node, { data: [{ codigo: 1, descricao: "Produto", quantidade: 2 }] });
  assert.ok(!/\d{4}-\d{2}-\d{2}/.test(node.querySelector("#table").innerHTML));
  assert.ok(source("pages/stock.js").includes("dataRecifeISO()"));
});
test("directorDashboard: dia e execucao usam BR e Recife", async () => {
  const { renderPainelDiretor } = await import("../../frontend/pages/directorDashboard.js");
  const html = renderPainelDiretor({ unidades: [], saude_robo: {
    ultima_execucao: "2026-10-02T01:00:00Z", dia_processado: "2026-10-01",
    unidades_processadas: [], unidades_com_falha: [],
  }, placar: { postos: [] } }, "auditor");
  brOnly(html);
  assert.ok(html.includes("01/10/2026 22:00"));
});
test("executiveDashboard: snapshot e origem mostram BR no fuso Recife, sem refresh", async () => {
  const { apiClient } = await import("../../frontend/services/apiClient.js");
  const { renderExecutiveDashboard } = await import("../../frontend/pages/executiveDashboard.js");
  const original = apiClient.get;
  apiClient.get = async () => ({ lastUpdated: "2026-10-02T01:00:00Z", fromSnapshot: true });
  try {
    const node = new Node();
    await renderExecutiveDashboard(node, {}, {}, { skipBackgroundRefresh: true });
    brOnly(node.querySelector("#exec-status-bar").innerHTML);
    assert.ok(node.querySelector("#exec-status-bar").innerHTML.includes("22:00"));
    let mensagem;
    globalThis.alert = text => mensagem = text;
    window._execShowAudit({ periodoInicial: "2026-10-01", periodoFinal: "2026-10-09" });
    brOnly(mensagem);
  } finally { apiClient.get = original; }
});
test("cashAudit: campos BR enviados como ISO sem consulta automatica", async () => {
  const { apiClient } = await import("../../frontend/services/apiClient.js");
  const { renderCashAudit } = await import("../../frontend/pages/cashAudit.js");
  const original = apiClient.get;
  const chamadas = [];
  apiClient.get = async (url, options) => {
    chamadas.push({ url, params: options?.params });
    return url.endsWith("/unidades") ? [] : { caixas: [], proveniencia: {}, adquirentes: [], funcionarios: [] };
  };
  try {
    const node = new Node();
    node.querySelector = function(selector) {
      if (selector === ".cash-audit") return null;
      return Node.prototype.querySelector.call(this, selector);
    };
    await renderCashAudit(node);
    assert.ok(node.innerHTML.includes('name="caInicio" type="text"'));
    assert.ok(!node.innerHTML.includes('type="date"'));
    assert.ok(node.innerHTML.includes('placeholder="mm/aaaa"') && !node.innerHTML.includes('type="month"'));
    assert.ok(source("pages/cashAudit.js").includes('lerDataBR(container.querySelector("#caInicio").value)'));
    node.querySelector("#caInicio").value = "01/10/2026";
    node.querySelector("#caFim").value = "09/10/2026";
    node.querySelector("#caMes").value = "10/2026";
    node.querySelector("#caUnidade").value = "5555";
    node.querySelector("#caFilters").events.submit({ preventDefault() {} });
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.ok(chamadas.some(c => c.params?.inicio === "2026-10-01" && c.params?.fim === "2026-10-09"));
    assert.ok(chamadas.some(c => c.params?.mes === "2026-10"));
    const antes = chamadas.length;
    node.querySelector("#caInicio").value = "31/02/2026";
    node.querySelector("#caFilters").events.submit({ preventDefault() {} });
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.equal(chamadas.length, antes);
    assert.match(node.querySelector("#caError").textContent, /inválida/);
  } finally { apiClient.get = original; }
  const { renderReincidencia } = await import("../../frontend/pages/cashAudit.js");
  brOnly(renderReincidencia({ dias_sem_dados: ["2026-10-01"], dias_sem_fechamento: ["2026-10-01"], dias_sem_recebimentos: ["2026-10-01"] }));
});
test("filtros gerais: campos BR, validacao explicita e estado ISO", async () => {
  const { renderFilters } = await import("../../frontend/components/filters.js");
  const node = new Node();
  node.querySelector = function(selector) {
    if (selector === "#empresaMultiselectHost") return null;
    return Node.prototype.querySelector.call(this, selector);
  };
  let recebido;
  renderFilters(node, { dataInicial: "2026-10-01", dataFinal: "2026-10-09" },
    value => recebido = value, null, { visibleFields: ["dataInicial", "dataFinal"] });
  assert.ok(node.innerHTML.includes('value="01/10/2026"'));
  assert.ok(!node.innerHTML.includes('type="date"'));
  node.querySelector("#dataInicial").value = "01/10/2026";
  node.querySelector("#dataFinal").value = "09/10/2026";
  const dateNode = node.querySelector("#dataInicial");
  node.querySelectorAll = selector => selector === "input:not([type=search])" ? [dateNode] : [];
  dateNode.closest = () => null;
  renderFilters(node, { dataInicial: "2026-10-01", dataFinal: "2026-10-09" },
    value => recebido = value, null, { visibleFields: ["dataInicial", "dataFinal"] });
  dateNode.events.change();
  await new Promise(resolve => setTimeout(resolve, 350));
  assert.equal(recebido.dataInicial, "2026-10-01");
  assert.equal(recebido.dataFinal, "2026-10-09");
  dateNode.value = "31/02/2026";
  dateNode.events.change();
  await new Promise(resolve => setTimeout(resolve, 350));
  assert.match(node.querySelector("[data-date-error]").textContent, /inválida/);
  assert.equal(recebido.dataInicial, "2026-10-01");
});
test("app: padrao utiliza o dia Recife, ISO apenas no estado/transporte", () => {
  const text = source("app.js");
  assert.ok(text.includes("const end = dataRecifeISO(now)") && text.includes("const startDate = somarDias(end, -5)"));
  assert.ok(!text.includes("now.toISOString().slice(0, 10)"));
  assert.equal(formatarData("2026-10-01"), "01/10/2026");
});
test("CSV/PDF: data BR e carimbo Recife", async () => {
  const { buildCsv, openPdfPreview } = await import("../../frontend/services/export.js");
  const columns = [{ key: "data", label: "Data", type: "date" }];
  brOnly(buildCsv(columns, [{ data: "2026-10-01" }]));
  let html;
  window.open = () => ({ document: { write: text => html = text, close() {} } });
  openPdfPreview("Teste", columns, [{ data: "2026-10-01" }]);
  brOnly(html);
  assert.ok(html.includes("Gerado em:") && source("services/export.js").includes("formatarDataHora(new Date())"));
});
test("snapshotService: calendario comparativo atravessa mes sem deslocar um dia", async () => {
  const { snapshotService } = await import("../../frontend/services/snapshotService.js");
  const original = globalThis.fetch;
  const urls = [];
  globalThis.fetch = async url => { urls.push(String(url)); return new Response(JSON.stringify({ data: [] }), { status: 200, headers: { "Content-Type": "application/json" } }); };
  try {
    const snapshot = await snapshotService.getSnapshot("ontem", "2026-10-01", "321");
    assert.equal(snapshot.data, "2026-09-30");
    assert.ok(urls.every(url => url.includes("dataInicial=2026-09-30")));
    assert.equal(formatarData(snapshot.data), "30/09/2026");
  } finally { globalThis.fetch = original; }
});
test("aliases antigos de format.js usam exatamente o helper unico", async () => {
  const format = await import("../../frontend/services/format.js");
  assert.equal(format.formatDate, formatarData);
  assert.equal(format.formatDateTime, formatarDataHora);
});
