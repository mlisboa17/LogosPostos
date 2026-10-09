import { apiClient } from "../services/apiClient.js";
import { formatDate, formatDateTime, formatNumber, recifeDateISO } from "../services/format.js";

const POSTOS_URL = "/api/v1/commercial/postos";
const PLACAR_URL = "/api/v1/commercial/placar";
const TIMEOUT = 200000;
const TIMER_TV = 10 * 60 * 1000;
const consultas = new WeakMap();
const timers = new WeakMap();
const postosCarregados = new WeakMap();

const NIVEIS = [
  ["bronze", "Bronze"],
  ["prata", "Prata"],
  ["ouro", "Ouro"],
];

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function litros(value) {
  return value === null || value === undefined ? "sem dados" : `${formatNumber(value)} L`;
}

function percentual(value) {
  return value === null || value === undefined ? "sem dados" : `${formatNumber(value)}%`;
}

function rotuloNivel(value) {
  if (value === "abaixo_bronze") return "Abaixo de Bronze";
  return NIVEIS.find(([id]) => id === value)?.[1] || "Sem projeção";
}

function rotuloStatus(value) {
  return value === "acima" ? "acima do ritmo" : value === "abaixo" ? "abaixo do ritmo" : "ritmo indisponível";
}

export function periodoPadraoPlacar(instante = new Date()) {
  return recifeDateISO(instante).slice(0, 7);
}

export function opcoesMeses(instante = new Date()) {
  const [anoAtual, mesAtual] = periodoPadraoPlacar(instante).split("-").map(Number);
  const formatarMes = new Intl.DateTimeFormat("pt-BR", {
    month: "long",
    year: "numeric",
    timeZone: "America/Recife",
  });
  return Array.from({ length: 240 }, (_, indice) => {
    const data = new Date(Date.UTC(anoAtual, mesAtual - 1 - indice, 1, 12));
    const valor = `${data.getUTCFullYear()}-${String(data.getUTCMonth() + 1).padStart(2, "0")}`;
    const rotulo = formatarMes.format(data);
    return `<option value="${valor}">${escapeHtml(rotulo)}</option>`;
  }).join("");
}

export function consultarPlacar(posto, mes) {
  return apiClient.get(PLACAR_URL, {
    params: { posto, mes },
    timeout: TIMEOUT,
  });
}

function renderMetas(niveis = {}) {
  if (!Object.keys(niveis).length) {
    return '<p class="cs-muted">Metas não cadastradas; exibindo somente o realizado.</p>';
  }
  return `<div class="cs-goals">${NIVEIS.map(([id, nome]) => {
    const nivel = niveis[id];
    if (!nivel) return "";
    const progresso = Math.max(0, Math.min(100, Number(nivel.percentual) || 0));
    return `<article class="cs-goal cs-goal--${id}">
      <div class="cs-goal__title"><strong>${nome}</strong><span>${percentual(nivel.percentual)} da meta</span></div>
      <div class="cs-progress" role="progressbar" aria-label="Meta ${nome}" aria-valuenow="${progresso.toFixed(1)}" aria-valuemin="0" aria-valuemax="100">
        <span style="width:${progresso}%"></span>
      </div>
      <div class="cs-goal__facts"><span>Meta ${litros(nivel.meta)}</span><span>Faltam ${litros(nivel.faltante)}</span></div>
      <div class="cs-goal__facts"><span>Meta viva ${litros(nivel.meta_viva)}</span><span>Média ${litros(nivel.media_exigida)}</span></div>
      <div class="cs-goal__facts"><span>Meta viva por frentista ${litros(nivel.meta_viva_frentista)}</span></div>
    </article>`;
  }).join("")}</div>`;
}

function renderStatusDia(dia) {
  const ritmo = NIVEIS.map(([id, nome]) => {
    const nivel = dia.niveis?.[id];
    if (!nivel) return "";
    return `<small>${nome}: média ${escapeHtml(rotuloStatus(nivel.status_media))}; meta viva ${escapeHtml(rotuloStatus(nivel.status_viva))}</small>`;
  }).filter(Boolean).join("");
  return `<span class="cs-status ${dia.fechado ? "cs-status--fechado" : "cs-status--parcial"}">${dia.fechado ? "Fechado" : "Parcial"}</span>${ritmo}`;
}

