import {
  fetchAccountsPayable,
  fetchAccountsReceivable,
  fetchConta,
  fetchCompanies,
  fetchEmpresasRede,
  fetchFinancialExpenses,
  fetchFinancialOverview,
  fetchSales,
  fetchSalesByItem,
  fetchSalesByPayment,
  fetchStock,
  fetchFuelSummary,
  fetchFuelExecutive,
  fetchFuelSnapshot,
  postFuelRefresh,
  fetchProductCatalog,
  fetchFinanceCenterSnapshot,
  postFinanceCenterRefresh,
  fetchFinancialIntelligenceSnapshot,
  postFinancialIntelligenceRefresh,
  fetchFinanceCenterSummary,
  fetchCashFlowSnapshot,
  postCashFlowRefresh,
  fetchCashFlow,
} from "./services/api.js";
import { APP_CONFIG } from "./config.js";
import { renderFilters, updateCompanyOptions } from "./components/filters.js";
import { FILIAIS, getFiliaisBaseCodWebSet, hydrateFiliaisCodigoMap, mergeFiliais } from "./components/filiais.js";
import { renderDashboard } from "./pages/dashboard.js";
import { renderExpenses } from "./pages/expenses.js";
import { renderAccountsPayable } from "./pages/accountsPayable.js";
import { renderSales } from "./pages/sales.js";
import { renderStock } from "./pages/stock.js";
import { renderExecutiveDashboard } from "./pages/executiveDashboard.js";
import { renderFuelExecutiveDashboard } from "./pages/fuelExecutiveDashboard.js";
import { renderFinanceCenter } from "./pages/financeCenter.js";
import { renderCashFlow } from "./pages/cashFlow.js";
import { renderCashAudit } from "./pages/cashAudit.js";
import { contarPendenciasAbertas, renderPendencias } from "./pages/pendencias.js";
import { renderCommercialScore } from "./pages/commercialScore.js?v=commercial-score-5";
import { currentSession, login, logout } from "./services/auth.js";
import { renderCompanySwitcher } from "./components/CompanySwitcher.js";
import { createTableState } from "./services/tableState.js";
import {
  ensureProductCatalog,
  enrichFuelExecutive,
  enrichFuelSummary,
  enrichStockRows,
} from "./services/productCatalog.js";

const now = new Date();
const end = now.toISOString().slice(0, 10);
const startDate = new Date(now.getTime() - 1000 * 60 * 60 * 24 * 5)
  .toISOString()
  .slice(0, 10);

const MULTI_FILTER_KEYS = new Set(["empresaCodigo", "centroCusto", "tipoDespesa"]);

const VIEW_ALIASES = {
  "finance-center": "financeCenter",
  financecenter: "financeCenter",
  "cash-flow": "cashFlow",
  cashflow: "cashFlow",
  "cash-audit": "cashAudit",
  cashaudit: "cashAudit",
  placar: "commercialScore",
  "commercial-score": "commercialScore",
};

const VIEW_URL_NAMES = {
  financeCenter: "finance-center",
  cashFlow: "cash-flow",
  cashAudit: "cash-audit",
  commercialScore: "placar",
};

function normalizeViewId(view) {
  const raw = String(view || "executive").trim();
  return VIEW_ALIASES[raw.toLowerCase()] || raw;
}

function viewForUrl(view) {
  return VIEW_URL_NAMES[view] || view;
}

function normalizeToArray(value) {
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item || "").trim())
      .filter(Boolean);
  }
  const text = String(value || "").trim();
  if (!text) return [];
  if (!text.includes(",")) return [text];
  return text
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseUrlFilterValue(key, value) {
  if (!MULTI_FILTER_KEYS.has(key)) return value || "";
  const normalized = normalizeToArray(value).filter(
    (item) => !/^(todos|all|__all__)$/i.test(String(item || "").trim())
  );
  if (normalized.length === 0) return "";
  if (normalized.length === 1) return normalized[0];
  return normalized;
}

function serializeUrlFilterValue(key, value) {
  if (value === "" || value === null || value === undefined) return "";
  if (!MULTI_FILTER_KEYS.has(key)) return String(value);
  const normalized = normalizeToArray(value);
  return normalized.join(",");
}

function normalizeEmpresaCodigos(value) {
  return normalizeToArray(value)
    .map((item) => item.replace(/\D/g, ""))
    .filter(Boolean)
    .map((item) => Number(item))
    .filter((item) => Number.isFinite(item));
}

function fingerprintFilters(filters) {
  const normalized = {
    ...filters,
    empresaCodigo: normalizeToArray(filters?.empresaCodigo),
    centroCusto: normalizeToArray(filters?.centroCusto),
    tipoDespesa: normalizeToArray(filters?.tipoDespesa),
  };
  return JSON.stringify(normalized);
}

