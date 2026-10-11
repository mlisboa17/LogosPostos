import { apiClient, buildQueryString } from "../services/apiClient.js";
import { formatarData as formatDate, formatarDataHora as formatDateTime, dataRecifeISO, somarDias, campoDataBR, ativarCamposDataBR, lerDataBR } from "../utils/datas.js";

const URL = "/api/v1/cash-audit/conferencia-recebimentos";
const consultas = new WeakMap();
const rotulos = { 1: "LANÇAR NO WEBPOSTO", 2: "ALTERAR NO WEBPOSTO", 3: "APURAR — LANÇAMENTO SEM LASTRO", 4: "CONFERIR À MÃO" };
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
function money(value) {
  return value === null || value === undefined ? "pendente"
    : esc(new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(value)));
}
function qtd(itens) {
  return `${itens.length} · ${money(itens.reduce((s, i) => s + Number(i.valor), 0))}`;
}
export function periodoConferencia(hoje = new Date()) {
  const fim = somarDias(dataRecifeISO(hoje), -2);
  return { inicio: somarDias(fim, -6), fim };
}
export function validarPeriodoConferencia(inicio, fim, hoje = new Date()) {
  const de = lerDataBR(inicio), ate = lerDataBR(fim);
  if (ate > periodoConferencia(hoje).fim) throw new Error("A data final deve ser até anteontem (hoje − 2 dias, Recife).");
  if (de > ate || de < somarDias(ate, -6)) throw new Error("O período deve conter de 1 a 7 dias.");
  return { inicio: de, fim: ate };
}
function detalhesPagamento(i) {
  const pagamentos = i.pagamentos?.length ? i.pagamentos : [null];
  return `<div class="cr-scroll"><table><caption>Detalhes por pagamento · ${esc(i.regra)}</caption>
    <thead><tr>${["Pagamento", "Adquirente / forma", "NSU / terminal (final)", "Lançamento / venda / caixa", "Hora / valor lançado / inclusão", "Abastecimento: hora / valor / bico / item / forma", "Responsável / identificação / nota / motivos"].map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>
    ${pagamentos.map(p => {
      const a = p?.abastecimento;
      const rs = p?.responsaveis?.length ? p.responsaveis : i.responsaveis || [];
      return `<tr><td>${p ? `1 · ${money(p.valor)} · ${esc(formatDateTime(p.momento))}` : "—"}</td>
      <td>${esc(p?.adquirente || "—")} / ${esc(p?.forma || "—")}</td><td>${esc(p?.nsu || "—")} / ${esc(p?.terminal || "—")}</td>
      <td>${esc(i.lancamento ?? "—")} / ${esc(i.venda ?? a?.venda_codigo ?? "—")} / ${esc(i.caixa ?? "—")}</td>
      <td>${i.momento_lancamento ? esc(formatDateTime(i.momento_lancamento)) : "—"} / ${i.valor_lancamento == null ? "—" : money(i.valor_lancamento)} / ${esc(i.tipo_inclusao || "—")}</td>
      <td>${a ? `${esc(formatDateTime(a.momento))} / ${money(a.valor)} / ${esc(a.bico ?? "—")} / ${esc(a.venda_item_codigo ?? "—")} / ${esc(p.forma_venda || "—")}` : "—"}</td>
      <td>${rs.length ? rs.map(r => `${esc(r.nome || "nome indisponível")} (${esc(r.codigo ?? "—")}) · ${esc(r.identificacao)} · nota ${esc(r.nota)} · ${esc((r.motivos || []).join(", "))}`).join("<br>") : esc(i.responsavel)}</td></tr>`;
    }).join("")}</tbody></table></div>`;
}
export function textoCorrecao(i) {
  return `Proposta — NÃO executada pelo Logos\nLançamento: ${i.lancamento ?? "não identificado"}; venda: ${i.venda ?? "não identificada"}; caixa: ${i.caixa ?? "sem caixa"}\n`
    + `${formatDateTime(i.momento)} · ${money(i.valor).replaceAll("&nbsp;", " ")}\n${i.de ?? "não identificado"} → ${i.para ?? "não identificado"}\n`
    + `${i.responsavel} · ${i.regra}\n${(i.evidencias || []).join("; ")}\n`
    + (i.pagamentos || []).map(p => `${formatDateTime(p.momento)} · ${money(p.valor)} · ${p.adquirente} ${p.forma || "—"} · NSU ${p.nsu || "—"} · terminal ${p.terminal || "—"}`).join("\n")
    + `\nNota: ${i.nota_certeza ?? 0}/100 (não é probabilidade). ${i.certeza}`;
}
function tabelaDiaria(dados) {
  const nomes = (dados.totais_adquirentes || []).map(t => t.adquirente);
  const colunas = nomes.map(n => `<th>Webposto ${esc(n)}</th><th>${esc(n)}</th><th>Dif.</th>`).join("");
  function valores(totais) {
    return nomes.map(n => {
      const t = totais.find(t => t.adquirente === n);
      return `<td>${money(t?.webposto)}</td><td>${money(t?.recebido)}</td><td>${money(t?.diferenca)}</td>`;
    }).join("");
  }
  return `<div class="cr-scroll"><table><caption>Visão diária por adquirente · Dif. = adquirente − webPosto</caption><thead><tr><th>Data</th>${colunas}<th>Diferença do dia</th></tr></thead>
    <tbody>${(dados.diario || []).map(d => `<tr><td>${esc(formatDate(d.dia))}${d.compensacao !== "sem compensacao" ? `<small>${esc(d.compensacao)}</small>` : ""}</td>${valores(d.adquirentes)}<td>${money(d.diferenca)}</td></tr>`).join("")}</tbody>
    <tfoot><tr><th>Total do período</th>${valores(dados.totais_adquirentes || [])}<th>${money(dados.diferenca_periodo)}</th></tr></tfoot></table></div>`;
}
export function renderConferencia(dados, { papel = "", adquirente = "Todas", somenteLeitura = false } = {}) {
  const itens = (dados.itens || []).filter(i => adquirente === "Todas" || i.adquirente === adquirente);
  const editar = !somenteLeitura && ["diretor", "gerente"].includes(papel);
  const formas = (dados.formas || []).filter(f => adquirente === "Todas" || f.adquirente === adquirente);
  return `<header><h2>Conferência de recebimentos · Unidade ${esc(dados.unidade)}</h2>
    <p>${esc(formatDate(dados.inicio))} a ${esc(formatDate(dados.fim))}</p>
    <strong>Conferido: ${esc(dados.conferidos.quantidade)} · ${money(dados.conferidos.total)}</strong>
    <p>O Logos recomenda; não lança, não altera e não exclui no ERP (ADR-003).</p></header>
    ${(dados.avisos || []).length ? `<details open><summary>Lacunas / fontes pendentes</summary><ul>${dados.avisos.map(a => `<li>${esc(a)}</li>`).join("")}</ul></details>` : ""}
    ${tabelaDiaria(dados)}
    <div class="cr-tabs" role="group" aria-label="Adquirentes">${["Todas", ...new Set((dados.formas || []).map(f => f.adquirente))].map(a => `<button type="button" data-adquirente="${esc(a)}" aria-pressed="${a === adquirente}">${esc(a)}</button>`).join("")}</div>
    <div class="cr-scroll"><table><caption>Por forma · adquirente × webPosto</caption><thead><tr><th>Adquirente</th><th>Forma</th><th>Adquirente · qtd / R$</th><th>webPosto · qtd / R$</th><th>Diferença</th></tr></thead>
    <tbody>${formas.map(f => `<tr><td>${esc(f.adquirente)}</td><td>${esc(f.resumo.forma)}</td><td>${esc(f.resumo.portal.quantidade)} · ${money(f.resumo.portal.total)}</td><td>${esc(f.resumo.webposto.quantidade)} · ${money(f.resumo.webposto.total)}</td><td>${money(f.resumo.diferenca)}</td></tr>`).join("")}</tbody></table></div>
    ${Object.entries(rotulos).map(([grupo, nome]) => {
      const lista = itens.filter(i => i.grupo === Number(grupo) && i.conferencia !== "conferido");
      return `<section class="cr-group cr-group--${grupo}"><h3>${grupo}. ${nome} — ${qtd(lista)}</h3>${lista.map(i => `
        <article data-item="${esc(i.id)}"><strong>1 · ${money(i.valor)} · ${esc(formatDateTime(i.momento))} · ${esc(i.adquirente)}</strong>
          <p>${esc(i.de || "")} → ${esc(i.para || i.forma)}</p><p>${esc(i.responsavel)} · ${esc(i.regra)} ${i.reincidente ? `<b>REINCIDENTE · ${esc(i.reincidencia_quantidade)} · ${money(i.reincidencia_total)}</b>` : ""}</p>
          <p>${esc(i.motivo)}</p>${detalhesPagamento(i)}<details><summary>Evidências</summary>${(i.evidencias || []).map(e => `<p>${esc(e)}</p>`).join("")}<p>NSU: ${esc(i.nsu || "—")}</p></details>
          ${i.grupo === 4 && editar ? '<label>Observação<textarea name="observacao" maxlength="2000" required></textarea></label><button type="button" data-decisao="conferido">Conferido</button><button type="button" data-decisao="nao_encontrado">Não encontrado</button>' : ""}
        </article>`).join("") || "<p>Nenhuma ocorrência neste grupo.</p>"}</section>`;
    }).join("")}
    <section><h3>Correções prontas — ${qtd(itens.filter(i => i.grupo === 2))}</h3>
      ${itens.filter(i => i.grupo === 2).map(i => `<article data-item="${esc(i.id)}"><p>${esc(i.de)} → ${esc(i.para)} · ${money(i.valor)}</p>
        <p>Lançamento ${esc(i.lancamento ?? "não identificado")} · Venda ${esc(i.venda ?? "não identificada")} · Caixa ${esc(i.caixa ?? "sem caixa")}</p><p>${esc(i.responsavel)} · Nota ${esc(i.nota_certeza ?? 0)}/100 (não é probabilidade) · ${esc(i.certeza)}</p>
        <p>Status: ${esc(i.proposta_status)}</p><button type="button" data-copiar="${esc(i.id)}">Copiar proposta</button>
        ${editar && i.proposta_status === "proposta" ? '<label>Observação<textarea name="observacao" required maxlength="2000"></textarea></label><button type="button" data-decisao="executada pelo gerente">Executada pelo gerente</button><button type="button" data-decisao="descartada">Descartada</button>' : ""}
        ${i.observacao ? `<p>${esc(i.observacao)}</p>` : ""}</article>`).join("")}
    </section><section><h3>Conferências manuais registradas</h3>${itens.filter(i => i.conferencia === "conferido").map(i => `<p>${esc(i.responsavel)} · 1 · ${money(i.valor)} · ${esc(i.observacao)}</p>`).join("")}</section>`;
}

