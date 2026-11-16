import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";
import { parseFin02DemoReport } from "../src/lib/fin02-demo-schema.ts";

const fixture = JSON.parse(readFileSync(
  new URL("../../../WebPosto_API/tests/fixtures/fin02-demo-v1.json", import.meta.url), "utf8"
));

function freshFixture() {
  const payload = structuredClone(fixture);
  payload.referencia_temporal = new Date().toISOString();
  for (const snapshot of Object.values(payload.snapshots)) {
    snapshot.capturado_em = new Date(Date.now() - 120000).toISOString();
    snapshot.origem_atualizada_em = new Date(Date.now() - 180000).toISOString();
  }
  return payload;
}

function createPanelHandler() {
  const source = readFileSync(new URL("../src/components/fin02-demo-panel.tsx", import.meta.url), "utf8");
  const ast = ts.createSourceFile("panel.tsx", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let initializer;
  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(ast) === "handleFileChange") {
      initializer = node.initializer.getText(ast);
    }
    ts.forEachChild(node, visit);
  }
  visit(ast);
  assert.ok(initializer, "The regression must execute the real panel handler.");
  const { outputText } = ts.transpileModule(`const handler = ${initializer};`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  });
  const state = { report: null, fileName: null, errorMessage: null };
  const handle = new Function(
    "setReport", "setFileName", "setErrorMessage", "parseFin02DemoReport",
    "FIN02_DEMO_MAX_FILE_BYTES", "MAX_FILE_SIZE_LABEL", "selectionId",
    `${outputText}\nreturn handler;`
  )(
    (value) => { state.report = value; }, (value) => { state.fileName = value; },
    (value) => { state.errorMessage = value; }, parseFin02DemoReport,
    1024 * 1024, "1 MiB", { current: 0 }
  );
  return { state, select: (file) => handle({ currentTarget: { files: file ? [file] : [] } }) };
}

function pendingFile(name) {
  let finish;
  let fail;
  const text = new Promise((resolve, reject) => { finish = resolve; fail = reject; });
  return { file: { name, size: 5000, text: () => text }, finish, fail };
}

test("latest oversized rejection invalidates the older pending valid read", async () => {
  const { state, select } = createPanelHandler();
  const older = pendingFile("older.json");
  const pending = select(older.file);
  await select({ name: "oversized.json", size: 1024 * 1024 + 1 });
  const rejected = { ...state };
  assert.equal(state.report, null);
  assert.match(state.errorMessage, /Arquivo rejeitado: o limite/);
  older.finish(JSON.stringify(freshFixture()));
  await pending;
  assert.deepEqual(state, rejected);
});

test("two valid reads in reverse order render only the latest selection", async () => {
  const { state, select } = createPanelHandler();
  const older = pendingFile("older.json");
  const latest = pendingFile("latest.json");
  const first = select(older.file);
  const second = select(latest.file);
  const payload = freshFixture();
  payload.resumo.despesas[0].fitid = "FITID-SINTETICO-LATEST";
  latest.finish(JSON.stringify(payload));
  await second;
  const accepted = { ...state };
  assert.equal(state.fileName, "latest.json");
  assert.equal(state.report.resumo.despesas[0].fitid, "FITID-SINTETICO-LATEST");
  older.finish(JSON.stringify(freshFixture()));
  await first;
  assert.deepEqual(state, accepted);
});

test("obsolete malformed JSON cannot replace a newer valid selection", async () => {
  const { state, select } = createPanelHandler();
  const older = pendingFile("older.json");
  const pending = select(older.file);
  await select({ name: "latest.json", size: 5000, text: async () => JSON.stringify(freshFixture()) });
  const accepted = { ...state };
  older.finish("{invalid");
  await pending;
  assert.deepEqual(state, accepted);
});

test("obsolete file read rejection cannot replace a newer valid selection", async () => {
  const { state, select } = createPanelHandler();
  const older = pendingFile("older.json");
  const pending = select(older.file);
  await select({ name: "latest.json", size: 5000, text: async () => JSON.stringify(freshFixture()) });
  const accepted = { ...state };
  older.fail(new Error("Synthetic read failure"));
  await pending;
  assert.deepEqual(state, accepted);
});

test("clearing input invalidates older pending reads", async () => {
  const { state, select } = createPanelHandler();
  const older = pendingFile("older.json");
  const pending = select(older.file);
  await select(null);
  older.finish(JSON.stringify(freshFixture()));
  await pending;
  assert.deepEqual(state, { report: null, fileName: null, errorMessage: null });
});

test("contract preserves exact Decimal, synthetic markers and snapshot metadata", () => {
  const report = parseFin02DemoReport(freshFixture());
  assert.equal(report.resumo.despesas[0].valor, "125.600000000000000001");
  assert.equal(report.resumo.total_geral, "125.600000000000000001");
  assert.equal(report.snapshots.titulos.status_cobertura, "COBERTURA_NAO_VERIFICADA");
  assert.equal(report.snapshots.titulos.declaracao_cobertura, "DECLARADA");
  assert.equal(report.sintetico, true);
  assert.equal(report.cnpj_sintetico, "00.000.000/0000-00");
});

test("rejects unknown fields, non-synthetic identity, marker and CNPJ", () => {
  for (const mutate of [
    (p) => { p.unexpected = true; }, (p) => { p.resumo.unidade_codigo = -1; },
    (p) => { p.sintetico = false; }, (p) => { delete p.sintetico; },
    (p) => { p.cnpj_sintetico = "CNPJ-NAO-PERMITIDO"; },
    (p) => { p.resumo.despesas[0].conta_sufixo = "CONTA-NAO-PERMITIDA"; },
  ]) {
    const payload = freshFixture();
    mutate(payload);
    assert.throws(() => parseFin02DemoReport(payload), /Formato FIN-02 inválido/);
  }
});

test("complete source triage does not verify ERP coverage", () => {
  const payload = freshFixture();
  payload.resumo.triagem_completa = true;
  payload.resumo.fontes_nao_mapeadas = [];
  payload.resumo.fontes_cobertura_incompleta = [];
  const report = parseFin02DemoReport(payload);
  assert.equal(report.resumo.triagem_completa, true);
  assert.equal(report.snapshots.titulos.status_cobertura, "COBERTURA_NAO_VERIFICADA");
});

test("rejects bad totals, negative decimals, stale metadata and inverted source times", () => {
  for (const [mutate, error] of [
    [(p) => { p.resumo.total_geral = "125.60"; }, /total geral/],
    [(p) => { p.resumo.despesas[0].valor = "-1"; }, /Formato FIN-02 inválido/],
    [(p) => { p.resumo.totais_por_tipo["PIX pessoa"][1] = "0"; }, /totais por tipo/],
    [(p) => { p.referencia_temporal = new Date(Date.now() - 8 * 86400000).toISOString(); }, /desatualizado/],
    [(p) => { p.snapshots.titulos.origem_atualizada_em = p.referencia_temporal; }, /inconsistentes/],
  ]) {
    const payload = freshFixture();
    mutate(payload);
    assert.throws(() => parseFin02DemoReport(payload), error);
  }
});