function uniqueRowKey(row = {}) {
  const empresa = row.empresaCodigo ?? row.codigoEmpresa ?? row.filialCodigo ?? "";
  const chave =
    row.codigo ??
    row.vendaCodigo ??
    row.vendaItemCodigo ??
    row.tituloPagarCodigo ??
    row.tituloReceberCodigo ??
    row.produtoCodigo ??
    row.caixaCodigo ??
    row.notaEntradaCodigo ??
    "";
  const data = row.data || row.dataMovimento || row.vencimento || row.abertura || "";
  return `${empresa}|${chave}|${data}`;
}

function mergeUniqueRows(rows) {
  const seen = new Set();
  const merged = [];
  rows.forEach((row) => {
    const key = uniqueRowKey(row);
    if (seen.has(key)) return;
    seen.add(key);
    merged.push(row);
  });
  return merged;
}

async function fetchAllPages(fetcher, filters, limit = 200, maxPages = 40) {
  const allRows = [];
  let totalHint = 0;

  for (let page = 1; page <= maxPages; page += 1) {
    const response = await fetcher(filters, page, limit);
    const rows = Array.isArray(response?.data)
      ? response.data
      : Array.isArray(response?.resultados)
        ? response.resultados
        : [];
    const total = Number(response?.total || 0);
    if (total > 0) totalHint = total;
    allRows.push(...rows);

    if (rows.length === 0) break;
    if (total > 0 && allRows.length >= total) break;
    if (rows.length < limit && total === 0) break;
  }

  return {
    data: allRows,
    total: totalHint > 0 ? totalHint : allRows.length,
  };
}

async function fetchDatasetAcrossCompanies(fetcher, filters, displayLimit) {
  const result = await fetchAllPages(fetcher, filters, 200);
  const data = mergeUniqueRows(result.data);
  return {
    page: 1,
    limit: displayLimit,
    total: data.length,
    data,
    synthetic: true,
  };
}

function fromUrl() {
  const query = new URLSearchParams(window.location.search);
  const viewRaw = query.get("view") || "executive";
  const viewNormalized = viewRaw === "fuel" ? "fuels" : normalizeViewId(viewRaw);
  return {
    view: viewNormalized,
    tv: query.get("tv") === "1",
    tvUnit: query.get("posto") || "",
    pageExpenses: Number(query.get("pageExpenses") || 1),
    pageAccounts: Number(query.get("pageAccounts") || 1),
    pageSales: Number(query.get("pageSales") || 1),
    pageFuels: Number(query.get("pageFuels") || 1),
    pageStock: Number(query.get("pageStock") || 1),
    filters: {
      dataInicial: query.get("dataInicial") || startDate,
      dataFinal: query.get("dataFinal") || end,
      empresaCodigo: parseUrlFilterValue("empresaCodigo", query.get("empresaCodigo") || ""),
      centroCusto: parseUrlFilterValue("centroCusto", query.get("centroCusto") || ""),
      tipoDespesa: parseUrlFilterValue("tipoDespesa", query.get("tipoDespesa") || ""),
      valorMin: query.get("valorMin") || "",
      valorMax: query.get("valorMax") || "",
    },
  };
}

function writeUrl(state) {
  const query = new URLSearchParams();
  query.set("view", viewForUrl(state.view));
  query.set("pageExpenses", String(state.pageExpenses));
  query.set("pageAccounts", String(state.pageAccounts));
  query.set("pageSales", String(state.pageSales));
  query.set("pageFuels", String(state.pageFuels));
  query.set("pageStock", String(state.pageStock));
  if (state.view === "commercialScore" && state.tv) {
    query.set("tv", "1");
    if (state.tvUnit) query.set("posto", String(state.tvUnit));
  }

  Object.entries(state.filters).forEach(([key, value]) => {
    const serialized = serializeUrlFilterValue(key, value);
    if (serialized !== "" && serialized !== null && serialized !== undefined) {
      query.set(key, String(serialized));
    }
  });

  const nextUrl = `${window.location.pathname}?${query.toString()}`;
  window.history.replaceState({}, "", nextUrl);
}

function cacheKey(name, payload) {
  return `${name}:${JSON.stringify(payload)}`;
}

function collectEmpresaCodigos(rows) {
  return Array.from(
    new Set(
      (rows || [])
        .map((row) => row?.empresaCodigo)
        .filter((codigo) => codigo !== null && codigo !== undefined && codigo !== "")
        .map((codigo) => String(codigo))
    )
  );
}

function findMissingCodigos(codigos, baseCodigos) {
  return codigos.filter((codigo) => !baseCodigos.has(String(codigo)));
}

function logEndpointDiagnostics(endpoint, payload, baseCodigos) {
  if (!APP_CONFIG.debugWebPosto) return;

  const resultados = Array.isArray(payload?.resultados)
    ? payload.resultados
    : Array.isArray(payload?.data)
      ? payload.data
      : [];
  const codigos = collectEmpresaCodigos(resultados);
  const faltantes = findMissingCodigos(codigos, baseCodigos);

  console.table({
    endpoint,
    total: resultados.length,
    ultimoCodigo: payload?.ultimoCodigo || null,
  });
  console.log(`[REDE DIAG] ${endpoint} empresaCodigo encontrados:`, codigos);
  console.log(`[REDE DIAG] ${endpoint} empresaCodigo fora de filiais.js:`, faltantes);
}

