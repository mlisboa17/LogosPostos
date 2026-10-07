import { apiClient } from "../services/apiClient.js";
import { formatCurrency, formatDate, formatTime, formatDateTime, recifeDateISO } from "../services/format.js";

const UNIDADES_URL = "/api/v1/cash-audit/unidades";
const FECHAMENTO_URL = "/api/v1/cash-audit/fechamento";
const RECEBIMENTOS_URL = "/api/v1/cash-audit/recebimentos";
let unidadesCarregadas = null;
const consultas = new WeakMap();

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

export function periodoPadrao(instante = new Date()) {
  const fim = recifeDateISO(instante);
  const inicio = new Date(`${fim}T12:00:00Z`);
  inicio.setUTCDate(inicio.getUTCDate() - 6);
  return { inicio: inicio.toISOString().slice(0, 10), fim };
}

export function diasDoPeriodo(inicio, fim) {
  const primeiro = new Date(`${inicio}T00:00:00Z`);
  const ultimo = new Date(`${fim}T00:00:00Z`);
  const quantidade = (ultimo - primeiro) / 86400000 + 1;
  if (!Number.isInteger(quantidade) || quantidade < 1 || quantidade > 31
      || primeiro.toISOString().slice(0, 10) !== inicio || ultimo.toISOString().slice(0, 10) !== fim) {
    throw new Error("O período deve ser válido e conter no máximo 31 dias.");
  }
  return Array.from({ length: quantidade }, (_, index) =>
    new Date(primeiro.getTime() + index * 86400000).toISOString().slice(0, 10)
  );
}

export function rankingFrentistas(dias) {
  const ranking = new Map();
  dias.forEach((dia) => {
    (dia.adquirentes || []).filter((item) => item.situacao === "ok").forEach((item) => {
      const investigacoes = [
        ...item.a_maior,
        ...item.pares_provaveis.map((par) => par.investigacao),
      ];
      investigacoes.forEach((inv) => {
        const atribuido = inv.atribuicao === "atribuido" && inv.frentista != null;
        const frentistas = atribuido
          ? [inv.frentista]
          : inv.atribuicao === "sugestao"
            ? [...new Set(inv.candidatos.map((c) => c.abastecimento.frentista).filter((id) => id != null))]
            : [];
        frentistas.forEach((id) => {
          const linha = ranking.get(id) || { frentista: id, atribuidos: 0, sugestoes: 0 };
          linha[atribuido ? "atribuidos" : "sugestoes"] += 1;
          ranking.set(id, linha);
        });
      });
    });
  });
  return [...ranking.values()].sort((a, b) =>
    (b.atribuidos + b.sugestoes) - (a.atribuidos + a.sugestoes) || a.frentista - b.frentista
  );
}

