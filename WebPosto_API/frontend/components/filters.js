import {
  mountMultiSelectLogos,
  readEmpresaCodigoFromMultiSelectLogos,
  updateMultiSelectLogos,
} from "./MultiSelectLogos.js";
import { campoDataBR, ativarCamposDataBR, lerDataBR } from "../utils/datas.js";

function normalizeMultiValue(value) {
  if (Array.isArray(value)) return value.filter((item) => String(item || "").trim() !== "");
  const text = String(value || "").trim();
  if (!text) return [];
  if (!text.includes(",")) return [text];
  return text
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function valueFromCommaInput(value) {
  const normalized = normalizeMultiValue(value).filter(
    (item) => !/^(todos|all|__all__)$/i.test(String(item || "").trim())
  );
  if (normalized.length === 0) return "";
  if (normalized.length === 1) return normalized[0];
  return normalized;
}

function debounce(fn, delayMs) {
  let timeoutId;
  return (...args) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delayMs);
  };
}

function isVisibleField(visible, key) {
  return visible.includes(key);
}

export function renderFilters(container, state, onChange, onClear, options = {}) {
  const visible = options.visibleFields || [
    "dataInicial",
    "dataFinal",
    "empresaCodigo",
    "centroCusto",
    "tipoDespesa",
    "valorMin",
    "valorMax",
  ];

  const fieldsHtml = [
    isVisibleField(visible, "dataInicial")
      ? `
        <div class="field">
          <label for="dataInicial">Data inicial</label>
          ${campoDataBR({ nome: "dataInicial", valor: state.dataInicial })}
        </div>
      `
      : "",
    isVisibleField(visible, "dataFinal")
      ? `
        <div class="field">
          <label for="dataFinal">Data final</label>
          ${campoDataBR({ nome: "dataFinal", valor: state.dataFinal })}
        </div>
      `
      : "",
    isVisibleField(visible, "empresaCodigo")
      ? `
        <div class="field field--empresa">
          <label>Empresa <span id="empresaCodigoCounter" class="small"></span></label>
          <div id="empresaMultiselectHost"></div>
        </div>
      `
      : "",
    isVisibleField(visible, "centroCusto")
      ? `
        <div class="field">
          <label for="centroCusto">Centro de custo</label>
          <input id="centroCusto" type="text" value="${Array.isArray(state.centroCusto) ? state.centroCusto.join(",") : (state.centroCusto || "")}" placeholder="ADMINISTRATIVO, OPERACIONAL" />
          <div class="small">Use vírgula para múltiplos valores</div>
        </div>
      `
      : "",
    isVisibleField(visible, "tipoDespesa")
      ? `
        <div class="field">
          <label for="tipoDespesa">Tipo despesa</label>
          <input id="tipoDespesa" type="text" value="${Array.isArray(state.tipoDespesa) ? state.tipoDespesa.join(",") : (state.tipoDespesa || "")}" placeholder="operacional, financeiro" />
          <div class="small">Use vírgula para múltiplos valores</div>
        </div>
      `
      : "",
    isVisibleField(visible, "valorMin")
      ? `
        <div class="field">
          <label for="valorMin">Valor minimo</label>
          <input id="valorMin" type="number" step="0.01" value="${state.valorMin || ""}" />
        </div>
      `
      : "",
    isVisibleField(visible, "valorMax")
      ? `
        <div class="field">
          <label for="valorMax">Valor maximo</label>
          <input id="valorMax" type="number" step="0.01" value="${state.valorMax || ""}" />
        </div>
      `
      : "",
  ].join("");

  container.innerHTML = `
    ${fieldsHtml}
    <div class="field filters-actions">
      <label>Ações</label>
      <div class="filters-actions__buttons">
        ${options.onRefresh ? '<button id="applyFilters" type="button">Atualizar</button>' : ""}
        <button id="clearFilters" type="button">Limpar filtros</button>
      </div>
    </div>
    <p class="small" data-date-error role="alert"></p>
  `;
  ativarCamposDataBR(container);

  const emitChange = debounce(() => {
    const errorNode = container.querySelector("[data-date-error]");
    const inicial = container.querySelector("#dataInicial");
    const final = container.querySelector("#dataFinal");
    let dataInicial, dataFinal;
    try {
      dataInicial = inicial ? lerDataBR(inicial.value) : state.dataInicial;
      dataFinal = final ? lerDataBR(final.value) : state.dataFinal;
      if (dataInicial && dataFinal && dataInicial > dataFinal) throw new Error("A data inicial deve ser anterior ou igual à final.");
      errorNode.textContent = "";
    } catch (error) {
      errorNode.textContent = error.message;
      return;
    }
    const host = container.querySelector("#empresaMultiselectHost");
    const nextState = {
      ...state,
      dataInicial,
      dataFinal,
      empresaCodigo: host ? readEmpresaCodigoFromMultiSelectLogos(host) : state.empresaCodigo,
      centroCusto: valueFromCommaInput(container.querySelector("#centroCusto")?.value || ""),
      tipoDespesa: valueFromCommaInput(container.querySelector("#tipoDespesa")?.value || ""),
      valorMin: container.querySelector("#valorMin")?.value || "",
      valorMax: container.querySelector("#valorMax")?.value || "",
    };
    onChange(nextState);
  }, 300);

  if (container.querySelector("#empresaMultiselectHost")) {
    const host = container.querySelector("#empresaMultiselectHost");
    mountMultiSelectLogos(host, state.empresaCodigo, () => emitChange());
  }

  container.querySelectorAll("input:not([type=search])").forEach((element) => {
    if (element.closest("#empresaMultiselect")) return;
    element.addEventListener("change", emitChange);
    element.addEventListener("input", emitChange);
  });

  container.querySelector("#clearFilters")?.addEventListener("click", () => onClear?.());
  container.querySelector("#applyFilters")?.addEventListener("click", () => {
    const datas = container.querySelectorAll("[data-data-br]");
    for (const input of datas) {
      try { lerDataBR(input.value); }
      catch (error) { container.querySelector("[data-date-error]").textContent = error.message; return; }
    }
    options.onRefresh?.();
  });
}

export function updateCompanyOptions(container, companies, selectedValue) {
  const host = container.querySelector("#empresaMultiselectHost");
  if (!host) return;
  updateMultiSelectLogos(host, selectedValue);
}
