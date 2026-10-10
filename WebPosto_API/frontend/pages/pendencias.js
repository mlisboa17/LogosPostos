import { apiClient } from "../services/apiClient.js";
import { formatDate } from "../services/format.js";

const PENDENCIAS_URL = "/api/v1/cash-audit/pendencias";
const UNIDADES_URL = "/api/v1/cash-audit/unidades";
const consultas = new WeakMap();
const unidadesCarregadas = new WeakMap();
const deslocamentos = new WeakMap();
const unidadeInicialAplicada = new WeakMap();
const LIMITE = 50;

const ROTULOS_STATUS = {
  aberta: "Aberta",
  justificada: "Justificada",
  aprovada: "Aprovada",
  recusada: "Recusada",
};

const ROTULOS_TIPO = {
  fechamento_quebra: "Quebra",
  fechamento_nao_consolidado: "Não consolidado",
  fechamento_caixa_aberto: "Caixa em andamento",
  fechamento_falta_sem_desconto: "Falta sem desconto",
  fechamento_vale_divergente: "Vale divergente",
  fechamento_sangria_sem_destino: "Sangria sem destino",
  fechamento_sangria_alterada: "Sangria alterada",
  fechamento_despesa_sem_plano: "Despesa sem plano",
  fechamento_despesa_sem_descricao: "Despesa sem descrição",
  recebimento_a_maior: "Recebimento a maior",
  recebimento_a_menor: "Recebimento a menor",
  reincidencia_quebra: "Reincidência de quebra",
  reincidencia_sangria_alterada: "Reincidência de sangria alterada",
  reincidencia_recebimento_a_maior: "Reincidência de recebimento a maior",
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

function moeda(value) {
  if (value === null || value === undefined) return "—";
  return escapeHtml(new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(Number(value)));
}

function dataHora(value) {
  if (!value) return "—";
  const data = new Date(value);
  if (Number.isNaN(data.getTime())) return "—";
  return escapeHtml(new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Recife",
  }).format(data));
}

function rotuloTipo(tipo) {
  return ROTULOS_TIPO[tipo] || tipo.replaceAll("_", " ");
}

export function renderListaPendencias(itens, papel) {
  if (!itens?.length) return '<p class="pe-empty">Nenhuma pendência encontrada para os filtros.</p>';
  return itens.map((item) => {
    const historico = (item.historico || []).map((evento) => `
      <li><strong>${escapeHtml(evento.acao)}</strong> · ${escapeHtml(evento.usuario)} ·
        ${dataHora(evento.registrado_em)} · ${escapeHtml(ROTULOS_STATUS[evento.status_novo] || evento.status_novo)}
        ${evento.justificativa ? `<p>${escapeHtml(evento.justificativa)}</p>` : ""}
      </li>`).join("");
    const ultimaJustificativa = [...(item.historico || [])].reverse()
      .find((evento) => ["justificada", "justificativa_corrigida"].includes(evento.acao)
        && evento.justificativa)?.justificativa || "";
    const justificar = papel === "gerente" && ["aberta", "justificada"].includes(item.status)
      ? `<form class="pe-action" data-pendencia="${escapeHtml(item.id)}">
          <label>${item.status === "aberta" ? "Justificativa" : "Corrigir justificativa"}
            <textarea name="justificativa" minlength="10" maxlength="2000" required>${escapeHtml(ultimaJustificativa)}</textarea>
          </label>
          <button type="submit">${item.status === "aberta" ? "Justificar" : "Registrar correção"}</button>
        </form>`
      : "";
    const decidir = papel === "diretor" && item.status === "justificada"
      ? `<div class="pe-action" data-pendencia="${escapeHtml(item.id)}">
          <label>Observação da decisão<textarea name="observacao" maxlength="2000"></textarea></label>
          <button type="button" data-acao="aprovar">Aprovar</button>
          <button type="button" data-acao="recusar">Recusar</button>
        </div>`
      : "";
    return `<article class="pe-card">
      <header><div><strong>${escapeHtml(rotuloTipo(item.tipo))}</strong>
        <span class="pe-status pe-status--${escapeHtml(item.status)}">${escapeHtml(ROTULOS_STATUS[item.status] || item.status)}</span></div>
        <span class="pe-severity pe-severity--${escapeHtml(item.severidade)}">${escapeHtml(item.severidade)}</span></header>
      <dl><div><dt>Unidade</dt><dd>${escapeHtml(item.unidade)}</dd></div>
        <div><dt>Dia</dt><dd>${escapeHtml(formatDate(item.dia))}</dd></div>
        <div><dt>Valor</dt><dd>${moeda(item.valor)}</dd></div>
        <div><dt>Referência</dt><dd>${escapeHtml(item.referencia)}</dd></div>
        <div><dt>Responsável</dt><dd>${escapeHtml(item.responsavel || "—")}</dd></div></dl>
      <p>${escapeHtml(item.mensagem)}</p>
      ${justificar}${decidir}
      <details><summary>Histórico (${(item.historico || []).length})</summary>
        <ol>${historico}</ol></details>
    </article>`;
  }).join("");
}