function logRedeValidation(payloads) {
  const baseCodigos = getFiliaisBaseCodWebSet();
  payloads.forEach(({ endpoint, payload }) => logEndpointDiagnostics(endpoint, payload, baseCodigos));
}

const state = {
  ...fromUrl(),
  limitExpenses: 50,
  limitAccounts: 50,
  limitSales: 50,
  limitStock: 50,
  data: {
    overview: null,
    expenses: null,
    accounts: null,
    sales: null,
    stock: null,
    receivables: null,
    fuelSummary: null,
    fuelExecutive: null,
  },
  companies: [],
  productCatalog: null,
  cache: new Map(),
  tables: {
    dashboard: createTableState(),
    expenses: createTableState(),
    accounts: createTableState(),
    sales: createTableState(),
    fuels: createTableState(),
    stock: createTableState(),
  },
};

const loadingNode = document.querySelector("#loading");
const errorNode = document.querySelector("#error");
const executiveNode = document.querySelector("#executiveView");
const dashboardNode = document.querySelector("#dashboardView");
const expensesNode = document.querySelector("#expensesView");
const accountsNode = document.querySelector("#accountsView");
const financeCenterNode = document.querySelector("#financeCenterView");
const cashFlowNode = document.querySelector("#cashFlowView");
const cashAuditNode = document.querySelector("#cashAuditView");
const pendenciasNode = document.querySelector("#pendenciasView");
const commercialScoreNode = document.querySelector("#commercialScoreView");
const fuelsNode = document.querySelector("#fuelsView");
const salesNode = document.querySelector("#salesView");
const stockNode = document.querySelector("#stockView");
const filtersNode = document.querySelector("#filtersContainer");
const authView = document.querySelector("#authView");
const authForm = document.querySelector("#authForm");
const authError = document.querySelector("#authError");
const authMessage = document.querySelector("#authMessage");
const authPassword = document.querySelector("#authPassword");
const logoutButton = document.querySelector("#logoutBtn");
const sessionUser = document.querySelector("#sessionUser");
const pendenciasCount = document.querySelector("#pendenciasCount");
let authenticatedUser = null;

async function atualizarContadorPendencias() {
  if (!authenticatedUser) return;
  try {
    const resposta = await contarPendenciasAbertas();
    pendenciasCount.textContent = String(resposta.abertas);
    pendenciasCount.classList.toggle("hidden", resposta.abertas <= 0);
  } catch (error) {
    setError(error.message || "Falha ao consultar pendências abertas.");
  }
}

function showAuthView(message = "Informe suas credenciais para acessar os dados financeiros.") {
  authMessage.textContent = message;
  authView.classList.remove("hidden");
  filtersNode.classList.add("hidden");
  document.querySelector("#tabs").classList.add("hidden");
  document.querySelector("main").classList.add("hidden");
  document.querySelector(".topbar").classList.add("hidden");
  document.querySelector("#authEmail").focus();
}

window.addEventListener("auth:required", (event) => {
  showAuthView(event.detail?.message || "Sua sessão expirou. Entre novamente.");
});

window.addEventListener("auth:display-only", () => {
  sessionUser.classList.add("hidden");
  logoutButton.classList.add("hidden");
});

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authError.classList.add("hidden");
  const submit = authForm.querySelector("button[type=submit]");
  submit.disabled = true;
  try {
    await login(document.querySelector("#authEmail").value, authPassword.value);
    window.location.reload();
  } catch (error) {
    authError.textContent = error.message || "Não foi possível entrar.";
    authError.classList.remove("hidden");
  } finally {
    submit.disabled = false;
    authPassword.value = "";
  }
});

logoutButton.addEventListener("click", async () => {
  logoutButton.disabled = true;
  try {
    await logout();
    window.location.reload();
  } catch (error) {
    setError(error.message || "Não foi possível encerrar a sessão.");
  } finally {
    logoutButton.disabled = false;
  }
});

void currentSession().then((user) => {
  if (!user) return;
  authenticatedUser = user;
  sessionUser.textContent = `${user.email} · ${user.role}`;
  sessionUser.classList.remove("hidden");
  logoutButton.classList.remove("hidden");
  void atualizarContadorPendencias();
}).catch((error) => setError(error.message || "Não foi possível validar a sessão."));

function setLoading(flag) {
  loadingNode.classList.toggle("hidden", !flag);
}

function setError(message) {
  if (!message) {
    errorNode.classList.add("hidden");
    errorNode.textContent = "";
    return;
  }
  errorNode.textContent = message;
  errorNode.classList.remove("hidden");
}

