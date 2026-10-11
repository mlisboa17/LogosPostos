import assert from "node:assert/strict";
import { test } from "node:test";
import { lerDataBR, formatarData, formatarDataHora, campoDataBR, dataRecifeISO, ativarCamposDataBR } from "../../frontend/utils/datas.js";

test("datas BR ida e volta, fuso Recife e datas invalidas", () => {
  assert.equal(lerDataBR("01/10/2026"), "2026-10-01");
  assert.equal(formatarData("2026-10-01"), "01/10/2026");
  assert.equal(formatarDataHora("2026-10-02T01:00:00Z"), "01/10/2026 22:00");
  assert.equal(dataRecifeISO(new Date("2026-10-02T01:00:00Z")), "2026-10-01");
  for (const value of ["31/02/2026", "29/02/2026", "00/10/2026", "2026-10-01", "1/10/2026"]) {
    assert.throws(() => lerDataBR(value), /inválida/);
  }
  assert.equal(lerDataBR("29/02/2024"), "2024-02-29");
});
test("campo brasileiro texto com mascara e validacao sem formato americano do navegador", () => {
  const html = campoDataBR({ nome: "inicio", valor: "2026-10-01" });
  assert.ok(html.includes('type="text"') && html.includes('value="01/10/2026"'));
  assert.ok(!html.includes('type="date"'));
  const handlers = {};
  const input = { value: "01102026", addEventListener: (e, fn) => handlers[e] = fn, setCustomValidity: value => input.error = value };
  ativarCamposDataBR({ querySelectorAll: () => [input] });
  handlers.input();
  assert.equal(input.value, "01/10/2026");
  input.value = "31/02/2026"; handlers.blur();
  assert.match(input.error, /inválida/);
});
