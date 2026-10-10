const API_BASE = window.location.origin || "";
let pendingRefresh;

function notifyAuthRequired(message) {
  if (typeof window.dispatchEvent === "function" && typeof CustomEvent === "function") {
    window.dispatchEvent(new CustomEvent("auth:required", { detail: { message } }));
  }
}

async function refreshAccessCookie(timeout) {
  if (!pendingRefresh) {
    pendingRefresh = fetchWithTimeout("/auth/refresh", {
      method: "POST",
      credentials: "same-origin",
    }, timeout).finally(() => {
      pendingRefresh = null;
    });
  }
  return pendingRefresh;
}

/**
 * Faz a requisição HTTP com timeout.
 * @param {string} url
 * @param {RequestInit} options
 * @param {number} timeoutMs
 * @returns {Promise<Response>}
 */
async function fetchWithTimeout(url, options = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    return response;
  } finally {
    clearTimeout(id);
  }
}

/**
 * Centraliza a construção da query string.
 * @param {Object} params
 * @returns {string}
 */
export function buildQueryString(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") return;
    query.set(key, String(value));
  });
  return query.toString() ? `?${query.toString()}` : "";
}

/**
 * Cliente de API Centralizado.
 * Lida com headers base, tratamento de erro, parsing JSON e timeout.
 */
export const apiClient = {
  async request(method, path, options = {}) {
    const { params, body, headers, timeout = 30000, suppressAuthRedirect = false } = options;
    const url = `${API_BASE}${path}${buildQueryString(params)}`;

    const fetchOptions = {
      method: method.toUpperCase(),
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...headers,
      },
    };

    if (body) {
      fetchOptions.body = JSON.stringify(body);
    }

    let response;
    try {
      response = await fetchWithTimeout(url, fetchOptions, timeout);
    } catch (error) {
      if (error?.name === "AbortError") {
        throw new Error(`Timeout na requisicao ${method.toUpperCase()} ${path}`);
      }
      throw error;
    }
    const isProtected = path.startsWith("/api/v1/cash-audit/") || path.startsWith("/api/v1/commercial/");
    const isDisplayMode = headers?.["X-Display-Mode"] === "true";
    if (response.status === 401 && isProtected && !suppressAuthRedirect && !isDisplayMode) {
      let refreshResponse;
      try {
        refreshResponse = await refreshAccessCookie(timeout);
      } catch (error) {
        notifyAuthRequired("Sua sessão expirou. Entre novamente.");
        throw error;
      }
      if (refreshResponse.ok) {
        try {
          response = await fetchWithTimeout(url, fetchOptions, timeout);
        } catch (error) {
          if (error?.name === "AbortError") {
            throw new Error(`Timeout na requisicao ${method.toUpperCase()} ${path}`);
          }
          throw error;
        }
      } else if (refreshResponse.status === 401) {
        notifyAuthRequired("Sua sessão expirou. Entre novamente.");
      } else {
        const error = new Error("Falha ao renovar a sessão.");
        error.status = refreshResponse.status;
        throw error;
      }
    }

    let data;
    try {
      if (response.status !== 204) {
        data = await response.json();
      }
    } catch (err) {
      throw new Error(`Falha ao processar resposta da API para ${path}`);
    }

    if (!response.ok || (data && data.success === false)) {
      const msg = data?.error?.message || data?.detail || `Falha na requisicao ${method} ${path}`;
      const error = new Error(msg);
      error.status = response.status;
      if (response.status === 401 && isProtected && !suppressAuthRedirect) {
        notifyAuthRequired(msg);
      }
      throw error;
    }

    return data;
  },

  get(path, options = {}) {
    return this.request("GET", path, options);
  },

  post(path, body, options = {}) {
    return this.request("POST", path, { ...options, body });
  },

  put(path, body, options = {}) {
    return this.request("PUT", path, { ...options, body });
  },

  delete(path, options = {}) {
    return this.request("DELETE", path, options);
  },
};
