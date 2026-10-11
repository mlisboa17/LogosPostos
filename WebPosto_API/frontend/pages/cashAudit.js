import { apiClient } from "../services/apiClient.js";
import { formatCurrency } from "../services/format.js";
import { formatarData as formatDate, formatarHora as formatTime, formatarDataHora as formatDateTime, dataRecifeISO as recifeDateISO, campoDataBR, ativarCamposDataBR, lerDataBR } from "../utils/datas.js";

const UNIDADES_URL = "/api/v1/cash-audit/unidades";
const FECHAMENTO_URL = "/api/v1/cash-audit/fechamento";
const RECEBIMENTOS_URL = "/api/v1/cash-audit/recebimentos";
const REINCIDENCIA_URL = "/api/v1/cash-audit/reincidencia";
const RELATORIO_URL = "/api/v1/cash-audit/relatorio-caixa";
const SINCRONIZAR_URL = "/api/v1/cash-audit/sincronizar";
let unidadesCarregadas = null;
const consultas = new WeakMap();
const consultasRecebimentos = new WeakMap();
const consultasReincidencia = new WeakMap();

export function consultarFechamento(unidade, inicio, fim) {
  return apiClient.get(FECHAMENTO_URL, { params: { unidade, inicio, fim }, timeout: 200000 });
}

export function consultarReincidencia(unidade, mes) {
  return apiClient.get(REINCIDENCIA_URL, { params: { unidade, mes }, timeout: 200000 });
}

export function consultarRelatorioCaixa(unidade, dia) {
  return apiClient.get(RELATORIO_URL, { params: { unidade, dia }, timeout: 200000 });
}

export function sincronizarRelatorioCaixa(unidade, dia) {
  return apiClient.post(SINCRONIZAR_URL, null, { params: { unidade, dia }, timeout: 200000 });
}

function renderMarkdownSeguro(texto) {
  return escapeHtml(texto).replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
}

function renderTabelaMarkdown(linhas) {
  const celulas = linhas
    .filter((linha) => !/^\|[\s|:-]+\|$/.test(linha.trim()))
    .map((linha) => linha.trim().replace(/^\||\|$/g, "").split("|").map((item) => item.trim()));
  if (!celulas.length) return "";
  const [cabecalho, ...corpo] = celulas;
  return `<div class="ca-table-wrap"><table class="table-compact"><thead><tr>${cabecalho.map((celula) => `<th>${renderMarkdownSeguro(celula)}</th>`).join("")}</tr></thead><tbody>${corpo.map((linha) =>
    `<tr>${linha.map((celula) => `<td>${renderMarkdownSeguro(celula)}</td>`).join("")}</tr>`
  ).join("")}</tbody></table></div>`;
}

export function renderRelatorioCaixa(markdown) {
  const secoes = [];
  let atual = { titulo: "Relatório do dia", linhas: [] };
  markdown.split(/\r?\n/).forEach((linha) => {
    if (linha.startsWith("# ")) {
      atual.titulo = linha.slice(2).trim();
    } else if (linha.startsWith("## ")) {
      secoes.push(atual);
      atual = { titulo: linha.slice(3).trim(), linhas: [] };
    } else if (!linha.startsWith("# ")) {
      atual.linhas.push(linha);
    }
  });
  secoes.push(atual);
  return secoes.map(({ titulo, linhas }) => {
    const conteudo = [];
    for (let indice = 0; indice < linhas.length;) {
      const linha = linhas[indice].trim();
      if (!linha) { indice += 1; continue; }
      if (linha.startsWith("|")) {
        const tabela = [];
        while (indice < linhas.length && linhas[indice].trim().startsWith("|")) {
          tabela.push(linhas[indice++]);
        }
        conteudo.push(renderTabelaMarkdown(tabela));
      } else if (linha.startsWith("### ")) {
        conteudo.push(`<h4>${renderMarkdownSeguro(linha.slice(4))}</h4>`);
        indice += 1;
      } else if (linha.startsWith("- ")) {
        const itens = [];
        while (indice < linhas.length && linhas[indice].trim().startsWith("- ")) {
          itens.push(`<li>${renderMarkdownSeguro(linhas[indice++].trim().slice(2))}</li>`);
        }
        conteudo.push(`<ul>${itens.join("")}</ul>`);
      } else {
        conteudo.push(`<p>${renderMarkdownSeguro(linha)}</p>`);
        indice += 1;
      }
    }
    const aberto = titulo === "Status da conferência" ? " open" : "";
    return `<details class="ca-panel ca-report-block"${aberto}><summary>${renderMarkdownSeguro(titulo)}</summary>${conteudo.join("")}</details>`;
  }).join("");
}

