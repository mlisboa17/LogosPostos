async function parseResponse(response) {
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    throw new Error("Falha ao processar resposta de autenticação.");
  }
  if (!response.ok) {
    const error = new Error(payload?.detail || "Falha na autenticação.");
    error.status = response.status;
    throw error;
  }
  return payload;
}

export async function login(email, password) {
  const response = await fetch("/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return parseResponse(response);
}

export async function currentSession() {
  let response = await fetch("/auth/me", { credentials: "same-origin" });
  if (response.status === 401) {
    const refreshed = await fetch("/auth/refresh", {
      method: "POST",
      credentials: "same-origin",
    });
    if (refreshed.status === 401) return null;
    await parseResponse(refreshed);
    response = await fetch("/auth/me", { credentials: "same-origin" });
  }
  return parseResponse(response);
}

export async function logout() {
  const response = await fetch("/auth/logout", {
    method: "POST",
    credentials: "same-origin",
  });
  return parseResponse(response);
}