export function renderPaginacaoPendencias(total, deslocamento) {
  if (total <= LIMITE) return "";
  const pagina = Math.floor(deslocamento / LIMITE) + 1;
  const paginas = Math.ceil(total / LIMITE);
  return `<nav class="pe-pagination" aria-label="Paginação de pendências">
    <button type="button" data-pagina="-1" ${pagina <= 1 ? "disabled" : ""}>Anterior</button>
    <span>Página ${pagina} de ${paginas} · ${total} pendências</span>
    <button type="button" data-pagina="1" ${pagina >= paginas ? "disabled" : ""}>Próxima</button>
  </nav>`;
}

async function carregarUnidades(container) {
  let pendente = unidadesCarregadas.get(container);
  if (!pendente) {
    pendente = apiClient.get(UNIDADES_URL);
    unidadesCarregadas.set(container, pendente);
  }
  try {
    return await pendente;
  } catch (error) {
    unidadesCarregadas.delete(container);
    throw error;
  }
}

async function carregarLista(container, papel, onChange) {
  const sequencia = (consultas.get(container) || 0) + 1;
  consultas.set(container, sequencia);
  const lista = container.querySelector("#peLista");
  const erro = container.querySelector("#peErro");
  erro.classList.add("hidden");
  lista.innerHTML = '<p class="pe-empty" role="status">Carregando pendências…</p>';
  const unidade = container.querySelector("#peUnidade").value;
  const status = container.querySelector("#peStatus").value;
  const tipo = container.querySelector("#peTipo").value.trim();
  const deslocamento = deslocamentos.get(container) || 0;
  const params = { status, limite: LIMITE, deslocamento };
  if (unidade) params.unidade = Number(unidade);
  if (tipo) params.tipo = tipo;
  try {
    const resposta = await apiClient.get(PENDENCIAS_URL, { params });
    if (consultas.get(container) !== sequencia) return;
    lista.innerHTML = `${renderListaPendencias(resposta.items, papel)}` +
      `${renderPaginacaoPendencias(resposta.total, deslocamento)}`;
    if (onChange) await onChange();
  } catch (error) {
    if (consultas.get(container) !== sequencia) return;
    lista.innerHTML = "";
    erro.textContent = error.message || "Falha ao carregar pendências.";
    erro.classList.remove("hidden");
  }
}

export async function contarPendenciasAbertas() {
  return apiClient.get(`${PENDENCIAS_URL}/contagem-abertas`);
}

