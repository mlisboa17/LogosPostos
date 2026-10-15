import { apiClient } from "../services/apiClient.js";
import { ativarCamposDataBR, campoDataBR, dataRecifeISO, formatarData, formatarDataHora, lerDataBR, somarDias } from "../utils/datas.js";

const URL = "/api/v1/cash-audit/lancamentos-logos";
const consultas = new WeakMap();
const operacoes = new WeakSet();
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[c]);

function detalhes(item) {
  return `<p>Valor: ${esc(item.valor)} · Caixa: ${esc(item.caixa)} · Frentista: ${esc(item.frentista)}</p>
    <p class="ll-texto">${esc(item.texto)}</p>
    <details><summary>Evidências</summary><ul>${(item.evidencias || []).map(e => `<li>${esc(e)}</li>`).join("") || "<li>Sem evidências informadas.</li>"}</ul></details>`;
}

export function renderLancamentos(dados, { papel = "", somenteLeitura = false } = {}) {
  const escrever = papel === "diretor" && !somenteLeitura;
  return `${!escrever ? "<p>Somente leitura. Apenas o diretor pode lançar, recusar ou desfazer.</p>" : ""}
    <section class="cr-group"><h3>Propostas</h3>${dados.propostas.map(p => `<article>
      <h4>Unidade ${esc(p.unidade)} · ${esc(formatarData(p.dia))}</h4>
      <p>NSU final: ${esc(p.nsu_final ?? "—")}</p>${detalhes(p)}
      ${!p.elegivel ? `<p>Bloqueado: ${esc(p.motivo || "Proposta não elegível.")}</p>` : p.motivo ? `<p>${esc(p.motivo)}</p>` : ""}
      ${escrever && p.elegivel === true ? `<button type="button" data-acao="aprovar" data-id="${esc(p.id)}">Lançar</button>
        <button type="button" data-acao="recusar" data-id="${esc(p.id)}">Não lançar</button>` : ""}
    </article>`).join("") || "<p>Nenhuma proposta para esta unidade e data.</p>"}</section>
    <section class="cr-group"><h3>Histórico</h3>${dados.historico.map(h => `<article>
      <h4>${esc(h.estado)} · ${esc(formatarDataHora(h.instante))}</h4>
      <p>Ação: ${esc(h.acao_id)} · Lançamento criado: ${esc(h.id_criado ?? "—")}</p>${detalhes(h)}
      ${escrever && h.estado === "confirmado" ? `<button type="button" data-acao="desfazer" data-id="${esc(h.acao_id)}">Desfazer</button>` : ""}
    </article>`).join("") || "<p>Nenhuma ação registrada para esta unidade e data.</p>"}</section>`;
}

export async function renderLancamentosLogos(container, { papel = "", unidadeInicial = null, somenteLeitura = false } = {}) {
  if (operacoes.has(container)) return;
  const token = Symbol();
  consultas.set(container, token);
  container.innerHTML = '<p role="status">Carregando unidades…</p>';
  try {
    const unidades = await apiClient.get("/api/v1/cash-audit/unidades");
    if (consultas.get(container) !== token) return;
    if (!Array.isArray(unidades) || !unidades.length) throw new Error("Nenhuma unidade disponível no seu escopo.");
    const dia = somarDias(dataRecifeISO(), -1);
    container.innerHTML = `<section class="conferencia-recebimentos lancamentos-logos">
      <header><h2>Lançamentos do Logos</h2><p>Revise o texto e as evidências antes de lançar.</p></header>
      <form class="cr-filters"><label>Unidade<select name="unidade">${unidades.map(u => `<option value="${esc(u.empresa_codigo)}" ${Number(unidadeInicial) === Number(u.empresa_codigo) ? "selected" : ""}>${esc(u.nome)}</option>`).join("")}</select></label>
      <label>Data${campoDataBR({ nome: "dia", id: "lancamentosLogosDia", valor: dia })}</label>
      <button type="submit">Consultar</button></form>
      <p class="ll-message" role="status" aria-live="polite"></p><div class="ll-result"></div></section>`;
    const form = container.querySelector("form");
    const result = container.querySelector(".ll-result");
    const message = container.querySelector(".ll-message");
    ativarCamposDataBR(form);
    let dados, params;
    const atual = () => consultas.get(container) === token;
    const informar = (texto, erro = false) => {
      message.setAttribute("role", erro ? "alert" : "status");
      message.textContent = texto;
    };
    const bloquear = flag => {
      for (const control of container.querySelectorAll("button, input, select")) control.disabled = flag;
    };
    async function carregar(selecionados, sucesso = "") {
      dados = null;
      result.innerHTML = "";
      informar("Carregando lançamentos…");
      const resposta = await apiClient.get(URL, { params: selecionados });
      if (!atual()) return;
      if (!Array.isArray(resposta?.propostas) || !Array.isArray(resposta?.historico)) {
        throw new Error("Resposta inválida ao consultar lançamentos.");
      }
      result.innerHTML = renderLancamentos(resposta, { papel, somenteLeitura });
      dados = resposta;
      params = selecionados;
      informar(sucesso);
    }
    async function consultar() {
      if (operacoes.has(container)) return;
      operacoes.add(container);
      try {
        const selecionados = {
          unidade: Number(form.elements.unidade.value),
          dia: lerDataBR(form.elements.dia.value),
        };
        if (!unidades.some(u => Number(u.empresa_codigo) === selecionados.unidade)) throw new Error("Selecione uma unidade disponível.");
        bloquear(true);
        await carregar(selecionados);
      } catch (error) {
        if (atual()) {
          dados = null;
          result.innerHTML = "";
          informar(error.message || "Falha ao consultar lançamentos.", true);
        }
      } finally {
        operacoes.delete(container);
        if (atual()) bloquear(false);
      }
    }
    form.addEventListener("submit", event => { event.preventDefault(); void consultar(); });
    result.addEventListener("click", async event => {
      const button = event.target.closest("[data-acao]");
      if (!button || button.disabled || !atual() || operacoes.has(container)) return;
      if (papel !== "diretor" || somenteLeitura) {
        informar("Somente o diretor pode registrar ações.", true);
        return;
      }
      const { acao, id } = button.dataset;
      const permitido = acao === "desfazer"
        ? dados?.historico.some(h => h.acao_id === id && h.estado === "confirmado")
        : ["aprovar", "recusar"].includes(acao) && dados?.propostas.some(p =>
          p.id === id && p.elegivel === true && Number(p.unidade) === params.unidade && p.dia === params.dia);
      if (!permitido) { informar("Ação indisponível para este registro.", true); return; }
      operacoes.add(container);
      bloquear(true);
      informar("Registrando ação…");
      let registrada = false;
      try {
        const resposta = await apiClient.post(`${URL}/${encodeURIComponent(id)}/${acao}`, { ...params });
        registrada = true;
        if (!atual()) return;
        await carregar(params, resposta.mensagem || `Estado: ${resposta.estado}`);
      } catch (error) {
        if (atual()) {
          // Após uma falha, consulte o estado persistido antes de tentar escrever novamente.
          dados = null;
          result.innerHTML = "";
          informar(`${registrada ? "Ação registrada, mas não foi possível atualizar a lista. " : ""}${error.message || "Falha ao registrar ação."} Consulte novamente antes de continuar.`, true);
        }
      } finally {
        operacoes.delete(container);
        if (atual()) bloquear(false);
      }
    });
    await consultar();
  } catch (error) {
    if (consultas.get(container) === token) container.innerHTML = `<p role="alert">${esc(error.message || "Falha ao carregar lançamentos.")}</p>`;
  }
}