function setView(view) {
  state.view = normalizeViewId(view);
  writeUrl(state);
  executiveNode.classList.toggle("hidden", view !== "executive");
  dashboardNode.classList.toggle("hidden", view !== "dashboard");
  expensesNode.classList.toggle("hidden", view !== "expenses");
  accountsNode.classList.toggle("hidden", view !== "accounts");
  financeCenterNode.classList.toggle("hidden", view !== "financeCenter");
  cashFlowNode.classList.toggle("hidden", view !== "cashFlow");
  cashAuditNode.classList.toggle("hidden", view !== "cashAudit");
  pendenciasNode.classList.toggle("hidden", view !== "pendencias");
  commercialScoreNode.classList.toggle("hidden", view !== "commercialScore");
  fuelsNode.classList.toggle("hidden", view !== "fuels");
  salesNode.classList.toggle("hidden", view !== "sales");
  stockNode.classList.toggle("hidden", view !== "stock");

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.view === view);
  });
}

function ensureDataDefaults() {
  if (!state.data.overview) state.data.overview = null;
  if (!state.data.expenses) state.data.expenses = { resultados: [], data: [] };
  if (!state.data.accounts) state.data.accounts = { resultados: [], data: [] };
  if (!state.data.sales) state.data.sales = { resultados: [], data: [] };
  if (!state.data.stock) state.data.stock = { resultados: [], data: [] };
  if (!state.data.receivables) state.data.receivables = { resultados: [], data: [] };
  if (!state.data.financeCenter) state.data.financeCenter = null;
  if (!state.data.cashFlow) state.data.cashFlow = null;
}

function clearFilters() {
  state.filters = {
    dataInicial: startDate,
    dataFinal: end,
    empresaCodigo: "",
    centroCusto: "",
    tipoDespesa: "",
    valorMin: "",
    valorMax: "",
  };
  state.pageExpenses = 1;
  state.pageAccounts = 1;
  state.pageSales = 1;
  state.pageFuels = 1;
  state.pageStock = 1;
  state.tables.dashboard = createTableState();
  state.tables.expenses = createTableState();
  state.tables.accounts = createTableState();
  state.tables.sales = createTableState();
  state.tables.fuels = createTableState();
  state.tables.stock = createTableState();
  mountFilters();
}

function mountFilters() {
  renderFilters(
    filtersNode,
    state.filters,
    async (nextFilters) => {
      state.filters = nextFilters;
      state.pageExpenses = 1;
      state.pageAccounts = 1;
      state.pageSales = 1;
      state.pageStock = 1;
      writeUrl(state);
      await refreshAll(false);
    },
    async () => {
      clearFilters();
      writeUrl(state);
      await refreshAll(false);
    },
    {
      onRefresh: async () => {
        state.cache.clear();
        await refreshAll(true);
      },
    }
  );
  updateCompanyOptions(filtersNode, state.companies, state.filters.empresaCodigo);
}

async function getCached(name, params, loader, bypassCache = false) {
  const key = cacheKey(name, params);
  if (!bypassCache && state.cache.has(key)) {
    return state.cache.get(key);
  }
  const result = await loader();
  state.cache.set(key, result);
  return result;
}

function applyFilialMasterFallback() {
  state.companies = mergeFiliais([]);
  hydrateFiliaisCodigoMap(state.companies);
  updateCompanyOptions(filtersNode, state.companies, state.filters.empresaCodigo);
}

async function refreshCompaniesFromApiInBackground(bypassCache = false) {
  try {
    const empresasRede = await getCached(
      "companies_rede",
      { dataInicial: state.filters.dataInicial, dataFinal: state.filters.dataFinal },
      () => fetchEmpresasRede({ dataInicial: state.filters.dataInicial, dataFinal: state.filters.dataFinal }),
      bypassCache
    );

    const apiRows = empresasRede?.resultados || [];
    state.companies = mergeFiliais(apiRows);

    if (APP_CONFIG.debugWebPosto && apiRows.length < FILIAIS.length) {
      console.warn(
        `API retornou apenas ${apiRows.length} empresas. Base local possui ${FILIAIS.length}. Mesclando dados para visao de rede.`
      );
    }

    const companiesFromBackend = await getCached(
      "companies",
      { dataInicial: state.filters.dataInicial, dataFinal: state.filters.dataFinal },
      () => fetchCompanies(state.filters.dataInicial, state.filters.dataFinal),
      bypassCache
    );

    hydrateFiliaisCodigoMap([...companiesFromBackend, ...state.companies]);
    updateCompanyOptions(filtersNode, state.companies, state.filters.empresaCodigo);

    const companyCodes = state.companies
      .map((company) => Number(company?.empresaCodigo))
      .filter((value) => Number.isFinite(value));
    state.productCatalog = await ensureProductCatalog(fetchProductCatalog, companyCodes);
  } catch (error) {
    console.warn("Falha ao atualizar empresas da API. Mantendo FilialMaster local:", error);
  }
}

async function refreshCompanies(bypassCache = false) {
  applyFilialMasterFallback();
  refreshCompaniesFromApiInBackground(bypassCache);
}

