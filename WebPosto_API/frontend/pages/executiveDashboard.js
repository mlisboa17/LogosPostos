import { renderTopNBlocks } from "../components/topN.js";
import { renderAlerts } from "../components/alerts.js";
import { metricsEngine } from "../services/metricsEngine.js";
import { formatCurrency, formatNumber } from "../services/format.js";
import { fetchExecutiveSnapshot, postExecutiveRefresh } from "../services/api.js";
import { computeAlerts, computeTopN } from "../services/analyticsEngine.js";
import { APP_CONFIG } from "../config.js";
import { formatarData, formatarDataHora } from "../utils/datas.js";

const FRIENDLY_FALLBACK_MSG = "Não foi possível atualizar agora. Exibindo último dado disponível.";
const STALE_THRESHOLD_MS = 30 * 60 * 1000;
const REFRESH_POLL_MS = 3000;
const REFRESH_POLL_MAX_MS = 120000;

let executiveRenderGeneration = 0;
let executiveRefreshInFlight = false;
let lastAutoRefreshKey = "";

function formatSnapshotDate(iso) {
  if (!iso) return "—";
  return formatarDataHora(iso);
}

function isSnapshotStale(lastUpdated) {
  if (!lastUpdated) return true;
  const date = new Date(lastUpdated);
  if (Number.isNaN(date.getTime())) return true;
  return Date.now() - date.getTime() > STALE_THRESHOLD_MS;
}

function fuelDataFromSnapshot(fuel) {
  if (!fuel) return null;
  const data = fuel?.data || fuel;
  if (Array.isArray(data)) return data;
  const combustiveis = data?.combustiveis;
  if (!Array.isArray(combustiveis)) return null;
  return combustiveis.map((item) => ({
    combustivel: item.combustivel,
    combustivelDisplay: item.combustivelDisplay || item.combustivel,
    litros: item.litros,
    participacao: item.participacao,
  }));
}

function friendlyErrorMessage(hasSnapshotData) {
  return hasSnapshotData ? FRIENDLY_FALLBACK_MSG : "Sem dados disponíveis no momento. Tente atualizar em instantes.";
}

window._execShowAudit = (auditData) => {
  const d = auditData || {};
  alert(
    `Auditoria Gerencial (Calculado no Backend - LOGOS SPACE Analytics)\n\n` +
    `Período: ${formatarData(d.periodoInicial)} → ${formatarData(d.periodoFinal)}\n` +
    `Origem: ${d.origemSistema || "webpostos"}\n` +
    `Empresas: ${(d.empresasCodigos || []).join(", ") || "Rede completa"}\n\n` +
    `Lineage:\n` +
    Object.entries(d.lineage || {}).map(([k, v]) => `  ${k}: ${v}`).join("\n")
  );
};

function renderKpiBarFromBackend(container, kpis) {
  if (!kpis) {
    container.innerHTML = `<div class="kpi-bar"><div class="kpi-item"><span class="kpi-label">Sem dados de KPI</span></div></div>`;
    return;
  }
  container.innerHTML = `
    <div class="kpi-bar">
      <div class="kpi-item">
        <span class="kpi-label">Faturamento Total <b title="VENDA.totalVenda via /INTEGRACAO/VENDA_ITEM_REDE" style="cursor:help">ℹ️</b></span>
        <span class="kpi-val">${formatCurrency(kpis.faturamento)}</span>
      </div>
      <div class="kpi-item">
        <span class="kpi-label">Despesas Totais <b title="DESPESAS.valor via /INTEGRACAO/CONSULTAR_DESPESAS_FINANCEIRO_REDE" style="cursor:help">ℹ️</b></span>
        <span class="kpi-val">${formatCurrency(kpis.despesasTotais)}</span>
      </div>
      <div class="kpi-item">
        <span class="kpi-label">Resultado <b title="faturamento - custosProduto - outrasDespesas" style="cursor:help">ℹ️</b></span>
        <span class="kpi-val ${Number(kpis.resultadoOperacional) < 0 ? 'text-danger' : 'text-success'}">${formatCurrency(kpis.resultadoOperacional)}</span>
      </div>
      <div class="kpi-item">
        <span class="kpi-label">Ticket Médio <b title="faturamento / qtdVendas" style="cursor:help">ℹ️</b></span>
        <span class="kpi-val">${formatCurrency(kpis.ticketMedio)}</span>
      </div>
      <div class="kpi-item">
        <span class="kpi-label">Qtd Vendas <b title="Endpoint: VENDA" style="cursor:help">ℹ️</b></span>
        <span class="kpi-val">${formatNumber(kpis.qtdVendas)}</span>
      </div>
      <div class="kpi-item">
        <span class="kpi-label">Clientes <b title="Endpoint: VENDA (Nomes únicos)" style="cursor:help">ℹ️</b></span>
        <span class="kpi-val">${formatNumber(kpis.qtdClientes)}</span>
      </div>
      <div class="kpi-item">
        <span class="kpi-label">Estoque Total <b title="Endpoint: PRODUTO_ESTOQUE" style="cursor:help">ℹ️</b></span>
        <span class="kpi-val">${formatNumber(kpis.estoqueTotal)}</span>
      </div>
    </div>
  `;
}