export async function carregarRelatorioCaixa(container) {
  const unidade = container.querySelector("#caUnidade").value;
  const botao = container.querySelector("#caReportButton");
  const destino = container.querySelector("#caReportResults");
  let dia;
  try {
    dia = lerDataBR(container.querySelector("#caFim").value);
  } catch (error) {
    showError(container, error);
    return;
  }
  botao.disabled = true;
  destino.hidden = false;
  destino.innerHTML = '<p class="ca-empty">Carregando relatório local…</p>';
  try {
    const resposta = await consultarRelatorioCaixa(unidade, dia);
    const relatorio = resposta.relatorios.find((item) => String(item.unidade) === String(unidade));
    if (!relatorio) throw new Error("Relatório indisponível para esta unidade.");
    destino.innerHTML = `${renderRelatorioCaixa(relatorio.markdown)}<a class="ca-report-download" href="${RELATORIO_URL}.xlsx?unidade=${encodeURIComponent(unidade)}&dia=${encodeURIComponent(dia)}">Baixar planilha</a>`;
  } catch (error) {
    destino.innerHTML = `<p class="ca-error" role="alert">${escapeHtml(error?.message || "Falha ao carregar o relatório.")}</p>`;
  } finally {
    botao.disabled = false;
  }
}

export async function atualizarRelatorioCaixa(container) {
  const unidade = container.querySelector("#caUnidade").value;
  const botao = container.querySelector("#caSyncButton");
  const destino = container.querySelector("#caReportResults");
  let dia;
  try {
    dia = lerDataBR(container.querySelector("#caFim").value);
  } catch (error) {
    showError(container, error);
    return;
  }
  botao.disabled = true;
  destino.hidden = false;
  destino.innerHTML = '<p class="ca-empty" role="status">Sincronizando webPosto e fontes de recebimento…</p>';
  try {
    const resposta = await sincronizarRelatorioCaixa(unidade, dia);
    destino.innerHTML = `<p class="ca-report-updated" role="status">Dados de ${escapeHtml(formatDateTime(resposta.dados_consultados_em))}</p>${renderRelatorioCaixa(resposta.markdown)}<a class="ca-report-download" href="${RELATORIO_URL}.xlsx?unidade=${encodeURIComponent(unidade)}&dia=${encodeURIComponent(dia)}">Baixar planilha</a>`;
  } catch (error) {
    destino.innerHTML = `<p class="ca-error" role="alert">${escapeHtml(error?.message || "Falha ao sincronizar o relatório.")}</p>`;
  } finally {
    botao.disabled = false;
  }
}

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
  FALTA_SEM_DESCONTO: "Sem desconto",
  VALE_DIVERGENTE: "Vale divergente",
  DESPESA_SEM_PLANO: "Despesa sem plano",
  DESPESA_SEM_DESCRICAO: "Despesa sem descrição",
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
        ...(item.grupos_provaveis || []).flatMap((grupo) => grupo.investigacoes),
      ];
      [...new Map(investigacoes.map((inv) => [inv.transacao.identificador || inv, inv])).values()].forEach((inv) => {
        const atribuido = inv.atribuicao === "atribuido" && inv.frentista != null;
        const frentistas = atribuido
          ? [inv.frentista]
          : inv.atribuicao === "sugestao"
            ? [...new Set(inv.candidatos.map((c) => c.abastecimento.frentista).filter((id) => id != null))]
            : [];
        frentistas.forEach((id) => {
          const linha = ranking.get(id) || {
            frentista: id, atribuidos: 0, sugestoes: 0,
            valorAtribuidos: 0, valorSugestoes: 0, nome: null,
          };
          linha[atribuido ? "atribuidos" : "sugestoes"] += 1;
          linha[atribuido ? "valorAtribuidos" : "valorSugestoes"] += Number(inv.transacao.valor);
          linha.nome ||= atribuido ? inv.nome_frentista
            : inv.candidatos.find((c) => c.abastecimento.frentista === id)?.abastecimento.nome_frentista;
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
    ? inv.frentista == null ? "frentista não identificado — atribuição sem código" : `${inv.nome_frentista || "nome indisponível"} (${inv.frentista}) · atribuído`
    : inv.atribuicao === "sugestao" ? `frentista não identificado — Sugestão (${inv.candidatos.length} candidatos · ${formatCurrency(inv.transacao.valor)})` : "frentista não identificado — sem abastecimento";
  const candidatos = inv.candidatos.map((c) =>
    `<li>Frentista ${escapeHtml(c.abastecimento.frentista == null ? "não informado" : `${c.abastecimento.nome_frentista || "nome indisponível"} (${c.abastecimento.frentista})`)}:
    ${escapeHtml(c.pontos)} pontos · ${escapeHtml(c.motivos.join(" · "))}</li>`
  ).join("");
  return `<strong>${escapeHtml(rotulo)}</strong>${candidatos ? `<ul class="ca-candidates">${candidatos}</ul>` : ""}`;
}

function renderDivergencia(dia, transacao, classificacao, tom, investigacao = null, cartao = null, diferenca = null) {
  const momento = transacao.momento || "";
  const detalhePar = cartao
    ? `<p class="ca-hint">ERP: ${escapeHtml(formatTime(cartao.momento))} · ${safeCurrency(cartao.valor)}</p>`
    : "";
  return `<tr class="ca-row--${tom}">
    <td>${escapeHtml(formatDate(dia))}</td><td>${escapeHtml(formatTime(momento))}</td>
    <td class="ca-num">${safeCurrency(transacao.valor)}</td>
    <td class="ca-num">${diferenca == null ? "—" : safeCurrency(diferenca)}</td>
    <td>${escapeHtml(transacao.bandeira || transacao.administradora || "—")}</td>
    <td><span class="ca-chip ca-chip--${tom}">${escapeHtml(classificacao)}</span>${detalhePar}
      ${transacao.motivo ? `<p>${escapeHtml(transacao.motivo)}</p>` : ""}
      <p>tipoInclusao: ${escapeHtml((cartao || transacao).tipo_inclusao || (investigacao && !cartao ? "não aplicável (sem lançamento ERP)" : "não informado"))}</p></td>
    <td>${investigacao ? renderAtribuicao(investigacao) : escapeHtml(
      (cartao || transacao).frentista == null
        ? `frentista não identificado — ${(cartao || transacao).motivo_frentista || "sem vínculo com a venda"}`
        : `${(cartao || transacao).nome_frentista || "nome indisponível"} (${(cartao || transacao).frentista})`
    )}</td>
  </tr>`;
}

export function renderRecebimentos(dias, falhas = [], diaSelecionado = null) {
  const grupos = new Map();
  dias.forEach((dia) => (dia.adquirentes || []).forEach((item) => {
    const grupo = grupos.get(item.adquirente) || [];
    grupo.push({ dia: dia.dia, ...item });
    grupos.set(item.adquirente, grupo);
  }));
  const adquirentes = [...grupos.entries()].map(([nome, itens]) => {
    const titulo = nome === "PREMMIA" ? "Premmia" : nome;
    const ok = itens.filter((item) => item.situacao === "ok");
    const estados = [...new Set(itens.filter((item) => item.situacao !== "ok").map((item) => item.erro || item.situacao))];
    const avisos = estados.map((estado) =>
      `<span class="ca-badge ca-badge--pendente">${escapeHtml(estado)}</span>`
    ).join(" ");
    if (!ok.length) {
      return `<article class="ca-panel"><h4>${escapeHtml(titulo)} ${avisos}</h4>
        <p class="ca-muted">Sem conciliação disponível. Nenhum dado estimado.</p>
        ${itens.flatMap((item) => (item.alertas || []).map((a) =>
          `<p class="ca-error">${escapeHtml(a.codigo)}: ${escapeHtml(a.mensagem)}</p>`
        )).join("")}</article>`;
    }
    const resumo = {
      casados: ok.reduce((sum, item) => sum + item.casados.quantidade, 0),
      total: ok.reduce((sum, item) => sum + Number(item.casados.total), 0),
      maior: ok.reduce((sum, item) => sum + item.a_maior.length, 0),
      menor: ok.reduce((sum, item) => sum + item.a_menor.length, 0),
      pares: ok.reduce((sum, item) => sum + item.pares_provaveis.length + (item.grupos_provaveis || []).length, 0),
      maiorValor: ok.flatMap((i) => i.a_maior).reduce((s, i) => s + Number(i.transacao.valor), 0),
      menorValor: ok.flatMap((i) => i.a_menor).reduce((s, c) => s + Number(c.valor), 0),
      paresValor: ok.reduce((s, i) => s
        + [...new Map(i.pares_provaveis.map((p) => [p.investigacao.transacao.identificador || p.investigacao, p.investigacao])).values()].reduce((v, inv) => v + Number(inv.transacao.valor), 0)
        + (i.grupos_provaveis || []).reduce((v, g) => v + g.investigacoes.reduce((n, inv) => n + Number(inv.transacao.valor), 0), 0), 0),
    };
    const formas = new Map();
    ok.forEach((item) => (item.formas || []).forEach((f) => {
      const resumoForma = formas.get(f.forma) || { portalQtd: 0, portalValor: 0, erpQtd: 0, erpValor: 0 };
      resumoForma.portalQtd += f.portal.quantidade;
      resumoForma.portalValor += Number(f.portal.total);
      resumoForma.erpQtd += f.webposto.quantidade;
      resumoForma.erpValor += Number(f.webposto.total);
      formas.set(f.forma, resumoForma);
    }));
    const tabelaFormas = formas.size ? `<table class="table-compact"><thead><tr><th>Forma</th><th>Portal</th><th>webPosto</th><th>Diferença</th></tr></thead><tbody>${[...formas].map(([forma, f]) =>
      `<tr><td>${escapeHtml(forma)}</td><td>${f.portalQtd} · ${safeCurrency(f.portalValor)}</td><td>${f.erpQtd} · ${safeCurrency(f.erpValor)}</td><td>${safeCurrency(f.portalValor - f.erpValor)}</td></tr>`
    ).join("")}</tbody></table>` : "";
    const divergencias = ok.flatMap((i) => i.divergencias_valor || []);
    const linhas = ok.map((item) => [
      ...(item.divergencias_valor || []).map((c) => renderDivergencia(
        item.dia, c.transacao, Number(c.diferenca) > 0 ? "CARTAO_VALOR_A_MENOR" : "CARTAO_VALOR_A_MAIOR",
        Number(c.diferenca) > 0 ? "vermelho" : "laranja", null, c.cartao, c.diferenca
      )),
      ...(item.alertas || []).filter((a) => a.codigo === "CARTAO_NSU_REPETIDO").flatMap((a) =>
        a.cartoes.map((c) => renderDivergencia(item.dia, c, `${a.codigo}: ${a.mensagem}`, "vermelho"))
      ),
      ...item.a_menor.map((cartao) => renderDivergencia(item.dia, cartao, "A menor", "vermelho")),
      ...item.a_maior.map((inv) => renderDivergencia(item.dia, inv.transacao, "A maior", "laranja", inv)),
      ...item.pares_provaveis.map((par) => renderDivergencia(item.dia, par.investigacao.transacao, "Par provável", "amarelo", par.investigacao, par.cartao)),
      ...(item.grupos_provaveis || []).flatMap((grupo) => grupo.investigacoes.map((inv) =>
        renderDivergencia(item.dia, inv.transacao, `Grupo provável (${grupo.investigacoes.length} recebimentos · ${formatCurrency(grupo.investigacoes.reduce((s, i) => s + Number(i.transacao.valor), 0))})`, "amarelo", inv, grupo.cartao)
      )),
    ].join("")).join("");
    const fontes = ok.map((item) =>
      `${formatDate(item.dia)}: ${item.proveniencia?.versao_regra || "—"} · ${formatDateTime(item.proveniencia?.executado_em)}`
    ).join(" | ");
    return `<article class="ca-panel"><h4>${escapeHtml(titulo)} ${avisos}</h4>
      <p class="ca-hint">${ok.length} de ${itens.length} dias com conciliação disponível.</p>
      <div class="ca-kpis">
        <article class="ca-kpi"><span>Casados</span><strong>${resumo.casados}</strong><small>${safeCurrency(resumo.total)}</small></article>
        <article class="ca-kpi ca-kpi--laranja"><span>A maior</span><strong>${resumo.maior}</strong><small>${safeCurrency(resumo.maiorValor)}</small></article>
        <article class="ca-kpi ca-kpi--vermelho"><span>A menor</span><strong>${resumo.menor}</strong><small>${safeCurrency(resumo.menorValor)}</small></article>
        <article class="ca-kpi"><span>Pares prováveis</span><strong>${resumo.pares}</strong><small>${safeCurrency(resumo.paresValor)}</small></article>
        <article class="ca-kpi"><span>Valores divergentes</span><strong>${divergencias.length}</strong><small>${safeCurrency(divergencias.reduce((s, c) => s + Math.abs(Number(c.diferenca)), 0))}</small></article>
      </div>
      ${tabelaFormas}
      ${linhas ? `<div class="ca-table-wrap"><table class="table-compact ca-receipts-table">
        <thead><tr><th>Data</th><th>Hora</th><th class="ca-num">Valor</th><th class="ca-num">Diferença</th><th>Bandeira / forma</th><th>Classificação</th><th>Frentista / motivos</th></tr></thead>
        <tbody>${linhas}</tbody></table></div>` : '<p class="ca-ok">Sem divergências nos dias consultados.</p>'}
      <p class="ca-provenance">${escapeHtml(fontes)}</p>
    </article>`;
  }).join("");
  const ranking = rankingFrentistas(dias);
  const rankingHtml = ranking.length
    ? `<div class="ca-table-wrap"><table class="table-compact"><thead><tr><th>Frentista</th><th>Atribuídos</th><th>Sugestões</th></tr></thead>
      <tbody>${ranking.map((linha) => `<tr><td>${escapeHtml(linha.nome || "nome indisponível")} (${escapeHtml(linha.frentista)})</td><td>${linha.atribuidos} · ${safeCurrency(linha.valorAtribuidos)}</td><td>${linha.sugestoes} · ${safeCurrency(linha.valorSugestoes)}</td></tr>`).join("")}</tbody></table></div>`
    : '<p class="ca-muted">Sem atribuições ou sugestões nos dias disponíveis.</p>';
  return `<h3>Recebimentos eletrônicos</h3>
    ${diaSelecionado ? `<p class="ca-hint">Totais e ranking do dia ${escapeHtml(formatDate(diaSelecionado))}. O fechamento acima mantém o período selecionado.</p>` : ""}
    ${falhas.length ? `<p class="ca-error" role="alert">Dias indisponíveis: ${escapeHtml(falhas.join(" · "))}. Totais e ranking são parciais.</p>` : ""}
    ${adquirentes || '<p class="ca-muted">Sem adquirentes disponíveis.</p>'}
    <section class="ca-panel"><h4>Ranking ${diaSelecionado ? "do dia" : "do período"} por frentista</h4>
      <p class="ca-hint">Sugestões não são atribuições confirmadas. Um recebimento conta uma vez por candidato; pares estão incluídos.</p>${rankingHtml}
    </section>`;
}

export async function carregarRecebimentos(container, unidade, dias, dia) {
  // Um dia por vez: a conciliacao baixa milhares de itens de venda por dia no webPosto.
  const alvo = container.querySelector("#caRecebimentos");
  const consulta = {};
  consultasRecebimentos.set(container, consulta);
  const seletor = dias.length > 1
    ? `<div class="ca-chips ca-dias" role="group" aria-label="Dia dos recebimentos">${dias.map((d) =>
        `<button type="button" class="ca-chip${d === dia ? " ca-chip--ativo" : ""}" data-ca-dia="${escapeHtml(d)}" aria-pressed="${d === dia}">${escapeHtml(formatDate(d))}</button>`).join("")}</div>`
    : "";
  alvo.innerHTML = `<h3>Recebimentos eletrônicos</h3>${seletor}<p class="ca-muted">Carregando recebimentos de ${escapeHtml(formatDate(dia))}…</p>`;
  alvo.querySelectorAll("[data-ca-dia]").forEach((botao) => { botao.disabled = true; });
  const respostas = [];
  const falhas = [];
  try {
    respostas.push(await apiClient.get(RECEBIMENTOS_URL, { params: { unidade, dia }, timeout: 200000 }));
  } catch (error) {
    falhas.push(`${formatDate(dia)}: ${error.message || "falha na consulta"}`);
  }
  if (consultasRecebimentos.get(container) !== consulta) return;
  alvo.innerHTML = renderRecebimentos(respostas, falhas, dia).replace("</h3>", `</h3>${seletor}`);
  alvo.querySelectorAll("[data-ca-dia]").forEach((botao) => {
    botao.addEventListener("click", () => void carregarRecebimentos(container, unidade, dias, botao.dataset.caDia));
  });
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

export function renderDetalhes(auditoria) {
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
  const desconto = auditoria.desconto_falta;
  const descontoHtml = !desconto
    ? ""
    : desconto.situacao === "descontado"
      ? `<p class="ca-ok">Descontado (vale ${safeCurrency(desconto.total_vale)}).</p>`
      : desconto.situacao === "sem_desconto"
        ? `<p class="ca-neg">Falta de ${safeCurrency(desconto.falta)} sem desconto lançado.</p>`
        : `<p class="ca-warning">Vale divergente: falta de ${safeCurrency(desconto.falta)}, vale de ${safeCurrency(desconto.total_vale)}; diferença de ${safeCurrency(desconto.diferenca)}.</p>`;
  const despesas = auditoria.despesas?.length
    ? `<div class="ca-table-wrap"><table class="table-compact"><thead><tr>
        <th>Despesa paga no caixa</th><th>Plano de contas</th><th class="ca-num">Valor</th>
      </tr></thead><tbody>${auditoria.despesas.map((despesa) => `
        <tr><td>${escapeHtml(despesa.descricao || "Sem descrição útil")}</td>
        <td>${escapeHtml(despesa.plano_conta_codigo || "Sem plano de contas")}</td>
        <td class="ca-num">${safeCurrency(despesa.valor)}</td></tr>`).join("")}</tbody></table></div>`
    : '<p class="ca-muted">Nenhuma despesa em dinheiro registrada para este caixa.</p>';
  const informativos = Array.isArray(auditoria.informativos) && auditoria.informativos.length
    ? `<div class="ca-muted"><h4>Informações</h4><ul>${auditoria.informativos
      .map((informativo) => `<li>${escapeHtml(informativo)}</li>`).join("")}</ul></div>`
    : "";
  return `
    <div class="ca-detail-grid">
      <div><h4>Modalidades</h4>
        <table class="table-compact"><thead><tr><th>Modalidade</th><th class="ca-num">Apresentado</th><th class="ca-num">Apurado</th><th class="ca-num">Diferença</th></tr></thead>
        <tbody>${modalidades}</tbody></table>
        ${descontoHtml}
      </div>
      <div><h4>Alertas</h4>${alertas}<h4>Despesas do caixa</h4>${despesas}${informativos}</div>
    </div>`;
}

function rotuloAlerta(alerta) {
  if (alerta.codigo === "NAO_CONSOLIDADO") return `Parado ${escapeHtml(alerta.valor ?? 0)} dias`;
  return escapeHtml(ALERTA_ROTULO[alerta.codigo] || alerta.codigo);
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
    `${rotuloAlerta(g)}${g.n > 1 ? ` ×${g.n}` : ""}</span>`
  ).join("");
}

export function renderTabela(resultado) {
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

export function renderReincidencia(resultado) {
  const funcionarios = resultado?.funcionarios || [];
  const cobertura = (resultado?.dias_com_dados || []).length;
  const semDados = resultado?.dias_sem_dados || [];
  const semFechamento = resultado?.dias_sem_fechamento || [];
  const semRecebimentos = resultado?.dias_sem_recebimentos || [];
  const coberturaHtml = `<p class="ca-hint">${cobertura} dia(s) com snapshots; ${semDados.length} dia(s) sem arquivo` +
    `${semDados.length ? `: ${semDados.map(d => escapeHtml(formatDate(d))).join(", ")}` : ""}.</p>` +
    `<p class="ca-hint">Fechamento indisponível: ${semFechamento.map(d => escapeHtml(formatDate(d))).join(", ") || "nenhum"} · ` +
    `PagBank indisponível: ${semRecebimentos.map(d => escapeHtml(formatDate(d))).join(", ") || "nenhum"}.</p>`;
  if (!funcionarios.length) {
    return `${coberturaHtml}<p class="ca-empty">Sem recorrências registradas nos snapshots disponíveis.</p>`;
  }
  const linhas = funcionarios.map((item) => `
    <tr><td>${escapeHtml(item.nome || `Funcionário #${item.funcionario_codigo}`)}</td>
      <td class="ca-num">${escapeHtml(item.quebras)}</td>
      <td class="ca-num">${safeCurrency(item.faltas_total)}</td>
      <td class="ca-num">${escapeHtml(item.sangrias_alteradas)}</td>
      <td class="ca-num">${escapeHtml(item.recebimentos_a_maior_atribuidos)} · ${safeCurrency(item.valor_recebimentos_a_maior_atribuidos)}</td>
      <td class="ca-num">${escapeHtml(item.recebimentos_a_maior_sugeridos)} · ${safeCurrency(item.valor_recebimentos_a_maior_sugeridos)}</td>
    </tr>`).join("");
  return `${coberturaHtml}<div class="ca-table-wrap"><table class="table-compact ca-reincidencia-table">
    <thead><tr><th>Funcionário</th><th>Quebras</th><th>Faltas</th><th>Sangrias alteradas</th>
      <th>A maior atribuídos</th><th>A maior sugeridos</th></tr></thead><tbody>${linhas}</tbody></table></div>`;
}

export async function carregarReincidencia(container, unidade, mes) {
  const sequencia = (consultasReincidencia.get(container) || 0) + 1;
  consultasReincidencia.set(container, sequencia);
  const conteudo = container.querySelector("#caReincidencia");
  conteudo.innerHTML = '<p class="ca-empty">Carregando reincidência do mês…</p>';
  try {
    const resultado = await consultarReincidencia(unidade, mes);
    if (consultasReincidencia.get(container) !== sequencia) return;
    conteudo.innerHTML = renderReincidencia(resultado);
  } catch (error) {
    if (consultasReincidencia.get(container) !== sequencia) return;
    conteudo.innerHTML = `<p class="ca-error" role="alert">${escapeHtml(error?.message || "Falha ao carregar reincidência.")}</p>`;
  }
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
  let inicio, fim;
  let mes;
  const mensagem = container.querySelector("#caError");
  const conteudo = container.querySelector("#caResults");
  let dias;
  try {
    inicio = lerDataBR(container.querySelector("#caInicio").value);
    fim = lerDataBR(container.querySelector("#caFim").value);
    mes = lerDataBR(`01/${container.querySelector("#caMes").value}`).slice(0, 7);
    dias = diasDoPeriodo(inicio, fim);
  } catch (error) {
    showError(container, error);
    return;
  }
  container.querySelectorAll("#caFilters input, #caFilters select, #caFilters button").forEach((node) => { node.disabled = true; });
  consultasRecebimentos.delete(container);
  mensagem.classList.add("hidden");
  conteudo.innerHTML = '<p class="ca-empty">Carregando auditoria…</p>';
  container.querySelector("#caRecebimentos").innerHTML = '<h3>Recebimentos eletrônicos</h3><p class="ca-muted">Aguardando o fechamento…</p>';
  container.querySelector("#caProveniencia").textContent = "";
  void carregarReincidencia(container, unidade, mes);
  try {
    const resultado = await consultarFechamento(unidade, inicio, fim);
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
      await carregarRecebimentos(container, unidade, dias, dias[dias.length - 1]);
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
          <label>Data início${campoDataBR({ nome: "caInicio", valor: inicio })}</label>
          <label>Data fim${campoDataBR({ nome: "caFim", valor: fim })}</label>
          <label>Mês da reincidência<input id="caMes" type="text" inputmode="numeric" placeholder="mm/aaaa" maxlength="7" pattern="\\d{2}/\\d{4}" value="${fim.slice(5, 7)}/${fim.slice(0, 4)}" required></label>
          <button type="submit">Consultar</button>
          <button id="caReportButton" type="button">Relatório do dia</button>
          <button id="caSyncButton" type="button">Atualizar agora</button>
        </form>
        <p id="caError" class="ca-error hidden" role="alert"></p>
        <div id="caResults"><p class="ca-empty">Selecione uma unidade para consultar.</p></div>
        <section id="caReportResults" class="ca-report" hidden aria-live="polite"></section>
        <section id="caRecebimentos" class="ca-receipts" aria-live="polite"></section>
        <section class="ca-panel ca-reincidencia" aria-live="polite">
          <h3>Reincidência do mês</h3>
          <div id="caReincidencia"><p class="ca-empty">Selecione uma unidade para consultar.</p></div>
        </section>
        <footer id="caProveniencia" class="ca-provenance">Proveniência disponível após a consulta.</footer>
      </div>`;
    ativarCamposDataBR(container.querySelector("#caFilters"));
    container.querySelector("#caFilters").addEventListener("submit", (event) => {
      event.preventDefault();
      void carregarAuditoria(container);
    });
    container.querySelector("#caReportButton").addEventListener("click", () => {
      void carregarRelatorioCaixa(container);
    });
    container.querySelector("#caSyncButton").addEventListener("click", () => {
      void atualizarRelatorioCaixa(container);
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