function renderAll() {
  renderExecutiveDashboard(executiveNode, state.data, state.filters);
  
  renderDashboard(dashboardNode, state.data.overview, {
    tableState: state.tables.dashboard,
    onSearchChange: (search) => {
      state.tables.dashboard.search = search;
      renderAll();
    },
    onSortChange: (sort) => {
      state.tables.dashboard.sort = sort;
      renderAll();
    },
    onClearFilters: async () => {
      clearFilters();
      writeUrl(state);
      await refreshAll(false);
    },
    onRefresh: async () => {
      state.cache.clear();
      await refreshAll(true);
    },
    exportName: `dashboard_financeiro_${state.filters.dataInicial}`,
  });
  renderExpenses(
    expensesNode,
    state.data.expenses,
    async (nextPage) => {
      state.pageExpenses = nextPage;
      writeUrl(state);
      await refreshExpensesOnly(false);
    },
    {
      tableState: state.tables.expenses,
      onSearchChange: (search) => {
        state.tables.expenses.search = search;
        renderAll();
      },
      onSortChange: (sort) => {
        state.tables.expenses.sort = sort;
        renderAll();
      },
      onClearFilters: async () => {
        clearFilters();
        writeUrl(state);
        await refreshAll(false);
      },
      onRefresh: async () => {
        state.cache.clear();
        await refreshAll(true);
      },
      exportName: `despesas_${state.filters.dataInicial}`,
    }
  );
  renderAccountsPayable(
    accountsNode,
    state.data.accounts,
    async (nextPage) => {
      state.pageAccounts = nextPage;
      writeUrl(state);
      await refreshAccountsOnly(false);
    },
    {
      tableState: state.tables.accounts,
      onSearchChange: (search) => {
        state.tables.accounts.search = search;
        renderAll();
      },
      onSortChange: (sort) => {
        state.tables.accounts.sort = sort;
        renderAll();
      },
      onClearFilters: async () => {
        clearFilters();
        writeUrl(state);
        await refreshAll(false);
      },
      onRefresh: async () => {
        state.cache.clear();
        await refreshAll(true);
      },
      exportName: `contas_pagar_${state.filters.dataInicial}`,
    }
  );

  renderSales(
    salesNode,
    state.data.sales,
    async (nextPage) => {
      state.pageSales = nextPage;
      writeUrl(state);
      await refreshSalesOnly(false);
    },
    {
      fuelSummary: state.data.fuelSummary,
      tableState: state.tables.sales,
      onSearchChange: (search) => {
        state.tables.sales.search = search;
        renderAll();
      },
      onSortChange: (sort) => {
        state.tables.sales.sort = sort;
        renderAll();
      },
      onClearFilters: async () => {
        clearFilters();
        writeUrl(state);
        await refreshAll(false);
      },
      onRefresh: async () => {
        state.cache.clear();
        await refreshAll(true);
      },
      exportName: `vendas_${state.filters.dataInicial}`,
    }
  );

  renderFuelExecutiveDashboard(
    fuelsNode,
    state.data.fuelExecutive,
    {
      tableState: state.tables.fuels,
      onSearchChange: (search) => {
        state.tables.fuels.search = search;
        renderAll();
      },
      onSortChange: (sort) => {
        state.tables.fuels.sort = sort;
        renderAll();
      },
      onClearFilters: async () => {
        clearFilters();
        writeUrl(state);
        await refreshAll(false);
      },
      onRefresh: async () => {
        state.cache.clear();
        await refreshAll(true);
      },
      exportName: `executivo_combustiveis_${state.filters.dataInicial}`,
    }
  );

  renderFinanceCenter(financeCenterNode, state.data.financeCenter, state.filters, {
    onRefresh: async () => {
      state.cache.clear();
      await refreshAll(true);
    },
  });

  renderCashFlow(cashFlowNode, state.data.cashFlow, state.filters, {
    onRefresh: async () => {
      state.cache.clear();
      await refreshAll(true);
    },
  });
  if (state.view === "cashAudit") void renderCashAudit(cashAuditNode);
  if (state.view === "commercialScore") {
    void renderCommercialScore(commercialScoreNode, { tv: state.tv, tvUnit: state.tvUnit });
  }

  renderStock(
    stockNode,
    state.data.stock,
    async (nextPage) => {
      state.pageStock = nextPage;
      writeUrl(state);
      await refreshStockOnly(false);
    },
    {
      tableState: state.tables.stock,
      onSearchChange: (search) => {
        state.tables.stock.search = search;
        renderAll();
      },
      onSortChange: (sort) => {
        state.tables.stock.sort = sort;
        renderAll();
      },
      onClearFilters: async () => {
        clearFilters();
        writeUrl(state);
        await refreshAll(false);
      },
      onRefresh: async () => {
        state.cache.clear();
        await refreshAll(true);
      },
      exportName: `estoque_${state.filters.dataInicial}`,
    }
  );
}

