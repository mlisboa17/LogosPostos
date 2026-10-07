import { apiClient } from "../services/apiClient.js";
import { formatCurrency, formatDate } from "../services/format.js";

const UNIDADES_URL = "/api/v1/cash-audit/unidades";
const FECHAMENTO_URL = "/api/v1/cash-audit/fechamento";
let unidadesCarregadas = null;

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
  return `
    <div class="ca-kpis">
      <article class="ca-kpi"><span>Quebra total do período</span><strong>${safeCurrency(resultado?.quebra_total)}</strong></article>
      <article class="ca-kpi"><span>Caixas com alerta vermelho</span><strong>${caixas.filter((item) => item.severidade === "vermelho").length}</strong></article>
      <article class="ca-kpi"><span>Caixas não consolidados</span><strong>${caixas.filter((item) => !item.caixa?.consolidado).length}</strong></article>
      <article class="ca-kpi"><span>Sangrias sem destino</span><strong>${quantidade("SANGRIA_SEM_DESTINO")}</strong></article>
      <article class="ca-kpi"><span>Sangrias alteradas</span><strong>${quantidade("SANGRIA_ALTERADA")}</strong></article>
    </div>
  `;
}

function renderDetalhes(auditoria) {
  const modalidades = auditoria.modalidades?.length
    ? auditoria.modalidades.map((item) => `
      <tr>
        <td>${escapeHtml(item.rotulo)}</td>
        <td>${safeCurrency(item.apresentado)}</td>
        <td>${safeCurrency(item.apurado)}</td>
        <td>${safeCurrency(item.diferenca)}</td>
      </tr>`).join("")
    : '<tr><td colspan="4">Sem modalidades apresentadas.</td></tr>';
  const alertas = auditoria.alertas?.length
    ? `<ul>${auditoria.alertas.map((alerta) => `<li>${escapeHtml(alerta.mensagem)}</li>`).join("")}</ul>`
    : "<p>Sem alertas.</p>";
  return `
    <div class="ca-detail-grid">
      <div><h4>Modalidades</h4>
        <table class="table-compact"><thead><tr><th>Modalidade</th><th>Apresentado</th><th>Apurado</th><th>Diferença</th></tr></thead>
        <tbody>${modalidades}</tbody></table>
      </div>
      <div><h4>Alertas</h4>${alertas}</div>
    </div>`;
}

function renderTabela(resultado) {
  const caixas = resultado?.caixas || [];
  if (!caixas.length) return '<p class="ca-empty">Nenhum caixa encontrado no período.</p>';
  const linhas = caixas.map((auditoria, indice) => {
    const caixa = auditoria.caixa || {};
    const nivel = auditoria.severidade === "vermelho" || auditoria.severidade === "laranja"
      ? ` ca-row--${auditoria.severidade}`
      : "";
    const situacao = !caixa.fechado ? "Aberto" : caixa.consolidado ? "Consolidado" : "Fechado";
    const resumo = auditoria.alertas?.length
      ? auditoria.alertas.map((alerta) => alerta.mensagem).join(" · ")
      : "Sem alertas";
    return `
      <tr class="ca-row${nivel}" data-ca-row="${indice}" tabindex="0" aria-expanded="false">
        <td>${escapeHtml(formatDate(caixa.data))}</td><td>${escapeHtml(caixa.turno)}</td>
        <td>${escapeHtml(caixa.centro_custo ?? "—")}</td><td>${situacao}</td>
        <td>${safeCurrency(auditoria.quebra)}</td><td>${escapeHtml(resumo)}</td>
      </tr>
      <tr class="ca-detail hidden" data-ca-detail="${indice}"><td colspan="6">${renderDetalhes(auditoria)}</td></tr>`;
  }).join("");
  return `
    <div class="ca-table-wrap"><table class="table-compact ca-table">
      <thead><tr><th>Data</th><th>Turno</th><th>Centro de custo</th><th>Situação</th><th>Quebra (R$)</th><th>Alertas</th></tr></thead>
      <tbody>${linhas}</tbody>
    </table></div>`;
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
      `Regra ${proveniencia.versao_regra || "—"} · Executado em ${proveniencia.executado_em || "—"}`;
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