function renderDreFromBackend(container, dre) {
  if (!dre) {
    container.innerHTML = `<div class="panel"><span class="small">DRE não disponível.</span></div>`;
    return;
  }
  const isValid = dre.validacaoOk !== false;
  container.innerHTML = `
    <div class="panel dre-panel">
      <h3>DRE Gerencial <span style="font-size:11px;color:#888">(Calculado no Backend)</span></h3>
      <div class="dre-line"><span>Receitas brutas:</span><span>${formatCurrency(dre.receitas)}</span></div>
      <div class="dre-line negative"><span>(-) Custos Produto:</span><span>${formatCurrency(dre.custosProduto)}</span></div>
      <div class="dre-line negative"><span>(-) Outras Despesas:</span><span>${formatCurrency(dre.outrasDespesas)}</span></div>
      <hr />
      ${!isValid ? `<div class="alert-danger" style="margin-bottom:8px;padding:4px;font-size:12px">⚠ Divergência DRE detectada: ${dre.divergencia}</div>` : ""}
      <div class="dre-line total"><span>Resultado Operacional:</span><span class="${Number(dre.resultadoOperacional) < 0 ? 'text-danger' : 'text-success'}">${formatCurrency(dre.resultadoOperacional)}</span></div>
      <div class="dre-line"><span>Margem %:</span><span>${formatNumber(dre.margemPct)}% <b title="${dre.formula || ''}" style="cursor:help">ℹ️</b></span></div>
    </div>
  `;
}

function qualityBadgeClass(status) {
  if (status === "ok") return "badge-success";
  if (status === "warning") return "badge-warning";
  return "badge-danger";
}

function renderDataQualityCard(container, payload, errorMessage) {
  if (errorMessage) {
    container.innerHTML = `
      <div class="panel">
        <h3>Qualidade dos Dados</h3>
        <div class="small exec-fallback-msg">${errorMessage}</div>
      </div>
    `;
    return;
  }

  if (!payload) {
    container.innerHTML = `
      <div class="panel">
        <h3>Qualidade dos Dados</h3>
        <div class="small">Sem dados para o período selecionado.</div>
      </div>
    `;
    return;
  }

  const score = Number(payload.score || 0);
  const status = payload.status || "danger";
  const summary = payload.summary || {};
  const issues = payload.issues || {};

  container.innerHTML = `
    <div class="panel data-quality-card">
      <div class="data-quality-header">
        <h3>Qualidade dos Dados</h3>
        <span class="badge ${qualityBadgeClass(status)}">${status.toUpperCase()}</span>
      </div>
      <div class="data-quality-score">${formatNumber(score)}%</div>
      <div class="data-quality-summary small">
        ${formatNumber(summary.validos || 0)} válidos de ${formatNumber(summary.totalRegistros || 0)}
      </div>
      <div class="data-quality-issues small">
        Inválidos: ${formatNumber(summary.invalidos || 0)} • Duplicados: ${formatNumber(issues.duplicados || 0)} • Valores inválidos: ${formatNumber(issues.valoresInvalidos || 0)}
      </div>
    </div>
  `;
}