async function loadCashFlowWithSnapshotFirst(bypassCache = false) {
  let snapshot = null;
  try {
    snapshot = await fetchCashFlowSnapshot(state.filters);
  } catch (error) {
    console.warn("[cashFlow] falha ao carregar snapshot:", error);
  }

  if (snapshot?.fromSnapshot && snapshot?.flow) {
    state.data.cashFlow = {
      ...snapshot.flow,
      fromSnapshot: true,
      lastUpdated: snapshot.lastUpdated,
    };
    postCashFlowRefresh(state.filters).catch((error) => {
      console.warn("[cashFlow] refresh em background falhou:", error);
    });
    return;
  }

  const flow = await getCached(
    "cashFlow",
    state.filters,
    () => fetchCashFlow(state.filters),
    bypassCache
  );
  state.data.cashFlow = {
    ...flow,
    fromSnapshot: false,
    lastUpdated: new Date().toISOString(),
  };
  postCashFlowRefresh(state.filters).catch((error) => {
    console.warn("[cashFlow] refresh em background falhou:", error);
  });
}

async function loadFinanceCenterWithSnapshotFirst(bypassCache = false) {
  let snapshot = null;
  try {
    snapshot = await fetchFinanceCenterSnapshot(state.filters);
  } catch (error) {
    console.warn("[financeCenter] falha ao carregar snapshot:", error);
  }

  if (snapshot?.fromSnapshot && snapshot?.center) {
    state.data.financeCenter = {
      ...snapshot.center,
      fromSnapshot: true,
      lastUpdated: snapshot.lastUpdated,
      warnings: snapshot.warnings || [],
    };
    try {
      const intelSnap = await fetchFinancialIntelligenceSnapshot(state.filters);
      if (intelSnap?.fromSnapshot) {
        state.data.financeCenter.intelligence = intelSnap.intelligence;
        state.data.financeCenter.healthScore = intelSnap.healthScore;
        state.data.financeCenter.advanced = intelSnap.advanced;
        state.data.financeCenter.healthScoreV3 = intelSnap.healthScoreV3;
        state.data.financeCenter.supplierIntelligence = intelSnap.supplierIntelligence;
        state.data.financeCenter.supplierSegmentation = intelSnap.supplierSegmentation;
      }
    } catch (error) {
      console.warn("[financeCenter] intelligence snapshot:", error);
    }
    postFinanceCenterRefresh(state.filters).catch((error) => {
      console.warn("[financeCenter] refresh em background falhou:", error);
    });
    postFinancialIntelligenceRefresh(state.filters).catch((error) => {
      console.warn("[financeCenter] intelligence refresh falhou:", error);
    });
    return;
  }

  const summary = await getCached(
    "financeCenterSummary",
    state.filters,
    () => fetchFinanceCenterSummary(state.filters),
    bypassCache
  );
  state.data.financeCenter = {
    summary,
    fromSnapshot: false,
    lastUpdated: new Date().toISOString(),
  };
  try {
    const intelSnap = await fetchFinancialIntelligenceSnapshot(state.filters);
    if (intelSnap?.fromSnapshot) {
      state.data.financeCenter.intelligence = intelSnap.intelligence;
      state.data.financeCenter.healthScore = intelSnap.healthScore;
      state.data.financeCenter.advanced = intelSnap.advanced;
      state.data.financeCenter.healthScoreV3 = intelSnap.healthScoreV3;
      state.data.financeCenter.supplierIntelligence = intelSnap.supplierIntelligence;
      state.data.financeCenter.supplierSegmentation = intelSnap.supplierSegmentation;
    } else {
      const { fetchFinancialIntelligence, fetchFinancialHealthScore } = await import("./services/api.js");
      state.data.financeCenter.intelligence = await fetchFinancialIntelligence(state.filters);
      state.data.financeCenter.healthScore = await fetchFinancialHealthScore(state.filters);
      try {
        const { fetchFinancialIntelligenceAdvanced, fetchFinancialHealthScoreV3, fetchSupplierIntelligence, fetchSupplierSegmentation } = await import("./services/api.js");
        state.data.financeCenter.advanced = await fetchFinancialIntelligenceAdvanced(state.filters);
        state.data.financeCenter.healthScoreV3 = await fetchFinancialHealthScoreV3(state.filters);
        state.data.financeCenter.supplierIntelligence = await fetchSupplierIntelligence(state.filters);
        state.data.financeCenter.supplierSegmentation = await fetchSupplierSegmentation(state.filters);
      } catch (advErr) {
        console.warn("[financeCenter] advanced live:", advErr);
      }
    }
  } catch (error) {
    console.warn("[financeCenter] intelligence live:", error);
  }
  postFinanceCenterRefresh(state.filters).catch((error) => {
    console.warn("[financeCenter] refresh em background falhou:", error);
  });
}

async function loadFuelWithSnapshotFirst(bypassCache = false) {
  let snapshot = null;
  try {
    snapshot = await fetchFuelSnapshot(state.filters);
  } catch (error) {
    console.warn("[fuels] falha ao carregar snapshot:", error);
  }

  if (snapshot?.fromSnapshot && snapshot?.fuel?.data) {
    state.data.fuelExecutive = enrichFuelExecutive(state.productCatalog, snapshot.fuel.data);
    postFuelRefresh(state.filters).catch((error) => {
      console.warn("[fuels] refresh em background falhou:", error);
    });
    return;
  }

  state.data.fuelExecutive = await getCached(
    "fuelExecutive",
    state.filters,
    () => fetchFuelExecutive(state.filters),
    bypassCache
  );
  state.data.fuelExecutive = enrichFuelExecutive(state.productCatalog, state.data.fuelExecutive);
  postFuelRefresh(state.filters).catch((error) => {
    console.warn("[fuels] refresh em background falhou:", error);
  });
}

