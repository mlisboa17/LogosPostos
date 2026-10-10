import assert from "node:assert/strict";
import { test } from "node:test";

const { login, currentSession, logout } = await import("../../frontend/services/auth.js");

test("login usa cookie same-origin e não depende de JWT no corpo", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({
    user: { email: "gerente@example.invalid", role: "gerente", company_id: 321 },
  }), { status: 200, headers: { "Content-Type": "application/json" } }));

  const result = await login("gerente@example.invalid", "synthetic-test-password");

  assert.equal(result.user.role, "gerente");
  assert.equal(fetch.mock.calls[0].arguments[0], "/auth/login");
  assert.equal(fetch.mock.calls[0].arguments[1].credentials, "same-origin");
  assert.equal(fetch.mock.calls[0].arguments[1].body, JSON.stringify({
    email: "gerente@example.invalid",
    password: "synthetic-test-password",
  }));
});

test("sessão ausente retorna null e logout usa cookie same-origin", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => new Response(
    JSON.stringify({ detail: "Not authenticated" }),
    { status: 401, headers: { "Content-Type": "application/json" } },
  ));
  assert.equal(await currentSession(), null);

  fetch.mock.mockImplementation(async () => new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }));
  assert.deepEqual(await logout(), { ok: true });
  assert.equal(fetch.mock.calls[2].arguments[1].credentials, "same-origin");
});

test("falha de login preserva status HTTP para tratamento da interface", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({
    detail: "Invalid credentials",
  }), { status: 401, headers: { "Content-Type": "application/json" } }));

  await assert.rejects(login("wrong@example.invalid", "wrong-password"), (error) => {
    assert.equal(error.status, 401);
    assert.equal(error.message, "Invalid credentials");
    return true;
  });
});
