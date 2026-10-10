import { apiClient } from "../services/apiClient.js";
import { formatDate } from "../services/format.js";

const PAINEL_URL = "/api/v1/cash-audit/painel-diretor";
const PLACAR_URL = "/api/v1/commercial/painel-resumo";

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function moeda(valor) {
  if (valor === null || valor === undefined) return "—";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })
    .format(Number(valor));
}

function dataHora(valor) {
  if (!valor) return "Sem execução registrada";
  const data = new Date(valor);
  if (Number.isNaN(data.getTime())) return "Data indisponível";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Recife",
  }).format(data);
}

function rotuloNivel(nivel) {
  return ({
    bronze: "Bronze",
    prata: "Prata",
    ouro: "Ouro",
    abaixo_bronze: "Abaixo de Bronze",
  })[nivel] || "Sem projeção";
}

function renderSaude(saude, papel) {
  const falhas = saude.unidades_com_falha || [];
  const avisos = saude.avisos || [];
  const estado = saude.estado || (saude.alerta_atraso || saude.execucao_sem_unidades || falhas.length
    ? "falha"
    : avisos.length ? "atencao" : "ok");
  const status = estado === "falha"
    ? saude.alerta_atraso
      ? "Atenção: execução atrasada"
      : saude.execucao_sem_unidades
        ? "Atenção: nenhuma unidade processada"
        : "Atenção: execução com falhas"
    : estado === "atencao" ? "Atenção: configuração pendente" : "Execução dentro do prazo";
  const estiloAviso = estado === "atencao"
    ? ' style="border-left-color:#f59e0b;background:rgba(120,53,15,.25)"'
    : "";
  const listaAvisos = avisos.length
    ? `<ul class="dd-health__warnings">${avisos.map((aviso) =>
      `<li>${escapeHtml(aviso.unidade_nome)} (${escapeHtml(aviso.unidade_codigo)}) · ${escapeHtml(aviso.adquirente)}: ${escapeHtml(aviso.mensagem)}</li>`
    ).join("")}</ul>`
    : "";
  return `<section class="dd-panel dd-health ${estado === "falha" ? "dd-health--alert" : estado === "atencao" ? "dd-health--warning" : "dd-health--ok"}"${estiloAviso} aria-label="Saúde do robô">
    <div><span class="dd-eyebrow">Saúde do robô</span>
      <h3>${status}</h3>
      <p>Última execução: ${escapeHtml(dataHora(saude.ultima_execucao))}</p>
      <p>Dia processado: ${saude.dia_processado ? escapeHtml(formatDate(saude.dia_processado)) : "Sem execução registrada"}</p>
      ${listaAvisos}
    </div>
    <dl class="dd-health__facts">
      <div><dt>Unidades processadas</dt><dd>${saude.ultima_execucao ? escapeHtml((saude.unidades_processadas || []).length) : "—"}</dd></div>
      <div><dt>Unidades com falha</dt><dd>${saude.ultima_execucao ? escapeHtml(falhas.length) : "—"}</dd></div>
      <div><dt>Resumo diário</dt><dd>${saude.resumo_gerado === null ? "—" : saude.resumo_gerado ? "Gerado" : "Falha"}</dd></div>
    </dl>
    ${papel === "diretor" ? '<button class="dd-refresh" type="button">Atualizar agora</button>' : ""}
  </section>`;
}

function renderAdquirentes(adquirentes) {
  if (!adquirentes?.length) return '<span class="dd-muted">Sem configuração registrada</span>';
  return `<ul class="dd-acquirers">${adquirentes.map((item) => `
    <li><span>${escapeHtml(item.nome)}</span>
      <span class="dd-acquirer dd-acquirer--${item.situacao === "ativo" ? "ok" : item.situacao === "pendente" ? "pending" : "error"}">${escapeHtml(item.situacao)}</span>
    </li>`).join("")}</ul>`;
}