function renderDiario(dias = []) {
  if (!dias.length) return '<p class="cs-muted">Nenhum abastecimento no período consultado.</p>';
  return `<div class="cs-table-wrap"><table class="cs-table">
    <thead><tr><th>Dia</th><th>Situação</th><th>Litros do dia</th><th>Acumulado</th>
      <th>Meta viva Bronze</th><th>Prata</th><th>Ouro</th><th>Atendimentos</th></tr></thead>
    <tbody>${dias.map((dia) => `<tr>
      <td>${escapeHtml(formatDate(dia.dia))}</td>
      <td>${renderStatusDia(dia)}</td>
      <td>${escapeHtml(litros(dia.litros))}</td><td>${escapeHtml(litros(dia.acumulado))}</td>
      ${NIVEIS.map(([id]) => `<td>${escapeHtml(litros(dia.niveis?.[id]?.meta_viva))}</td>`).join("")}
      <td>${escapeHtml(formatNumber(dia.atendimentos))}</td>
    </tr>`).join("")}</tbody>
  </table></div>`;
}

function renderFrentistas(frentistas = []) {
  if (!frentistas.length) return '<p class="cs-muted">Sem abastecimentos atribuídos a frentistas.</p>';
  return `<div class="cs-table-wrap"><table class="cs-table">
    <thead><tr><th>Posição</th><th>Frentista</th><th>Atendimentos</th><th>Abastecimentos</th>
      <th>Litros</th><th>Ticket (L/carro)</th><th>Meta (L/carro)</th><th>Ganho exigido (L/carro)</th><th>Mix aditivado</th></tr></thead>
    <tbody>${frentistas.map((item) => `<tr class="${item.abaixo_meta === true ? "cs-row--abaixo" : ""}">
      <td>${escapeHtml(formatNumber(item.ranking_ticket))}º</td>
      <td>${escapeHtml(item.nome || (item.codigo == null ? "Sem código" : `#${item.codigo}`))}<small>Volume: ${escapeHtml(formatNumber(item.ranking_volume))}º</small></td>
      <td>${escapeHtml(formatNumber(item.atendimentos))}</td><td>${escapeHtml(formatNumber(item.abastecimentos))}</td>
      <td>${escapeHtml(litros(item.litros))}</td><td>${escapeHtml(litros(item.ticket))}</td>
      <td>${escapeHtml(litros(item.meta_ticket))}</td><td>${escapeHtml(litros(item.ganho_bico))}</td>
      <td>${escapeHtml(percentual(item.percentual_aditivado))}</td>
    </tr>`).join("")}</tbody>
  </table></div>`;
}

function renderMix(mix = []) {
  if (!mix.length) return '<p class="cs-muted">Mix indisponível sem abastecimentos.</p>';
  return `<div class="cs-table-wrap"><table class="cs-table">
    <thead><tr><th>Combustível</th><th>Litros</th><th>Participação</th><th>Aditivado</th></tr></thead>
    <tbody>${mix.map((item) => `<tr>
      <td>${escapeHtml(item.nome || `Produto #${item.produto}`)}</td><td>${escapeHtml(litros(item.litros))}</td>
      <td>${escapeHtml(percentual(item.percentual))}</td>
      <td>${item.aditivado == null ? "Não classificado" : item.aditivado ? "Sim" : "Não"}</td>
    </tr>`).join("")}</tbody>
  </table></div>`;
}

export function renderPlacarResultado(placar) {
  const temMetas = Object.keys(placar.niveis || {}).length > 0;
  return `<div class="cs-summary">
    <article class="cs-card cs-card--highlight"><span>Acumulado até ${escapeHtml(formatDate(placar.dia))}</span><strong>${escapeHtml(litros(placar.acumulado))}</strong></article>
    <article class="cs-card"><span>Atendimentos distintos</span><strong>${escapeHtml(formatNumber(placar.atendimentos))}</strong>
      <small>${escapeHtml(formatNumber(placar.abastecimentos))} abastecimentos · ${escapeHtml(formatNumber(placar.atendimentos_fallback))} atendimentos estimados por abastecimento</small></article>
    <article class="cs-card"><span>Ticket médio</span><strong>${escapeHtml(litros(placar.ticket))}</strong></article>
    <article class="cs-card"><span>Projeção do mês</span><strong>${escapeHtml(litros(placar.projecao))}</strong>
      <small>${temMetas ? `No ritmo atual: ${escapeHtml(rotuloNivel(placar.nivel_projetado))}` : "Sem metas cadastradas"}</small></article>
  </div>
  <section class="cs-panel"><div class="cs-section-heading"><h3>Metas mensais e ritmo</h3><span>${escapeHtml(formatNumber(placar.dias_restantes))} dias restantes</span></div>
    ${renderMetas(placar.niveis)}</section>
  <section class="cs-panel"><h3>Realizado diário e meta viva</h3>${renderDiario(placar.diario)}</section>
  <section class="cs-panel"><h3>Frentistas · ticket médio e volume</h3>${renderFrentistas(placar.frentistas)}</section>
  <section class="cs-panel"><h3>Mix de combustíveis</h3>${renderMix(placar.mix)}</section>
  <footer class="cs-provenance">Regra ${escapeHtml(placar.proveniencia?.versao_regra || "—")} · Consultado em ${escapeHtml(formatDateTime(placar.proveniencia?.executado_em))} (Recife)</footer>`;
}

