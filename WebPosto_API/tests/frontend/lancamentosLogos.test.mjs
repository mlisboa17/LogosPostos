import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

globalThis.window = { location: { origin: "http://localhost" } };
const { renderLancamentos, renderLancamentosLogos } = await import("../../frontend/pages/lancamentosLogos.js");
const { apiClient } = await import("../../frontend/services/apiClient.js");
const URL = "/api/v1/cash-audit/lancamentos-logos";
const proposta = {
  id: "proposta/1", unidade: 74014, dia: "2026-10-14", nsu_final: "1234",
  texto: "Texto do backend\n<script>teste</script>", elegivel: true, motivo: null,
  valor: "42.10", caixa: "9", frentista: "Frentista sintético", evidencias: ["<b>comprovante</b>"],
};
const historico = {
  acao_id: "acao/1", estado: "confirmado", instante: "2026-10-15T10:00:00-03:00",
  valor: "42.10", caixa: "9", frentista: "Frentista sintético", texto: proposta.texto,
  evidencias: proposta.evidencias, id_criado: 123,
};
const dados = {
  propostas: [proposta, { ...proposta, id: "bloqueada", elegivel: false, motivo: "Sem lastro <b>" }],
  historico: [historico, { ...historico, acao_id: "recusada", estado: "recusado", id_criado: null }],
};