function renderUnidade(unidade) {
  const fechamento = unidade.fechamento;
  const pendencias = unidade.pendencias_abertas;
  const linkPendencias = pendencias === null
    ? '<span class="dd-muted">Pendências indisponíveis</span>'
    : `<a class="dd-link" href="/app/financial?view=pendencias&amp;unidade=${encodeURIComponent(unidade.empresa_codigo)}">Ver ${escapeHtml(pendencias)} pendência(s)</a>`;
  return `<article class="dd-unit">
    <header><div><span class="dd-eyebrow">Unidade ${escapeHtml(unidade.empresa_codigo)}</span>
      <h3>${escapeHtml(unidade.nome)}</h3></div>
      <span class="dd-date">Último fechamento: ${fechamento?.dia ? escapeHtml(formatDate(fechamento.dia)) : "Sem dados"}</span>
    </header>
    <dl class="dd-metrics">
      <div><dt>Quebra</dt><dd>${moeda(fechamento?.quebra_total)}</dd></div>
      <div><dt>Faltas sem desconto</dt><dd>${fechamento ? `${escapeHtml(fechamento.faltas_sem_desconto)} · ${moeda(fechamento.faltas_sem_desconto_total)}` : "—"}</dd></div>
      <div><dt>Caixas parados</dt><dd>${fechamento ? `${escapeHtml(fechamento.caixas_parados)} · máx. ${escapeHtml(fechamento.caixas_parados_dias)} dia(s)` : "—"}</dd></div>
      <div><dt>Recebimentos a maior</dt><dd>${moeda(unidade.recebimentos_a_maior_total)}</dd></div>
      <div><dt>Recebimentos a menor</dt><dd>${moeda(unidade.recebimentos_a_menor_total)}</dd></div>
      <div><dt>Pendências abertas</dt><dd>${pendencias === null ? "—" : escapeHtml(pendencias)}</dd></div>
    </dl>
    <div class="dd-unit__footer"><div><span class="dd-eyebrow">Adquirentes</span>${renderAdquirentes(unidade.adquirentes)}</div>${linkPendencias}</div>
  </article>`;
}

function renderPlacar(placar) {
  const percentuais = placar.percentuais || {};
  const semProjecao = placar.postos_com_snapshot === 0;
  return `<section class="dd-panel">
    <div class="dd-section-heading"><div><span class="dd-eyebrow">Placar · ${escapeHtml(placar.mes)}</span><h3>Projeção de metas</h3></div>
      <span class="dd-muted">${escapeHtml(placar.postos_com_projecao)} de ${escapeHtml(placar.total_postos)} postos com projeção · ${escapeHtml(placar.postos_com_nivel)} com faixa projetada</span>
    </div>
    <div class="dd-goal-summary">${["bronze", "prata", "ouro"].map((nivel) => {
      const percentual = percentuais[nivel];
      return `<article class="dd-goal dd-goal--${nivel}">
        <span>${rotuloNivel(nivel)}</span><strong>${percentual === null ? "—" : `${escapeHtml(percentual)}%`}</strong>
        <small>${escapeHtml(placar.contagens?.[nivel] ?? "—")} posto(s) projetado(s)</small>
        ${percentual === null ? "" : `<span class="dd-progress"><i style="width:${Math.min(Math.max(Number(percentual), 0), 100)}%"></i></span>`}
      </article>`;
    }).join("")}</div>
    ${semProjecao ? '<p class="dd-muted">Sem snapshots persistidos para este período.</p>' : ""}
    <div class="dd-projections">${(placar.postos || []).map((posto) => `
      <div><strong>${escapeHtml(posto.nome)} (${escapeHtml(posto.empresa_codigo)})</strong>
        <span>${posto.com_snapshot ? `${rotuloNivel(posto.nivel_projetado)} · ${escapeHtml(Number(posto.projecao).toLocaleString("pt-BR"))} L` : "Sem snapshot persistido"}</span>
      </div>`).join("")}</div>
  </section>`;
}

export function renderPainelDiretor(dados, papel = "") {
  const unidades = dados?.unidades || [];
  return `<section class="director-dashboard">
    <header class="dd-header"><div><span class="dd-eyebrow">Visão executiva</span>
      <h2>Painel do Diretor</h2><p>Indicadores provenientes dos resultados persistidos; sem consulta ao ERP.</p></div>
      <span class="dd-stamp">Dados carregados ${escapeHtml(dataHora(new Date().toISOString()))}</span>
    </header>
    ${renderSaude(dados.saude_robo, papel)}
    <section class="dd-section"><div class="dd-section-heading"><div><span class="dd-eyebrow">Último dia fechado</span><h3>Hoje por unidade</h3></div></div>
      <div class="dd-units">${unidades.length ? unidades.map(renderUnidade).join("") : '<p class="dd-muted">Nenhuma unidade disponível no escopo.</p>'}</div>
    </section>
    ${renderPlacar(dados.placar)}
  </section>`;
}

export async function carregarPainelDiretor(container, { papel = "" } = {}) {
  container.innerHTML = '<section class="director-dashboard"><p class="dd-loading" role="status">Carregando painel com dados persistidos…</p></section>';
  try {
    const [dados, placar] = await Promise.all([
      apiClient.get(PAINEL_URL),
      apiClient.get(PLACAR_URL),
    ]);
    container.innerHTML = renderPainelDiretor({ ...dados, placar }, papel);
    const atualizar = container.querySelector(".dd-refresh");
    atualizar?.addEventListener("click", () => void carregarPainelDiretor(container, { papel }));
  } catch (error) {
    container.innerHTML = `<section class="director-dashboard"><p class="dd-error" role="alert">${escapeHtml(error.message || "Falha ao carregar painel.")}</p></section>`;
  }
}