export async function renderPendencias(container, { papel = "", unidadeInicial = "", onChange } = {}) {
  if (!container.querySelector(".pendencias")) {
    container.innerHTML = `
      <section class="pendencias">
        <header class="pe-header"><div><h2>Pendências</h2><p>Alertas vermelhos e laranjas da auditoria, com justificativa e histórico.</p></div>
          <button id="peAtualizar" type="button">Atualizar</button></header>
        <form id="peFiltros" class="pe-filters">
          <label>Unidade<select id="peUnidade"><option value="">Todas as unidades</option></select></label>
          <label>Status<select id="peStatus">
            <option value="aberta">Abertas</option><option value="justificada">Justificadas</option>
            <option value="aprovada">Aprovadas</option><option value="recusada">Recusadas</option>
            <option value="todas">Todos</option></select></label>
          <label>Tipo<input id="peTipo" maxlength="64" placeholder="Filtrar por tipo"></label>
          <button type="submit">Filtrar</button>
        </form>
        <p id="peErro" class="pe-error hidden" role="alert"></p>
        <div id="peLista" aria-live="polite"><p class="pe-empty">Selecione os filtros.</p></div>
      </section>`;
    container.querySelector("#peFiltros").addEventListener("submit", (event) => {
      event.preventDefault();
      deslocamentos.set(container, 0);
      void carregarLista(container, papel, onChange);
    });
    container.querySelector("#peAtualizar").addEventListener("click", () => {
      void carregarLista(container, papel, onChange);
    });
    container.querySelector("#peLista").addEventListener("click", async (event) => {
      const paginaBotao = event.target.closest("button[data-pagina]");
      if (paginaBotao && !paginaBotao.disabled) {
        const proximo = Math.max(0, (deslocamentos.get(container) || 0) + Number(paginaBotao.dataset.pagina) * LIMITE);
        deslocamentos.set(container, proximo);
        await carregarLista(container, papel, onChange);
        return;
      }
      const botao = event.target.closest("button[data-acao]");
      if (!botao) return;
      const action = botao.dataset.acao;
      const card = botao.closest("[data-pendencia]");
      const observacao = card.querySelector('[name="observacao"]').value.trim();
      botao.disabled = true;
      try {
        await apiClient.post(`${PENDENCIAS_URL}/${encodeURIComponent(card.dataset.pendencia)}/${action}`, {
          observacao: observacao || null,
        });
        deslocamentos.set(container, 0);
        await carregarLista(container, papel, onChange);
      } catch (error) {
        const erro = container.querySelector("#peErro");
        erro.textContent = error.message || "Falha ao decidir pendência.";
        erro.classList.remove("hidden");
      } finally {
        botao.disabled = false;
      }
    });
    container.querySelector("#peLista").addEventListener("submit", async (event) => {
      const form = event.target.closest("form[data-pendencia]");
      if (!form) return;
      event.preventDefault();
      const botao = form.querySelector("button[type=submit]");
      botao.disabled = true;
      try {
        await apiClient.post(
          `${PENDENCIAS_URL}/${encodeURIComponent(form.dataset.pendencia)}/justificar`,
          { justificativa: form.querySelector('[name="justificativa"]').value.trim() },
        );
        deslocamentos.set(container, 0);
        await carregarLista(container, papel, onChange);
      } catch (error) {
        const erro = container.querySelector("#peErro");
        erro.textContent = error.message || "Falha ao justificar pendência.";
        erro.classList.remove("hidden");
      } finally {
        botao.disabled = false;
      }
    });
  }
  const select = container.querySelector("#peUnidade");
  if (!select.options.length) {
    try {
      const unidades = await carregarUnidades(container);
      select.innerHTML = [
        '<option value="">Todas as unidades</option>',
        ...unidades.map((unidade) =>
          `<option value="${escapeHtml(unidade.empresa_codigo)}">${escapeHtml(unidade.nome)} (${escapeHtml(unidade.empresa_codigo)})</option>`
        ),
      ].join("");
    } catch (error) {
      const erro = container.querySelector("#peErro");
      erro.textContent = error.message || "Falha ao carregar unidades.";
      erro.classList.remove("hidden");
      return;
    }
  }
  const inicial = String(unidadeInicial || "");
  if (unidadeInicialAplicada.get(container) !== inicial) {
    select.value = inicial;
    unidadeInicialAplicada.set(container, inicial);
  }
  await carregarLista(container, papel, onChange);
}
