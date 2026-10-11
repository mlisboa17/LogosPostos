export const FUSO_RECIFE = "America/Recife";
const dataBR = new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO_RECIFE, day: "2-digit", month: "2-digit", year: "numeric" });
const horaBR = new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO_RECIFE, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

function dataLocal(value) {
  if (value instanceof Date) return value;
  const raw = String(value).trim();
  const iso = /^\d{2}\/\d{2}\/\d{4}$/.test(raw) ? lerDataBR(raw) : raw;
  const completo = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T00:00:00-03:00`
    : /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(iso) ? `${iso}-03:00` : iso;
  const date = new Date(completo);
  if (Number.isNaN(date.getTime())) throw new Error("Data inválida. Use dd/mm/aaaa.");
  return date;
}
export function lerDataBR(value) {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(String(value).trim());
  if (!match) throw new Error("Data inválida. Use dd/mm/aaaa.");
  const [, dd, mm, yyyy] = match;
  const date = new Date(`${yyyy}-${mm}-${dd}T12:00:00Z`);
  if (Number.isNaN(date.getTime()) || date.getUTCFullYear() !== Number(yyyy)
      || date.getUTCMonth() + 1 !== Number(mm) || date.getUTCDate() !== Number(dd)) {
    throw new Error("Data inválida. Use dd/mm/aaaa.");
  }
  return `${yyyy}-${mm}-${dd}`;
}
export function formatarData(value) {
  return value === null || value === undefined || value === "" ? "sem dados" : dataBR.format(dataLocal(value));
}
export function formatarHora(value) {
  return value === null || value === undefined || value === "" ? "sem dados" : horaBR.format(dataLocal(value));
}
export function formatarDataHora(value) {
  return value === null || value === undefined || value === "" ? "sem dados" : `${formatarData(value)} ${formatarHora(value)}`;
}
export function dataRecifeISO(value = new Date()) {
  return lerDataBR(formatarData(value));
}
export function somarDias(iso, dias) {
  const date = new Date(`${iso}T12:00:00Z`);
  if (Number.isNaN(date.getTime())) throw new Error("Data inválida.");
  date.setUTCDate(date.getUTCDate() + dias);
  return dataRecifeISO(date);
}
export function campoDataBR({ nome, valor = "", obrigatorio = true } = {}) {
  if (!/^[a-zA-Z][\w-]*$/.test(nome)) throw new Error("Nome de campo de data inválido.");
  const exibido = valor ? formatarData(valor) : "";
  return `<input name="${nome}" type="text" inputmode="numeric" placeholder="dd/mm/aaaa" maxlength="10" pattern="\\d{2}/\\d{2}/\\d{4}" value="${exibido}" ${obrigatorio ? "required" : ""} data-data-br aria-label="${nome} dd/mm/aaaa">`;
}
export function ativarCamposDataBR(container) {
  for (const input of container.querySelectorAll("[data-data-br]")) {
    input.addEventListener("input", () => {
      const digits = input.value.replace(/\D/g, "").slice(0, 8);
      input.value = [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4)].filter(Boolean).join("/");
      input.setCustomValidity("");
    });
    input.addEventListener("blur", () => {
      try { if (input.value) lerDataBR(input.value); input.setCustomValidity(""); }
      catch (error) { input.setCustomValidity(error.message); }
    });
  }
}