function node() {
  return {
    innerHTML: "", textContent: "", disabled: false, listeners: {}, attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; },
    addEventListener(name, handler) { this.listeners[name] = handler; },
    querySelectorAll() { return []; },
  };
}
function fixture() {
  const form = node(), result = node(), message = node(), submit = node();
  form.elements = { unidade: { value: "74014" }, dia: { value: "14/10/2026" } };
  const container = node();
  const controls = [submit, ...Object.values(form.elements)];
  container.querySelector = selector => ({ form, ".ll-result": result, ".ll-message": message })[selector];
  container.querySelectorAll = () => controls;
  const click = (acao, id) => {
    const button = { disabled: false, dataset: { acao, id } };
    controls.push(button);
    return result.listeners.click({ target: { closest: () => button } });
  };
  const consultar = () => form.listeners.submit({ preventDefault() {} });
  return { container, form, result, message, click, consultar, controls };
}
function mockGet(t, handler = async () => structuredClone(dados)) {
  return t.mock.method(apiClient, "get", async (url, options) => url.endsWith("/unidades")
    ? [{ empresa_codigo: 74014, nome: "Unidade sintética" }]
    : handler(url, options));
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test("texto simples, evidências, bloqueios, histórico e ações exclusivas do diretor", () => {
  const html = renderLancamentos(dados, { papel: "diretor" });
  for (const text of ["Texto do backend\n&lt;script&gt;", "&lt;b&gt;comprovante", "Bloqueado: Sem lastro &lt;b&gt;",
    "42.10", "Frentista sintético", "1234", "14/10/2026", "15/10/2026 10:00", "Lançamento criado: 123"]) assert.ok(html.includes(text), text);
  for (const acao of ["aprovar", "recusar", "desfazer"]) assert.equal(html.split(`data-acao="${acao}"`).length - 1, 1);
  assert.doesNotMatch(html, /<script>|<b>comprovante/);
  for (const papel of ["gerente", "auditor", ""]) {
    assert.doesNotMatch(renderLancamentos(dados, { papel }), /data-acao/);
  }
  assert.doesNotMatch(renderLancamentos(dados, { papel: "diretor", somenteLeitura: true }), /data-acao/);
  assert.match(renderLancamentos({ propostas: [], historico: [] }), /Nenhuma proposta.*Nenhuma ação/s);
});

test("consulta usa unidade e dia ISO e oferece seletores", async t => {
  const get = mockGet(t);
  const f = fixture();
  await renderLancamentosLogos(f.container, { papel: "gerente", unidadeInicial: 74014 });
  assert.match(f.container.innerHTML, /Lançamentos do Logos/);
  assert.match(f.container.innerHTML, /name="unidade"/);
  assert.match(f.container.innerHTML, /name="dia"/);
  assert.deepEqual(get.mock.calls[1].arguments, [URL, { params: { unidade: 74014, dia: "2026-10-14" } }]);
  assert.doesNotMatch(f.result.innerHTML, /data-acao/);
});

for (const acao of ["aprovar", "recusar", "desfazer"]) {
  test(`${acao}: um toque, JSON direto, ID codificado e proteção contra clique duplo`, async t => {
    mockGet(t);
    let liberar;
    const post = t.mock.method(apiClient, "post", () => new Promise(resolve => { liberar = resolve; }));
    const f = fixture();
    await renderLancamentosLogos(f.container, { papel: "diretor" });
    // Mudanças ainda não consultadas não podem alterar o escopo da ação.
    f.form.elements.dia.value = "13/10/2026";
    const id = acao === "desfazer" ? historico.acao_id : proposta.id;
    const primeira = f.click(acao, id);
    await f.click(acao, id);
    assert.equal(post.mock.calls.length, 1);
    assert.ok(f.controls.slice(0, 3).every(c => c.disabled));
    assert.deepEqual(post.mock.calls[0].arguments, [
      `${URL}/${encodeURIComponent(id)}/${acao}`, { unidade: 74014, dia: "2026-10-14" },
    ]);
    liberar({ estado: "confirmado", mensagem: "Ação registrada" });
    await primeira;
    assert.equal(f.message.textContent, "Ação registrada");
    assert.ok(f.controls.every(c => !c.disabled));
  });
}

test("gerente, somente leitura, bloqueados, histórico não confirmado e IDs desconhecidos jamais escrevem", async t => {
  mockGet(t);
  const post = t.mock.method(apiClient, "post", async () => { throw new Error("Não deve chamar"); });
  for (const options of [{ papel: "gerente" }, { papel: "diretor", somenteLeitura: true }, { papel: "diretor" }]) {
    const f = fixture();
    await renderLancamentosLogos(f.container, options);
    for (const [acao, id] of [["aprovar", "bloqueada"], ["recusar", "desconhecida"], ["desfazer", "recusada"]]) await f.click(acao, id);
    if (options.papel === "gerente" || options.somenteLeitura) {
      await f.click("aprovar", proposta.id);
      await f.click("recusar", proposta.id);
      await f.click("desfazer", historico.acao_id);
    }
  }
  assert.equal(post.mock.calls.length, 0);
});

test("erro detail explícito e nova consulta obrigatória após falha de escrita", async t => {
  mockGet(t);
  const post = t.mock.method(apiClient, "post", async () => { throw new Error("Proposta já processada"); });
  const f = fixture();
  await renderLancamentosLogos(f.container, { papel: "diretor" });
  await f.click("aprovar", proposta.id);
  assert.match(f.message.textContent, /Proposta já processada.*Consulte novamente/);
  assert.equal(f.message.attributes.role, "alert");
  assert.equal(f.result.innerHTML, "");
  await f.click("aprovar", proposta.id);
  assert.equal(post.mock.calls.length, 1);
  f.consultar();
  await settle();
  assert.match(f.result.innerHTML, /data-acao/);
});

test("sucesso de escrita com falha ao recarregar não oferece ações antigas", async t => {
  let chamadas = 0;
  mockGet(t, async () => { if (++chamadas > 1) throw new Error("Consulta indisponível"); return dados; });
  t.mock.method(apiClient, "post", async () => ({ estado: "confirmado", mensagem: "OK" }));
  const f = fixture();
  await renderLancamentosLogos(f.container, { papel: "diretor" });
  await f.click("aprovar", proposta.id);
  assert.match(f.message.textContent, /Ação registrada.*Consulta indisponível/);
  assert.equal(f.result.innerHTML, "");
});

test("falhas de leitura, resposta inválida e data inválida são explícitas", async t => {
  for (const resposta of [new Error("Sem permissão"), {}]) {
    const get = mockGet(t, async () => { if (resposta instanceof Error) throw resposta; return resposta; });
    const f = fixture();
    await renderLancamentosLogos(f.container);
    assert.equal(f.message.attributes.role, "alert");
    assert.match(f.message.textContent, /Sem permissão|Resposta inválida/);
    get.mock.restore();
  }
  const get = mockGet(t);
  const f = fixture();
  await renderLancamentosLogos(f.container);
  f.form.elements.dia.value = "31/02/2026";
  f.consultar();
  await settle();
  assert.match(f.message.textContent, /Data inválida/);
  assert.equal(get.mock.calls.length, 2);
});

test("falha ao carregar unidades e escopo vazio são explícitos", async t => {
  for (const resposta of [new Error("Sessão expirada"), []]) {
    const get = t.mock.method(apiClient, "get", async () => { if (resposta instanceof Error) throw resposta; return resposta; });
    const f = fixture();
    await renderLancamentosLogos(f.container);
    assert.match(f.container.innerHTML, /role="alert"/);
    assert.match(f.container.innerHTML, /Sessão expirada|Nenhuma unidade/);
    get.mock.restore();
  }
});

test("Painel e navegação integram a nova página sem alterar o cockpit", async () => {
  const app = await readFile(new globalThis.URL("../../frontend/app.js", import.meta.url), "utf8");
  const index = await readFile(new globalThis.URL("../../frontend/index.html", import.meta.url), "utf8");
  const painel = await readFile(new globalThis.URL("../../frontend/pages/directorDashboard.js", import.meta.url), "utf8");
  assert.match(app, /"lancamentos-logos": "lancamentosLogos"/);
  assert.match(app, /renderLancamentosLogos\(lancamentosLogosNode/);
  assert.match(index, /data-view="lancamentosLogos"/);
  assert.match(index, /id="lancamentosLogosView"/);
  assert.match(painel, /view=lancamentos-logos/);
});