async function refreshExecutiveFirst(bypassCache = false) {
  setError("");
  setLoading(true);
  try {
    applyFilialMasterFallback();
    ensureDataDefaults();
    renderAll();
  } catch (err) {
    setError(err.message || "Falha na carga inicial do painel executivo");
  } finally {
    setLoading(false);
  }

  refreshCompaniesFromApiInBackground(bypassCache);
}

async function refreshOperationalDataInBackground(bypassCache = false) {
  try {
    const filtersFingerprintAtCall = fingerprintFilters(state.filters);

    const [overview, expenses, accounts, sales, stock, receivables, salesByItem, salesByPayment, conta] = await Promise.all([
      getCached("overview", state.filters, () => fetchFinancialOverview(state.filters), bypassCache),
      getCached(
        "expenses",
        { ...state.filters, scope: "all" },
        () => fetchDatasetAcrossCompanies(fetchFinancialExpenses, state.filters, state.limitExpenses),
        bypassCache
      ),
      getCached(
        "accounts",
        { ...state.filters, scope: "all" },
        () => fetchDatasetAcrossCompanies(fetchAccountsPayable, state.filters, state.limitAccounts),
        bypassCache
      ),
      getCached(
        "sales",
        { ...state.filters, scope: "all" },
        () => fetchDatasetAcrossCompanies(fetchSales, state.filters, state.limitSales),
        bypassCache
      ),
      getCached(
        "stock",
        { ...state.filters, scope: "all" },
        () => fetchDatasetAcrossCompanies(fetchStock, state.filters, state.limitStock),
        bypassCache
      ),
      getCached(
        "receivables",
        { ...state.filters, page: 1, limit: 1 },
        () => fetchAccountsReceivable(state.filters, 1, 1),
        bypassCache
      ),
      getCached(
        "salesByItem",
        { ...state.filters, scope: "all" },
        () => fetchSalesByItem(state.filters, state.pageSales, state.limitSales),
        bypassCache
      ),
      getCached(
        "salesByPayment",
        { ...state.filters, scope: "all" },
        () => fetchSalesByPayment(state.filters, state.pageSales, state.limitSales),
        bypassCache
      ),
      getCached(
        "conta",
        { ...state.filters, scope: "all" },
        () => fetchConta(state.filters, state.pageAccounts, state.limitAccounts),
        bypassCache
      ),
    ]);

    if (filtersFingerprintAtCall !== fingerprintFilters(state.filters)) {
      console.log("[BACKGROUND LOAD] Ignorando resultado antigo por alteração de filtros");
      return;
    }

    state.data.overview = overview;
    state.data.expenses = expenses;
    state.data.accounts = accounts;
    state.data.sales = sales;
    state.data.stock = stock;
    state.data.receivables = receivables;

    logRedeValidation([
      { endpoint: "/INTEGRACAO/EMPRESAS", payload: { resultados: state.companies } },
      { endpoint: "/INTEGRACAO/CONSULTAR_DESPESAS_FINANCEIRO_REDE", payload: expenses },
      { endpoint: "/INTEGRACAO/VENDA", payload: sales },
      { endpoint: "/INTEGRACAO/VENDA_ITEM", payload: salesByItem },
      { endpoint: "/INTEGRACAO/VENDA_FORMA_PAGAMENTO", payload: salesByPayment },
      { endpoint: "/INTEGRACAO/CONTA", payload: conta },
      { endpoint: "/INTEGRACAO/PRODUTO_ESTOQUE", payload: stock },
      { endpoint: "/INTEGRACAO/PRODUTO_EMPRESA", payload: stock },
    ]);

    renderAll();
  } catch (error) {
    console.warn("Falha no carregamento operacional em background:", error);
  }
}

