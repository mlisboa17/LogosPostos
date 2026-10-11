import { renderTable } from "../components/table.js";
import { formatCurrency, formatMissing } from "../services/formatters.js";
import { formatarData as formatDate, dataRecifeISO } from "../utils/datas.js";
import { resolveFilialFromRow } from "../components/filiais.js";

export function renderExpenses(container, payload, onPageChange, options = {}) {
  const rows = payload?.data || [];
  const page = payload?.page || 1;
  const limit = payload?.limit || 50;
  const total = payload?.total || 0;

  container.innerHTML = '<div id="table"></div><div id="pager"></div>';
  renderTable(
    container.querySelector("#table"),
    [
      { key: "data", label: "Data", type: "date", sortable: true, formatter: formatDate, filter: true },
      { key: "valor", label: "Valor", type: "currency", sortable: true, formatter: formatCurrency, sum: true, filter: true },
      { key: "planoConta", label: "Plano de conta", type: "text", sortable: true, truncate: true, filter: true },
      {
        key: "filial",
        label: "Filial",
        type: "text",
        sortable: true,
        filter: true,
        filterType: "select",
        accessor: (row) => resolveFilialFromRow(row),
        formatter: formatMissing,
        exportFormatter: (value, row) => resolveFilialFromRow(row),
        searchable: true,
      },
      {
        key: "centroCusto",
        label: "Centro de custo",
        type: "text",
        sortable: true,
        truncate: true,
        formatter: formatMissing,
        filter: true,
        filterType: "select",
      },
      { key: "origem", label: "Origem", type: "text", sortable: true, formatter: formatMissing, filter: true, filterType: "select" },
      { key: "status", label: "Status", type: "status", sortable: true, formatter: formatMissing, filter: true, filterType: "select" },
    ],
    rows,
    {
      state: options.tableState,
      onSearchChange: options.onSearchChange,
      onSortChange: options.onSortChange,
      onRefresh: options.onRefresh,
      onPageChange: onPageChange,
      pagination: { page, limit, total },
      emptyMessage: "Nenhuma despesa encontrada para os filtros informados.",
      showClearFilters: true,
      onClearFilters: options.onClearFilters,
      title: "Despesas",
      exportName: options.exportName || `despesas_${String(rows[0]?.data || dataRecifeISO())}`,
      pdfDescription: "Despesas filtradas da visão atual.",
    }
  );
}