export async function renderConferenciaRecebimentos(container, { papel = "", unidadeInicial = null, somenteLeitura = false } = {}) {
  const token = Symbol();
  consultas.set(container, token);
  try {
    const unidades = await apiClient.get("/api/v1/cash-audit/unidades");
    if (consultas.get(container) !== token) return;
    const { inicio, fim } = periodoConferencia();
    container.innerHTML = `<section class="conferencia-recebimentos"><form class="cr-filters">
      <label>Unidade<select name="unidade">${unidades.map(u => `<option value="${u.empresa_codigo}" ${Number(unidadeInicial) === u.empresa_codigo ? "selected" : ""}>${esc(u.nome)}</option>`).join("")}</select></label>
      <label>Início${campoDataBR({ nome: "inicio", valor: inicio })}</label><label>Fim${campoDataBR({ nome: "fim", valor: fim })}</label>
      <button type="submit">Consultar dados gravados</button></form><p class="cr-message" role="status"></p><div class="cr-result"></div></section>`;
    const form = container.querySelector("form");
    ativarCamposDataBR(form);
    const result = container.querySelector(".cr-result");
    const message = container.querySelector(".cr-message");
    let dados, filtro = "Todas", params;
    function pintar() { result.innerHTML = renderConferencia(dados, { papel, adquirente: filtro, somenteLeitura }); }
    async function carregar() {
      const request = Symbol();
      consultas.set(container, request);
      result.innerHTML = "";
      message.textContent = "Carregando resultados gravados…";
      const selecionados = Object.fromEntries(new FormData(form));
      try {
        Object.assign(selecionados, validarPeriodoConferencia(selecionados.inicio, selecionados.fim));
        const resposta = await apiClient.get(URL, { params: selecionados });
        if (consultas.get(container) !== request) return;
        dados = resposta;
        params = selecionados;
        pintar();
        message.innerHTML = `<a href="${URL}.xlsx${esc(buildQueryString(params))}">Baixar planilha de conferência</a>`;
      } catch (e) {
        if (consultas.get(container) === request) message.textContent = e.message;
      }
    }
    form.addEventListener("submit", e => { e.preventDefault(); void carregar(); });
    result.addEventListener("click", async e => {
      const aba = e.target.closest("[data-adquirente]");
      if (aba) { filtro = aba.dataset.adquirente; pintar(); return; }
      const copiar = e.target.closest("[data-copiar]");
      const button = e.target.closest("[data-decisao]");
      try {
        if (copiar) {
          await navigator.clipboard.writeText(textoCorrecao(dados.itens.find(i => i.id === copiar.dataset.copiar)));
          message.textContent = "Proposta copiada; nenhuma alteração no ERP.";
        }
        if (button && !somenteLeitura) {
          const article = button.closest("[data-item]");
          const observacao = article.querySelector("textarea").value.trim();
          if (!observacao) throw new Error("Informe uma observação antes de registrar.");
          const i = dados.itens.find(i => i.id === article.dataset.item);
          button.disabled = true;
          await apiClient.post(`${URL}/${i.id}`, { body: {
            unidade: dados.unidade, dia: i.momento.slice(0, 10), decisao: button.dataset.decisao, observacao,
          } });
          await carregar();
        }
      } catch (erro) {
        message.textContent = erro.message;
        if (button) button.disabled = false;
      }
    });
    await carregar();
  } catch (erro) {
    container.innerHTML = `<p role="alert">${esc(erro.message)}</p>`;
  }
}
