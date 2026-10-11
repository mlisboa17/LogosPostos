import { formatMissing } from "./formatters.js";
import { APP_CONFIG } from "../config.js";
import { formatarData, formatarDataHora } from "../utils/datas.js";

function parseExportNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const raw = String(value)
    .replace(/\s/g, "")
    .replace(/R\$/g, "")
    .replace(/[^0-9,.-]/g, "");
  if (!raw) return null;
  const hasComma = raw.includes(",");
  const hasDot = raw.includes(".");
  let normalized = raw;
  if (hasComma && hasDot) {
    normalized = raw.replace(/\./g, "").replace(/,/g, ".");
  } else if (hasComma) {
    normalized = raw.replace(/,/g, ".");
  }
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function logExportReconciliation(kind, filename, columns, rows) {
  if (!APP_CONFIG.debugFinancialReconciliation) return;

  const numericColumns = columns.filter((column) => column.type === "currency" || column.type === "number");
  const byColumn = numericColumns.map((column) => {
    const raw = rows.map((row) => (column.accessor ? column.accessor(row) : row[column.key]));
    const normalized = raw.map((value) => parseExportNumber(value));
    const summed = normalized.reduce((acc, value) => (value === null ? acc : acc + value), 0);
    return {
      key: column.key,
      bruto: raw,
      normalizado: normalized,
      valorExportado: summed,
    };
  });

  console.log("[debugFinancialReconciliation] export", {
    kind,
    filename,
    rowCount: rows.length,
    byColumn,
  });
}

function escapeCsv(value) {
  const text = formatMissing(value);
  return `"${text.replace(/"/g, '""')}"`;
}

export function buildCsv(columns, rows) {
  const header = columns.map((column) => escapeCsv(column.label)).join(";");
  const lines = rows.map((row) =>
    columns
      .map((column) => {
        const rawValue = column.accessor ? column.accessor(row) : row[column.key];
        const formatted = column.exportFormatter
          ? column.exportFormatter(rawValue, row)
          : column.formatter
            ? column.formatter(rawValue, row)
            : column.type === "date" ? formatarData(rawValue) : rawValue;
        return escapeCsv(formatted);
      })
      .join(";")
  );
  return [header, ...lines].join("\n");
}

export function downloadCsv(filename, columns, rows) {
  logExportReconciliation("csv", filename, columns, rows);
  const csv = buildCsv(columns, rows);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

export function openPdfPreview(title, columns, rows, meta = {}) {
  logExportReconciliation("pdf", title, columns, rows);
  const popup = window.open("", "_blank", "width=1100,height=800");
  if (!popup) return;

  const rowsHtml = rows
    .map(
      (row) =>
        `<tr>${columns
          .map((column) => {
            const rawValue = column.accessor ? column.accessor(row) : row[column.key];
            const formatted = column.exportFormatter
              ? column.exportFormatter(rawValue, row)
              : column.formatter
                ? column.formatter(rawValue, row)
                : column.type === "date" ? formatarData(rawValue) : rawValue;
            return `<td>${formatMissing(formatted)}</td>`;
          })
          .join("")}</tr>`
    )
    .join("");

  popup.document.write(`
    <!doctype html>
    <html lang="pt-BR">
      <head>
        <meta charset="utf-8" />
        <title>${title}</title>
        <style>
          body { font-family: Arial, sans-serif; padding: 24px; color: #222; }
          h1 { margin: 0 0 8px; }
          .meta { color: #555; margin-bottom: 16px; font-size: 12px; }
          table { width: 100%; border-collapse: collapse; font-size: 12px; }
          th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
          th { background: #f5f5f5; }
        </style>
      </head>
      <body>
        <h1>${title}</h1>
        <div class="meta">${meta.subtitle || meta.description || "Exportação da visão atual"}</div>
        <div class="meta">Gerado em: ${formatarDataHora(new Date())}</div>
        <table>
          <thead><tr>${columns.map((column) => `<th>${column.label}</th>`).join("")}</tr></thead>
          <tbody>${rowsHtml}</tbody>
        </table>
        <script>window.onload = () => window.print();</script>
      </body>
    </html>
  `);
  popup.document.close();
}