async function refreshAll(bypassCache = false) {
  if (state.view === "executive") {
    await refreshExecutiveFirst(bypassCache);
    refreshOperationalDataInBackground(bypassCache);
    return;
  }

  setError("");
  setLoading(true);
  if (APP_CONFIG.debugFilters) {
    console.log("[debugFilters] filtros globais aplicados", {
      ...state.filters,
      empresaCodigo: normalizeToArray(state.filters.empresaCodigo),
      centroCusto: normalizeToArray(state.filters.centroCusto),
      tipoDespesa: normalizeToArray(state.filters.tipoDespesa),
    });
  }
  try {
    if (state.view === "commercialScore") {
      await renderCommercialScore(commercialScoreNode, {
        load: true,
        tv: state.tv,
        tvUnit: state.tvUnit,
      });
      return;
    }

    if (state.view === "pendencias") {
      await renderPendencias(pendenciasNode, {
        papel: authenticatedUser?.role || "",
        onChange: atualizarContadorPendencias,
      });
      return;
    }

    await refreshCompanies(bypassCache);

    ensureDataDefaults();

    if (state.view === "dashboard") {
      state.data.overview = await getCached("overview", state.filters, () => fetchFinancialOverview(state.filters), bypassCache);
    }

    if (state.view === "expenses") {
      state.data.expenses = await getCached(
        "expenses",
        { ...state.filters, scope: "all" },
        () => fetchDatasetAcrossCompanies(fetchFinancialExpenses, state.filters, state.limitExpenses),
        bypassCache
      );
    }

    if (state.view === "accounts") {
      state.data.accounts = await getCached(
        "accounts",
        { ...state.filters, scope: "all" },
        () => fetchDatasetAcrossCompanies(fetchAccountsPayable, state.filters, state.limitAccounts),
        bypassCache
      );
    }

    if (state.view === "sales") {
      state.data.sales = await getCached(
        "sales",
        { ...state.filters, scope: "all" },
        () => fetchDatasetAcrossCompanies(fetchSales, state.filters, state.limitSales),
        bypassCache
      );
      state.data.fuelSummary = await getCached(
        "fuelSummary",
        state.filters,
        () => fetchFuelSummary(state.filters),
        bypassCache
      );
      state.data.fuelSummary = enrichFuelSummary(state.productCatalog, state.data.fuelSummary || []);
    }

    if (state.view === "fuels") {
      await loadFuelWithSnapshotFirst(bypassCache);
    }

    if (state.view === "financeCenter") {
      await loadFinanceCenterWithSnapshotFirst(bypassCache);
    }

    if (state.view === "cashFlow") {
      await loadCashFlowWithSnapshotFirst(bypassCache);
    }

    if (state.view === "cashAudit") {
      await renderCashAudit(cashAuditNode, { load: true });
    }

    if (state.view === "stock") {
      state.data.stock = await getCached(
        "stock",
        { ...state.filters, scope: "all" },
        () => fetchDatasetAcrossCompanies(fetchStock, state.filters, state.limitStock),
        bypassCache
      );
      state.data.stock = {
        ...state.data.stock,
        data: enrichStockRows(state.productCatalog, state.data.stock?.data || []),
      };
    }

    renderAll();
  } catch (error) {
    setError(error.message || "Falha ao carregar dados financeiros");
  } finally {
    setLoading(false);
  }
}

async function refreshExpensesOnly(bypassCache = false) {
  setError("");
  setLoading(true);
  try {
    const expenses = await getCached(
      "expenses",
      { ...state.filters, scope: "all" },
      () => fetchDatasetAcrossCompanies(fetchFinancialExpenses, state.filters, state.limitExpenses),
      bypassCache
    );
    state.data.expenses = expenses;
    renderAll();
  } catch (error) {
    setError(error.message || "Falha ao carregar despesas");
  } finally {
    setLoading(false);
  }
}

async function refreshAccountsOnly(bypassCache = false) {
  setError("");
  setLoading(true);
  try {
    const accounts = await getCached(
      "accounts",
      { ...state.filters, scope: "all" },
      () => fetchDatasetAcrossCompanies(fetchAccountsPayable, state.filters, state.limitAccounts),
      bypassCache
    );
    state.data.accounts = accounts;
    renderAll();
  } catch (error) {
    setError(error.message || "Falha ao carregar contas a pagar");
  } finally {
    setLoading(false);
  }
}

async function refreshSalesOnly(bypassCache = false) {
  setError("");
  setLoading(true);
  try {
    const sales = await getCached(
      "sales",
      { ...state.filters, scope: "all" },
      () => fetchDatasetAcrossCompanies(fetchSales, state.filters, state.limitSales),
      bypassCache
    );
    state.data.sales = sales;

    state.data.fuelSummary = await getCached(
      "fuelSummary",
      state.filters,
      () => fetchFuelSummary(state.filters),
      bypassCache
    );

    renderAll();
  } catch (error) {
    setError(error.message || "Falha ao carregar vendas");
  } finally {
    setLoading(false);
  }
}

async function refreshStockOnly(bypassCache = false) {
  setError("");
  setLoading(true);
  try {
    const stock = await getCached(
      "stock",
      { ...state.filters, scope: "all" },
      () => fetchDatasetAcrossCompanies(fetchStock, state.filters, state.limitStock),
      bypassCache
    );
    state.data.stock = stock;
    renderAll();
  } catch (error) {
    setError(error.message || "Falha ao carregar estoque");
  } finally {
    setLoading(false);
  }
}

mountFilters();

document.querySelector("#refreshBtn")?.addEventListener("click", async () => {
  state.cache.clear();
  await refreshAll(true);
  await atualizarContadorPendencias();
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", async () => {
    setView(tab.dataset.view);
    await refreshAll(false);
  });
});

setView(state.view);
writeUrl(state);
refreshAll(false);
