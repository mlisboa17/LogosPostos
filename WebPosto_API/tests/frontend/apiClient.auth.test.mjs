import assert from "node:assert/strict";
import { test } from "node:test";

const authEvents = [];
globalThis.window = {
  location: { origin: "http://localhost" },
  dispatchEvent: (event) => authEvents.push(event),
};
globalThis.CustomEvent = class CustomEvent {
  constructor(type, options = {}) {
    this.type = type;
    this.detail = options.detail;
  }
};

const { apiClient } = await import("../../frontend/services/apiClient.js");

test("401 renova cookie e repete a chamada same-origin uma única vez", async (t) => {
  authEvents.length = 0;
  let auditCalls = 0;
  const fetch = t.mock.method(globalThis, "fetch", async (url, options) => {
    if (url === "/auth/refresh") {
      return new Response(JSON.stringify({ user: { role: "diretor" } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    auditCalls += 1;
    return auditCalls === 1
      ? new Response(JSON.stringify({ detail: "Invalid token" }), { status: 401 })
      : new Response(JSON.stringify([{ empresa_codigo: 321 }]), { status: 200 });
  });

  const result = await apiClient.get("/api/v1/cash-audit/unidades");

  assert.deepEqual(result, [{ empresa_codigo: 321 }]);
  assert.deepEqual(fetch.mock.calls.map((call) => call.arguments[0]), [
    "http://localhost/api/v1/cash-audit/unidades",
    "/auth/refresh",
    "http://localhost/api/v1/cash-audit/unidades",
  ]);
  assert.ok(fetch.mock.calls.every((call) => call.arguments[1].credentials === "same-origin"));
  assert.deepEqual(authEvents, []);
});

test("modo TV não tenta refresh de usuário nem envia evento até erro final", async (t) => {
  authEvents.length = 0;
  const fetch = t.mock.method(globalThis, "fetch", async () => new Response(
    JSON.stringify({ detail: "Invalid display token" }),
    { status: 401, headers: { "Content-Type": "application/json" } },
  ));

  await assert.rejects(
    apiClient.get("/api/v1/commercial/placar", {
      headers: { "X-Display-Mode": "true" },
    }),
    (error) => error.status === 401,
  );

  assert.equal(fetch.mock.calls.length, 1);
  assert.deepEqual(authEvents.map((event) => event.type), ["auth:required"]);
});

test("probe de token TV pode tratar 401 sem disparar login", async (t) => {
  authEvents.length = 0;
  t.mock.method(globalThis, "fetch", async () => new Response(
    JSON.stringify({ detail: "Not authenticated" }),
    { status: 401, headers: { "Content-Type": "application/json" } },
  ));

  await assert.rejects(
    apiClient.get("/api/v1/commercial/postos", {
      headers: { "X-Display-Mode": "true" },
      suppressAuthRedirect: true,
    }),
    (error) => error.status === 401,
  );
  assert.deepEqual(authEvents, []);
});