function renderNetworkCoverageCard(container, payload, errorMessage) {
  if (errorMessage) {
    container.innerHTML = `
      <div class="panel">
        <h3>Cobertura e Saúde da Rede</h3>
        <div class="small exec-fallback-msg">${errorMessage}</div>
      </div>
    `;
    return;
  }

  if (!payload) {
    container.innerHTML = `
      <div class="panel">
        <h3>Cobertura e Saúde da Rede</h3>
        <div class="small">Sem dados de cobertura disponíveis.</div>
      </div>
    `;
    return;
  }

  const covPercent = payload.coveragePercent ?? 0;
  const confirmedPercent = payload.coverageConfirmedPercent ?? 0;
  const healthScore = payload.networkHealth ?? 0;
  const tot = payload.filiaisTotais ?? 0;
  const confirmed = payload.filiaisConfirmadas ?? 0;
  const pending = payload.filiaisPendentesIdentificacao ?? 0;
  const active = payload.filiaisAtivas ?? 0;
  const inactive = payload.filiaisInativas ?? 0;
  const withData = payload.filiaisComDados ?? 0;
  const semData = payload.filiaisSemDados ?? 0;

  const branches = payload.filiais || [];
  const numSemToken = branches.filter((b) => b.statusDetalhado === "Token insuficiente").length;
  const numPending = branches.filter((b) => b.status === "PENDENTE_IDENTIFICACAO").length;

  container.innerHTML = `
    <div class="panel network-coverage-card" style="margin-bottom:1rem;">
      <div class="data-quality-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <h3 style="margin:0;">Cobertura e Saúde da Rede</h3>
        <span class="badge ${healthScore >= 90 ? 'badge-success' : 'badge-warning'}" style="padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">
          SAÚDE DA REDE: ${healthScore}%
        </span>
      </div>
      
      <div class="grid-2-cols" style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-top:0.5rem;margin-bottom:0.5rem;">
        <div class="cov-col" style="border-right: 1px solid #efefef; padding-right:1rem;">
          <div style="font-size:12px;color:#666;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Cobertura da Rede</div>
          <div style="font-size:32px;font-weight:bold;color:#4f46e5;margin:4px 0;">${formatNumber(covPercent)}%</div>
          <div style="font-size:12px;color:#888;">Operacional: filiaisComDados / filiaisAtivas (${withData} / ${active})</div>
          <div style="font-size:12px;color:#888;">Confirmadas: ${formatNumber(confirmedPercent)}% (${confirmed} / ${tot})</div>
        </div>
        <div class="resumo-col" style="padding-left:0.5rem; display:flex; flex-direction:column; justify-content:center; gap:4px;">
          <div style="font-size:13px;color:#333;"><strong style="color:#1d4ed8;">● ${confirmed}</strong> com COD WEB confirmado</div>
          <div style="font-size:13px;color:#333;"><strong style="color:#059669;">● ${active}</strong> filiais ativas</div>
          <div style="font-size:13px;color:#333;"><strong style="color:#2563eb;">● ${withData}</strong> com dados operacionais</div>
          <div style="font-size:13px;color:#333;"><strong style="color:#db2777;">● ${numSemToken}</strong> token insuficiente</div>
          <div style="font-size:13px;color:#333;"><strong style="color:#c2410c;">● ${numPending}</strong> pendente de identificação</div>
          ${inactive > 0 ? `<div style="font-size:11px;color:#6b7280;margin-top:2px;"><b>${inactive}</b> filial inativa fora da cobertura operacional atual</div>` : ""}
        </div>
      </div>

      <div class="panel" style="background:#fafafa;border:1px solid #eee;margin:0.5rem 0 0.75rem 0;">
        <h3 style="margin:0 0 0.5rem 0;">Governança de Filiais</h3>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px;font-size:13px;">
          <div><strong>${tot}</strong> filiais cadastradas</div>
          <div><strong>${confirmed}</strong> com COD WEB confirmado</div>
          <div><strong>${pending}</strong> pendente de identificação</div>
          <div><strong>${active}</strong> filiais ativas</div>
          <div><strong>${inactive}</strong> filial inativa</div>
          <div><strong>${withData}</strong> filiais com dados operacionais</div>
        </div>
      </div>
      
      <hr style="border:0;border-top:1px solid #efefef;margin:0.8rem 0;" />
      
      <div style="font-size:12px;font-weight:bold;color:#444;margin-bottom:6px;">Status de Governança por Filial:</div>
      <div class="filiais-grid-container" style="display:grid;grid-template-columns:repeat(auto-fill, minmax(130px, 1fr));gap:6px;max-height:150px;overflow-y:auto;padding-right:4px;">
        ${branches.map(b => {
          let badgeColor = "background:#efefef;color:#666;";
          if (b.status === "INATIVA") {
            badgeColor = "background:#f3f4f6;color:#9ca3af;border: 1px dashed #d1d5db;text-decoration:line-through;";
          } else if (b.status === "PENDENTE_IDENTIFICACAO") {
            badgeColor = "background:#fff7ed;color:#c2410c;border: 1px solid #fed7aa;";
          } else if (b.statusDetalhado === "Dados operacionais" || b.statusDetalhado === "Dados operacionais em rede") {
            badgeColor = "background:#ecfdf5;color:#047857;border: 1px solid #a7f3d0;";
          } else if (b.statusDetalhado === "Token insuficiente") {
            badgeColor = "background:#fdf2f8;color:#be185d;border: 1px solid #fbcfe8;";
          }
          
          return `
            <div style="border-radius:4px;padding:6px;font-size:11px;${badgeColor} display:flex;flex-direction:column;justify-content:space-between;">
              <strong style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block;" title="${b.nome}">${b.nome}</strong>
              <span style="font-size:9px;margin-top:2px;opacity:0.9;">${b.codWeb ?? "COD WEB pendente"} • ${b.status}${b.statusDetalhado ? ` • ${b.statusDetalhado}` : ""}</span>
            </div>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

function renderExecutiveFuelsCard(container, fuelSummary, errorMessage) {
  if (errorMessage) {
    container.innerHTML = `
      <div class="panel">
        <h3>Volume e Mix de Combustíveis</h3>
        <div class="small exec-fallback-msg">${errorMessage}</div>
      </div>
    `;
    return;
  }

  if (!fuelSummary || fuelSummary.length === 0) {
    container.innerHTML = `
      <div class="panel">
        <h3>Volume e Mix de Combustíveis</h3>
        <div class="small">Sem dados de combustíveis no período.</div>
      </div>
    `;
    return;
  }

  const totalLitros = fuelSummary.reduce((acc, f) => acc + Number(f.litros || 0), 0);

  const formatDecimal = (num) => {
    const n = Number(num);
    if (!Number.isFinite(n)) return "0";
    return n.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  };

  container.innerHTML = `
    <div class="panel">
      <h3 style="margin-bottom: 12px;">Mix de Combustíveis (Volume Físico)</h3>
      <div style="font-size: 24px; font-weight: bold; color: #1e293b; margin-bottom: 15px;">
        ${formatDecimal(totalLitros)} <span style="font-size: 14px; font-weight: normal; color: #64748b;">L totais</span>
      </div>
      <div style="display: flex; flex-direction: column; gap: 12px;">
        ${fuelSummary.map((item) => {
          const part = Number(item.participacao || 0);
          let color = "#3b82f6";
          const name = (item.combustivelDisplay || item.combustivel || "").toUpperCase();
          if (name.includes("ALCOOL") || name.includes("ETANOL") || name.includes("ALC")) {
            color = "#10b981";
          } else if (name.includes("DIESEL") || name.includes("DSL")) {
            color = "#f59e0b";
          } else if (name.includes("GNV")) {
            color = "#8b5cf6";
          }
          
          return `
            <div>
              <div style="display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px;">
                <span style="font-weight: 600; color: #334155;">${item.combustivelDisplay || item.combustivel}</span>
                <span style="color: #64748b; font-size: 12px;">${formatDecimal(item.litros)} L (${part}%)</span>
              </div>
              <div style="width: 100%; height: 8px; border-radius: 4px; background: #e2e8f0; overflow: hidden;">
                <div style="width: ${part}%; background: ${color}; height: 100%; border-radius: 4px;"></div>
              </div>
            </div>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

function renderExecutiveStatusBar(container, snapshot, refreshing = false) {
  const statusNode = container.querySelector("#exec-status-bar");
  if (!statusNode) return;

  const lastUpdated = snapshot?.lastUpdated;
  const stale = isSnapshotStale(lastUpdated);
  const hasData = Boolean(snapshot?.kpis || snapshot?.dre || snapshot?.coverage || snapshot?.dataQuality || snapshot?.fuel);

  statusNode.innerHTML = `
    <div class="exec-status-bar">
      <div class="exec-status-meta">
        <span class="exec-status-label">Última atualização: <strong>${formatSnapshotDate(lastUpdated)}</strong></span>
        ${stale && hasData ? `<span class="exec-status-stale">Dados podem estar desatualizados.</span>` : ""}
        ${refreshing ? `<span class="exec-status-refreshing">Atualizando em segundo plano…</span>` : ""}
      </div>
      <button class="btn-primary exec-refresh-btn" type="button" id="execRefreshNowBtn" ${refreshing ? "disabled" : ""}>
        Atualizar agora
      </button>
    </div>
  `;
}

function renderExecutiveFromSnapshot(container, snapshot, { refreshing = false } = {}) {
  const kpiNode = container.querySelector("#exec-kpis");
  const dreNode = container.querySelector("#exec-dre");
  const qualityNode = container.querySelector("#exec-quality");
  const coverageNode = container.querySelector("#exec-coverage");
  const fuelsNode = container.querySelector("#exec-fuels");

  const hasKpis = Boolean(snapshot?.kpis);
  const hasDre = Boolean(snapshot?.dre);
  const hasQuality = Boolean(snapshot?.dataQuality);
  const hasCoverage = Boolean(snapshot?.coverage);
  const fuelSummary = fuelDataFromSnapshot(snapshot?.fuel);
  const hasFuel = Boolean(fuelSummary?.length);

  if (hasKpis) {
    renderKpiBarFromBackend(kpiNode, snapshot.kpis);
    if (APP_CONFIG.debugFinancialReconciliation) {
      console.log("[debugFinancialReconciliation] executive-kpi", {
        valorKPI: {
          receita: snapshot.kpis?.faturamento,
          despesa: snapshot.kpis?.despesasTotais,
          resultado: snapshot.kpis?.resultadoOperacional,
        },
      });
    }
  } else {
    kpiNode.innerHTML = `<div class="kpi-bar"><div class="kpi-item"><span class="kpi-label exec-fallback-msg">${friendlyErrorMessage(false)}</span></div></div>`;
  }

  if (hasDre) {
    renderDreFromBackend(dreNode, snapshot.dre);
  } else {
    dreNode.innerHTML = `<div class="panel"><span class="small exec-fallback-msg">${friendlyErrorMessage(false)}</span></div>`;
  }

  renderDataQualityCard(
    qualityNode,
    hasQuality ? snapshot.dataQuality : null,
    hasQuality ? null : friendlyErrorMessage(false)
  );
  renderNetworkCoverageCard(
    coverageNode,
    hasCoverage ? snapshot.coverage : null,
    hasCoverage ? null : friendlyErrorMessage(false)
  );
  renderExecutiveFuelsCard(
    fuelsNode,
    hasFuel ? fuelSummary : null,
    hasFuel ? null : friendlyErrorMessage(false)
  );

  renderExecutiveStatusBar(container, snapshot, refreshing);

  container.querySelector("#execAuditBtn")?.addEventListener("click", () => {
    window._execShowAudit(snapshot?.kpis);
  });
}

async function waitForSnapshotRefresh(filters, previousUpdated, generation) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < REFRESH_POLL_MAX_MS) {
    if (generation !== executiveRenderGeneration) return null;
    await new Promise((resolve) => setTimeout(resolve, REFRESH_POLL_MS));
    try {
      const snapshot = await fetchExecutiveSnapshot(filters || {});
      if (snapshot?.lastUpdated && snapshot.lastUpdated !== previousUpdated) {
        return snapshot;
      }
      if (snapshot?.fromSnapshot && snapshot?.lastUpdated && !previousUpdated) {
        return snapshot;
      }
    } catch (error) {
      console.warn("[executive] falha ao consultar snapshot durante refresh:", error);
    }
  }
  return null;
}

