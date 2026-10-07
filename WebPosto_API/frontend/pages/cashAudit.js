import { apiClient } from "../services/apiClient.js";
import { formatCurrency, formatDate } from "../services/format.js";

const UNIDADES_URL = "/api/v1/cash-audit/unidades";
const FECHAMENTO_URL = "/api/v1/cash-audit/fechamento";
let unidadesCarregadas = null;

// Centros de custo da rede (V1/CENTROS_CUSTO, 2026-10-06)
const CENTROS_CUSTO = {
  7295: "Pista", 10529: "Pista GNV", 18713: "Fechamento", 21650: "Loja",
  22310: "Conveniência", 24886: "Conveniência 24h", 24423: "Food",
  23036: "Lubrificantes (inativo)", 23069: "Lubrificante", 24290: "Grupo A",
};
const ALERTA_ROTULO = {
  QUEBRA: "Quebra",
  NAO_CONSOLIDADO: "Não consolidado",
  CAIXA_ABERTO: "Em andamento",
  SANGRIA_SEM_DESTINO: "Sangria sem destino",
  SANGRIA_ALTERADA: "Sangria alterada",
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function safeCurrency(value) {
  return escapeHtml(formatCurrency(value));
}

function localDate(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function defaultPeriod() {
  const fim = new Date();
  const inicio = new Date(fim);
  inicio.setDate(inicio.getDate() - 6);
  return { inicio: localDate(inicio), fim: localDate(fim) };
}

function renderKpis(resultado) {
  const caixas = resultado?.caixas || [];
  const alertas = caixas.flatMap((item) => item.alertas || []);
  const quantidade = (codigo) => alertas.filter((alerta) => alerta.codigo === codigo).length;
  const quebra = Number(resultado?.quebra_total || 0);
  const kpi = (rotulo, valor, tom = "") =>
    `<article class="ca-kpi${tom ? ` ca-kpi--${tom}` : ""}"><span>${rotulo}</span><strong>${valor}</strong></article>`;
  const vermelhos = caixas.filter((item) => item.severidade === "vermelho").length;
  const naoConsolidados = caixas.filter((item) => item.caixa?.fechado && !item.caixa?.consolidado).length;
  const emAndamento = caixas.filter((item) => !item.caixa?.fechado).length;
  return `
    <div class="ca-kpis">
      ${kpi("Quebra do período (caixas fechados)", safeCurrency(quebra), quebra < -10 ? "vermelho" : "")}
      ${kpi("Caixas com alerta vermelho", `${vermelhos} <small>de ${caixas.length}</small>`, vermelhos ? "vermelho" : "")}
      ${kpi("Fechados não consolidados", naoConsolidados, naoConsolidados ? "laranja" : "")}
      ${kpi("Sangrias sem destino", quantidade("SANGRIA_SEM_DESTINO"), quantidade("SANGRIA_SEM_DESTINO") ? "vermelho" : "")}
      ${kpi("Sangrias alteradas", quantidade("SANGRIA_ALTERADA"), quantidade("SANGRIA_ALTERADA") ? "laranja" : "")}
      ${emAndamento ? kpi("Caixas em andamento", emAndamento) : ""}
    </div>
  `;
}

function renderDetalhes(auditoria) {
  const modalidades = auditoria.modalidades?.length
    ? auditoria.modalidades.map((item) => `
      <tr>
        <td>${escapeHtml(item.rotulo)}</td>
        <td class="ca-num">${safeCurrency(item.apresentado)}</td>
        <td class="ca-num">${safeCurrency(item.apurado)}</td>
        <td class="ca-num ${Number(item.diferenca) < -10 ? "ca-neg" : Number(item.diferenca) > 10 ? "ca-pos" : ""}">${safeCurrency(item.diferenca)}</td>
      </tr>`).join("")
    : '<tr><td colspan="4">Sem modalidades apresentadas.</td></tr>';
  const alertas = auditoria.alertas?.length
    ? `<ul>${auditoria.alertas.map((alerta) => `<li>${escapeHtml(alerta.mensagem)}</li>`).join("")}</ul>`
    : "<p>Sem alertas.</p>";
  return `
    <div class="ca-detail-grid">
      <div><h4>Modalidades</h4>
        <table class="table-compact"><thead><tr><th>Modalidade</th><th class="ca-num">Apresentado</th><th class="ca-num">Apurado</th><th class="ca-num">Diferença</th></tr></thead>
        <tbody>${modalidades}</tbody></table>
      </div>
      <div><h4>Alertas</h4>${alertas}</div>
    </div>`;
}

function renderChips(alertas) {
  if (!alertas?.length) return '<span class="ca-ok">OK</span>';
  const grupos = new Map();
  alertas.forEach((alerta) => {
    const atual = grupos.get(alerta.codigo) || { ...alerta, n: 0 };
    atual.n += 1;
    grupos.set(alerta.codigo, atual);
  });
  return [...grupos.values()].map((g) =>
    `<span class="ca-chip ca-chip--${escapeHtml(g.severidade)}" title="${escapeHtml(g.mensagem)}">` +
    `${escapeHtml(ALERTA_ROTULO[g.codigo] || g.codigo)}${g.n > 1 ? ` ×${g.n}` : ""}</span>`
  ).join("");
}

function renderTabela(resultado) {
  const caixas = resultado?.caixas || [];
  if (!caixas.length) return '<p class="ca-empty">Nenhum caixa encontrado no período.</p>';
  const linhas = caixas.map((auditoria, indice) => {
    const caixa = auditoria.caixa || {};
    const nivel = auditoria.severidade === "vermelho" || auditoria.severidade === "laranja"
      ? ` ca-row--${auditoria.severidade}`
      : "";
    const situacao = !caixa.fechado
      ? '<span class="ca-badge ca-badge--andamento">Em andamento</span>'
      : caixa.consolidado
        ? '<span class="ca-badge ca-badge--ok">Consolidado</span>'
        : '<span class="ca-badge ca-badge--pendente">Fechado</span>';
    const quebra = Number(auditoria.quebra || 0);
    const quebraHtml = !caixa.fechado
      ? '<span class="ca-muted">—</span>'
      : `<span class="${quebra < -10 ? "ca-neg" : quebra > 10 ? "ca-pos" : ""}">${safeCurrency(quebra)}</span>`;
    const centro = CENTROS_CUSTO[caixa.centro_custo] || caixa.centro_custo || "—";
    return `
      <tr class="ca-row${nivel}" data-ca-row="${indice}" tabindex="0" aria-expanded="false">
        <td>${escapeHtml(formatDate(caixa.data))}</td>
        <td>${escapeHtml(String(caixa.turno || "").replace(" TURNO", "º turno").replace("ºº", "º"))}</td>
        <td>${escapeHtml(centro)}</td>
        <td>${situacao}</td>
        <td class="ca-num">${quebraHtml}</td>
        <td><div class="ca-chips">${renderChips(auditoria.alertas)}</div></td>
      </tr>
      <tr class="ca-detail hidden" data-ca-detail="${indice}"><td colspan="6">${renderDetalhes(auditoria)}</td></tr>`;
  }).join("");
  return `
    <div class="ca-table-wrap"><table class="table-compact ca-table">
      <thead><tr><th>Data</th><th>Turno</th><th>Centro de custo</th><th>Situação</th><th class="ca-num">Quebra</th><th>Alertas</th></tr></thead>
      <tbody>${linhas}</tbody>
    </table></div>
    <p class="ca-hint">Clique em um caixa para ver as modalidades e os alertas em detalhe.</p>`;
}

function showError(container, error) {
  const message = error?.message || "Falha ao carregar a auditoria de caixa.";
  const node = container.querySelector("#caError");
  node.textContent = message;
  node.classList.remove("hidden");
}

async function loadUnidades(select) {
  if (!unidadesCarregadas) {
    unidadesCarregadas = apiClient.get(UNIDADES_URL);
  }
  try {
    const unidades = await unidadesCarregadas;
    select.innerHTML = unidades.map((unidade) =>
      `<option value="${escapeHtml(unidade.empresa_codigo)}">${escapeHtml(unidade.nome)} (${escapeHtml(unidade.empresa_codigo)})</option>`
    ).join("");
  } catch (error) {
    unidadesCarregadas = null;
    throw error;
  }
}

async function carregarAuditoria(container) {
  const unidade = container.querySelector("#caUnidade").value;
  const inicio = container.querySelector("#caInicio").value;
  const fim = container.querySelector("#caFim").value;
  const mensagem = container.querySelector("#caError");
  const conteudo = container.querySelector("#caResults");
  mensagem.classList.add("hidden");
  conteudo.innerHTML = '<p class="ca-empty">Carregando auditoria…</p>';
  try {
    const resultado = await apiClient.get(FECHAMENTO_URL, { params: { unidade, inicio, fim } });
    conteudo.innerHTML = `${renderKpis(resultado)}<section class="ca-panel"><h3>Caixas auditados</h3>${renderTabela(resultado)}</section>`;
    const proveniencia = resultado.proveniencia || {};
    container.querySelector("#caProveniencia").textContent =
      `Fonte: webPosto · Regra ${proveniencia.versao_regra || "—"} · Consultado em ${proveniencia.executado_em ? new Date(proveniencia.executado_em).toLocaleString("pt-BR") : "—"}`;
    container.querySelectorAll("[data-ca-row]").forEach((row) => {
      const toggle = () => {
        const index = row.dataset.caRow;
        const detail = container.querySelector(`[data-ca-detail="${index}"]`);
        const expanded = row.getAttribute("aria-expanded") === "true";
        row.setAttribute("aria-expanded", String(!expanded));
        detail.classList.toggle("hidden", expanded);
      };
      row.addEventListener("click", toggle);
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          toggle();
        }
      });
    });
  } catch (error) {
    conteudo.innerHTML = "";
    showError(container, error);
  }
}