async function carregarPostos(container) {
  let pendente = postosCarregados.get(container);
  if (!pendente) {
    pendente = apiClient.get(POSTOS_URL, { timeout: 30000 });
    postosCarregados.set(container, pendente);
  }
  try {
    const postos = await pendente;
    const select = container.querySelector("#csPosto");
    select.innerHTML = postos.map((posto) =>
      `<option value="${escapeHtml(posto.empresa_codigo)}">${escapeHtml(posto.nome)}</option>`
    ).join("");
    select.value = String(postos.some((posto) => posto.empresa_codigo === 11495)
      ? 11495
      : postos[0]?.empresa_codigo || "");
  } catch (error) {
    postosCarregados.delete(container);
    throw error;
  }
}

async function carregarResultado(container) {
  const seq = (consultas.get(container) || 0) + 1;
  consultas.set(container, seq);
  const erro = container.querySelector("#csError");
  const resultado = container.querySelector("#csResults");
  const posto = container.querySelector("#csPosto").value;
  const mes = container.querySelector("#csMes").value;
  erro.classList.add("hidden");
  erro.textContent = "";
  resultado.innerHTML = '<p class="cs-muted" role="status">Consultando dados do webPosto…</p>';
  try {
    const placar = await consultarPlacar(Number(posto), mes);
    if (consultas.get(container) === seq) resultado.innerHTML = renderPlacarResultado(placar);
  } catch (error) {
    if (consultas.get(container) !== seq) return;
    resultado.innerHTML = "";
    erro.textContent = error.message || "Fonte indisponível. Tente novamente.";
    erro.classList.remove("hidden");
  }
}

export async function renderCommercialScore(container, { load = false, tv = false } = {}) {
  if (!container.querySelector(".commercial-score")) {
    container.innerHTML = `
      <div class="commercial-score">
        <header class="cs-header"><div><h2>Placar de Metas</h2><p>Volume realizado, ritmo mensal e desempenho por frentista.</p></div>
          <button id="csRefresh" type="button">Atualizar</button></header>
        <form id="csFilters" class="cs-filters">
          <label>Posto<select id="csPosto" required></select></label>
          <label>Mês<select id="csMes" lang="pt-BR" required>${opcoesMeses()}</select></label>
          <button type="submit">Consultar</button>
        </form>
        <p class="cs-explanation">O atendimento é uma venda distinta; quando o vínculo com a venda não está disponível, conta-se o abastecimento. Os dois totais são exibidos separadamente.</p>
        <p id="csError" class="cs-error hidden" role="alert"></p>
        <div id="csResults"><p class="cs-muted">Escolha o posto e o mês para consultar.</p></div>
      </div>`;
    container.querySelector("#csMes").value = periodoPadraoPlacar();
    container.querySelector("#csFilters").addEventListener("submit", (event) => {
      event.preventDefault();
      void carregarResultado(container);
    });
    container.querySelector("#csRefresh").addEventListener("click", () => void carregarResultado(container));
  }
  const root = container.querySelector(".commercial-score");
  root.classList.toggle("commercial-score--tv", tv);
  const posto = container.querySelector("#csPosto");
  if (!posto.options.length) {
    try {
      await carregarPostos(container);
    } catch (error) {
      const aviso = container.querySelector("#csError");
      aviso.textContent = error.message || "Não foi possível carregar os postos.";
      aviso.classList.remove("hidden");
      return;
    }
  }
  if (tv && !timers.has(container)) {
    timers.set(container, setInterval(() => {
      if (!container.closest(".view")?.classList.contains("hidden")) void carregarResultado(container);
    }, TIMER_TV));
  } else if (!tv && timers.has(container)) {
    clearInterval(timers.get(container));
    timers.delete(container);
  }
  if (load && posto.value) await carregarResultado(container);
}