function renderAtribuicao(inv) {
  if (!inv) return '<span class="ca-muted">Sem atribuição</span>';
  const rotulo = inv.atribuicao === "atribuido"
    ? inv.frentista == null ? "Atribuído sem código de frentista" : `Frentista #${inv.frentista} · atribuído`
    : inv.atribuicao === "sugestao" ? `Sugestão (${inv.candidatos.length} candidatos)` : "Sem abastecimento";
  const candidatos = inv.candidatos.map((c) =>
    `<li>Frentista ${escapeHtml(c.abastecimento.frentista == null ? "não informado" : `#${c.abastecimento.frentista}`)}:
    ${escapeHtml(c.pontos)} pontos · ${escapeHtml(c.motivos.join(" · "))}</li>`
  ).join("");
  return `<strong>${escapeHtml(rotulo)}</strong>${candidatos ? `<ul class="ca-candidates">${candidatos}</ul>` : ""}`;
}

function renderDivergencia(dia, transacao, classificacao, tom, investigacao = null, cartao = null) {
  const momento = transacao.momento || "";
  const detalhePar = cartao
    ? `<p class="ca-hint">ERP: ${escapeHtml(formatTime(cartao.momento))} · ${safeCurrency(cartao.valor)}</p>`
    : "";
  return `<tr class="ca-row--${tom}">
    <td>${escapeHtml(formatDate(dia))}</td><td>${escapeHtml(formatTime(momento))}</td>
    <td class="ca-num">${safeCurrency(transacao.valor)}</td>
    <td>${escapeHtml(transacao.bandeira || transacao.administradora || "—")}</td>
    <td><span class="ca-chip ca-chip--${tom}">${classificacao}</span>${detalhePar}</td>
    <td>${renderAtribuicao(investigacao)}</td>
  </tr>`;
}

export function renderRecebimentos(dias, falhas = []) {
  const grupos = new Map();
  dias.forEach((dia) => (dia.adquirentes || []).forEach((item) => {
    const grupo = grupos.get(item.adquirente) || [];
    grupo.push({ dia: dia.dia, ...item });
    grupos.set(item.adquirente, grupo);
  }));
  const adquirentes = [...grupos.entries()].map(([nome, itens]) => {
    const ok = itens.filter((item) => item.situacao === "ok");
    const estados = [...new Set(itens.filter((item) => item.situacao !== "ok").map((item) => item.erro || item.situacao))];
    const avisos = estados.map((estado) =>
      `<span class="ca-badge ca-badge--pendente">${escapeHtml(estado)}</span>`
    ).join(" ");
    if (!ok.length) {
      return `<article class="ca-panel"><h4>${escapeHtml(nome)} ${avisos}</h4>
        <p class="ca-muted">Sem conciliação disponível. Nenhum dado estimado.</p></article>`;
    }
    const resumo = {
      casados: ok.reduce((sum, item) => sum + item.casados.quantidade, 0),
      total: ok.reduce((sum, item) => sum + Number(item.casados.total), 0),
      maior: ok.reduce((sum, item) => sum + item.a_maior.length, 0),
      menor: ok.reduce((sum, item) => sum + item.a_menor.length, 0),
      pares: ok.reduce((sum, item) => sum + item.pares_provaveis.length, 0),
    };
    const linhas = ok.map((item) => [
      ...item.a_menor.map((cartao) => renderDivergencia(item.dia, cartao, "A menor", "vermelho")),
      ...item.a_maior.map((inv) => renderDivergencia(item.dia, inv.transacao, "A maior", "laranja", inv)),
      ...item.pares_provaveis.map((par) => renderDivergencia(item.dia, par.investigacao.transacao, "Par provável", "amarelo", par.investigacao, par.cartao)),
    ].join("")).join("");
    const fontes = ok.map((item) =>
      `${formatDate(item.dia)}: ${item.proveniencia?.versao_regra || "—"} · ${formatDateTime(item.proveniencia?.executado_em)}`
    ).join(" | ");
    return `<article class="ca-panel"><h4>${escapeHtml(nome)} ${avisos}</h4>
      <p class="ca-hint">${ok.length} de ${itens.length} dias com conciliação disponível.</p>
      <div class="ca-kpis">
        <article class="ca-kpi"><span>Casados</span><strong>${resumo.casados}</strong><small>${safeCurrency(resumo.total)}</small></article>
        <article class="ca-kpi ca-kpi--laranja"><span>A maior</span><strong>${resumo.maior}</strong></article>
        <article class="ca-kpi ca-kpi--vermelho"><span>A menor</span><strong>${resumo.menor}</strong></article>
        <article class="ca-kpi"><span>Pares prováveis</span><strong>${resumo.pares}</strong></article>
      </div>
      ${linhas ? `<div class="ca-table-wrap"><table class="table-compact ca-receipts-table">
        <thead><tr><th>Data</th><th>Hora</th><th class="ca-num">Valor</th><th>Bandeira / forma</th><th>Classificação</th><th>Frentista / motivos</th></tr></thead>
        <tbody>${linhas}</tbody></table></div>` : '<p class="ca-ok">Sem divergências nos dias consultados.</p>'}
      <p class="ca-provenance">${escapeHtml(fontes)}</p>
    </article>`;
  }).join("");
  const ranking = rankingFrentistas(dias);
  const rankingHtml = ranking.length
    ? `<div class="ca-table-wrap"><table class="table-compact"><thead><tr><th>Frentista</th><th>Atribuídos</th><th>Sugestões</th></tr></thead>
      <tbody>${ranking.map((linha) => `<tr><td>#${escapeHtml(linha.frentista)}</td><td>${linha.atribuidos}</td><td>${linha.sugestoes}</td></tr>`).join("")}</tbody></table></div>`
    : '<p class="ca-muted">Sem atribuições ou sugestões nos dias disponíveis.</p>';
  return `<h3>Recebimentos eletrônicos</h3>
    ${falhas.length ? `<p class="ca-error" role="alert">Dias indisponíveis: ${escapeHtml(falhas.join(" · "))}. Totais e ranking são parciais.</p>` : ""}
    ${adquirentes || '<p class="ca-muted">Sem adquirentes disponíveis.</p>'}
    <section class="ca-panel"><h4>Ranking do período por frentista</h4>
      <p class="ca-hint">Sugestões não são atribuições confirmadas. Um recebimento conta uma vez por candidato; pares estão incluídos.</p>${rankingHtml}
    </section>`;
}

async function carregarRecebimentos(container, unidade, dias) {
  const respostas = [];
  const falhas = [];
  let proximo = 0;
  const worker = async () => {
    while (proximo < dias.length) {
      const dia = dias[proximo++];
      try {
        respostas.push(await apiClient.get(RECEBIMENTOS_URL, { params: { unidade, dia }, timeout: 200000 }));
      } catch (error) {
        falhas.push(`${formatDate(dia)}: ${error.message || "falha na consulta"}`);
      }
    }
  };
  await Promise.all([worker(), worker()]);
  respostas.sort((a, b) => a.dia.localeCompare(b.dia));
  container.querySelector("#caRecebimentos").innerHTML = renderRecebimentos(respostas, falhas);
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
  if (consultas.has(container)) return consultas.get(container);
  const consulta = executarConsulta(container);
  consultas.set(container, consulta);
  try {
    await consulta;
  } finally {
    consultas.delete(container);
  }
}

async function executarConsulta(container) {
  const unidade = container.querySelector("#caUnidade").value;
  const inicio = container.querySelector("#caInicio").value;
  const fim = container.querySelector("#caFim").value;
  const mensagem = container.querySelector("#caError");
  const conteudo = container.querySelector("#caResults");
  let dias;
  try {
    dias = diasDoPeriodo(inicio, fim);
  } catch (error) {
    showError(container, error);
    return;
  }
  container.querySelectorAll("#caFilters input, #caFilters select, #caFilters button").forEach((node) => { node.disabled = true; });
  mensagem.classList.add("hidden");
  conteudo.innerHTML = '<p class="ca-empty">Carregando auditoria…</p>';
  container.querySelector("#caRecebimentos").innerHTML = '<h3>Recebimentos eletrônicos</h3><p class="ca-muted">Carregando recebimentos…</p>';
  container.querySelector("#caProveniencia").textContent = "";
  const recebimentos = carregarRecebimentos(container, unidade, dias);
  try {
    const resultado = await apiClient.get(FECHAMENTO_URL, { params: { unidade, inicio, fim } });
    conteudo.innerHTML = `${renderKpis(resultado)}<section class="ca-panel"><h3>Caixas auditados</h3>${renderTabela(resultado)}</section>`;
    const proveniencia = resultado.proveniencia || {};
    container.querySelector("#caProveniencia").textContent =
      `Fonte: webPosto · Regra ${proveniencia.versao_regra || "—"} · Consultado em ${formatDateTime(proveniencia.executado_em)} (Recife)`;
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
  } finally {
    try {
      await recebimentos;
    } finally {
      container.querySelectorAll("#caFilters input, #caFilters select, #caFilters button").forEach((node) => { node.disabled = false; });
    }
  }
}

export async function renderCashAudit(container, { load = false } = {}) {
  if (!container.querySelector(".cash-audit")) {
    const { inicio, fim } = periodoPadrao();
    container.innerHTML = `
      <div class="cash-audit">
        <header class="ca-header"><div><h2>Fechamento do Dia</h2><p>Auditoria de caixa por unidade, período e modalidade.</p></div></header>
        <form id="caFilters" class="ca-filters">
          <label>Unidade<select id="caUnidade" required></select></label>
          <label>Data início<input id="caInicio" type="date" lang="pt-BR" value="${inicio}" required></label>
          <label>Data fim<input id="caFim" type="date" lang="pt-BR" value="${fim}" required></label>
          <button type="submit">Consultar</button>
        </form>
        <p id="caError" class="ca-error hidden" role="alert"></p>
        <div id="caResults"><p class="ca-empty">Selecione uma unidade para consultar.</p></div>
        <section id="caRecebimentos" class="ca-receipts" aria-live="polite"></section>
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