async function triggerExecutiveRefresh(container, filters, generation) {
  if (executiveRefreshInFlight) return;
  executiveRefreshInFlight = true;

  const statusSnapshot = { lastUpdated: container.dataset.lastUpdated || null };
  renderExecutiveStatusBar(container, statusSnapshot, true);

  let previousUpdated = container.dataset.lastUpdated || null;
  try {
    await postExecutiveRefresh(filters || {});
    const refreshed = await waitForSnapshotRefresh(filters, previousUpdated, generation);
    if (generation !== executiveRenderGeneration) return;
    if (refreshed) {
      container.dataset.lastUpdated = refreshed.lastUpdated || "";
      renderExecutiveFromSnapshot(container, refreshed, { refreshing: false });
    } else {
      renderExecutiveStatusBar(container, statusSnapshot, false);
    }
  } catch (error) {
    console.warn("[executive] refresh em background falhou:", error);
    renderExecutiveStatusBar(container, statusSnapshot, false);
  } finally {
    executiveRefreshInFlight = false;
  }
}

export async function renderExecutiveDashboard(container, data, filters, options = {}) {
  const generation = ++executiveRenderGeneration;
  const sales = data.sales?.resultados || data.sales?.data || [];
  const expenses = data.expenses?.resultados || data.expenses?.data || [];
  const accounts = data.accounts?.resultados || data.accounts?.data || [];
  const stock = data.stock?.resultados || data.stock?.data || [];

  metricsEngine.mount(sales, expenses, stock);

  const topn = computeTopN(sales, expenses);
  const alerts = computeAlerts(sales, expenses, accounts, stock);

  container.innerHTML = `
    <div class="executive-dashboard">
      <div id="exec-status-bar"></div>
      <div id="exec-kpis" class="exec-kpis-container"></div>

      <div style="display:flex;justify-content:flex-end;gap:0.5rem;margin-bottom:0.5rem;">
        <button class="btn-primary" style="background:#555;padding:0.4rem 0.8rem;font-size:12px;" id="execAuditBtn">
          Ver origem dos dados
        </button>
      </div>

      <div class="exec-grid">
        <div class="exec-main-col">
          <div id="exec-coverage"></div>
          <div id="exec-quality"></div>
          <div id="exec-alerts"></div>
          <div id="exec-dre"></div>
        </div>
        <div class="exec-side-col">
          <div id="exec-topn"></div>
          <div id="exec-fuels"></div>
        </div>
      </div>
    </div>
  `;

  const coverageNode = container.querySelector("#exec-coverage");
  const alertsNode = container.querySelector("#exec-alerts");
  const topnNode = container.querySelector("#exec-topn");
  const qualityNode = container.querySelector("#exec-quality");
  const fuelsNode = container.querySelector("#exec-fuels");
  const kpiNode = container.querySelector("#exec-kpis");
  const dreNode = container.querySelector("#exec-dre");

  const isOperationalLoading = sales.length === 0 && expenses.length === 0 && accounts.length === 0;

  if (isOperationalLoading) {
    alertsNode.innerHTML = `<div class="panel"><span class="small">Analisando faturamento e despesas para alertas…</span></div>`;
    topnNode.innerHTML = `<div class="panel"><h3>Top Faturamento / Despesas</h3><div class="small">Calculando ranking de filiais…</div></div>`;
  } else {
    renderAlerts(alertsNode, alerts);
    renderTopNBlocks(topnNode, topn);
  }

  kpiNode.innerHTML = `<div class="kpi-bar"><div class="kpi-item"><span class="kpi-label">Carregando snapshot executivo…</span></div></div>`;
  dreNode.innerHTML = `<div class="panel"><span class="small">Carregando DRE…</span></div>`;
  coverageNode.innerHTML = `<div class="panel"><span class="small">Carregando cobertura…</span></div>`;
  qualityNode.innerHTML = `<div class="panel"><span class="small">Carregando qualidade…</span></div>`;
  fuelsNode.innerHTML = `<div class="panel"><span class="small">Carregando combustíveis…</span></div>`;

  let snapshot = null;
  try {
    snapshot = await fetchExecutiveSnapshot(filters || {});
  } catch (error) {
    console.warn("[executive] falha ao carregar snapshot:", error);
    snapshot = {
      fromSnapshot: false,
      lastUpdated: null,
      kpis: null,
      dre: null,
      coverage: null,
      dataQuality: null,
      fuel: null,
      warnings: [],
    };
  }

  if (generation !== executiveRenderGeneration) return;

  container.dataset.lastUpdated = snapshot?.lastUpdated || "";
  renderExecutiveFromSnapshot(container, snapshot, { refreshing: !options.skipBackgroundRefresh });

  if (!container.dataset.execClickBound) {
    container.dataset.execClickBound = "1";
    container.addEventListener("click", (event) => {
      const target = event.target;
      if (target?.id === "execRefreshNowBtn") {
        triggerExecutiveRefresh(container, filters, executiveRenderGeneration);
      }
    });
  }

  const refreshKey = JSON.stringify(filters || {});
  const shouldAutoRefresh = !options.skipBackgroundRefresh && refreshKey !== lastAutoRefreshKey;
  if (shouldAutoRefresh) {
    lastAutoRefreshKey = refreshKey;
    triggerExecutiveRefresh(container, filters, generation);
  }
}