export async function renderCashAudit(container, { load = false } = {}) {
  if (!container.querySelector(".cash-audit")) {
    const { inicio, fim } = defaultPeriod();
    container.innerHTML = `
      <div class="cash-audit">
        <header class="ca-header"><div><h2>Fechamento do Dia</h2><p>Auditoria de caixa por unidade, período e modalidade.</p></div></header>
        <form id="caFilters" class="ca-filters">
          <label>Unidade<select id="caUnidade" required></select></label>
          <label>Data início<input id="caInicio" type="date" value="${inicio}" required></label>
          <label>Data fim<input id="caFim" type="date" value="${fim}" required></label>
          <button type="submit">Consultar</button>
        </form>
        <p id="caError" class="ca-error hidden" role="alert"></p>
        <div id="caResults"><p class="ca-empty">Selecione uma unidade para consultar.</p></div>
        <footer id="caProveniencia" class="ca-provenance">Proveniência disponível após a consulta.</footer>
      </div>`;
    container.querySelector("#caFilters").addEventListener("submit", (event) => {
      event.preventDefault();
      void carregarAuditoria(container);
    });
  }
  const unidadeSelect = container.querySelector("#caUnidade");
  if (!unidadeSelect.options.length) {
    try {
      await loadUnidades(unidadeSelect);
    } catch (error) {
      showError(container, error);
      return;
    }
  }
  if (load && unidadeSelect.value) {
    await carregarAuditoria(container);
  }
}
