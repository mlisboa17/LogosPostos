import { renderTable } from "../components/table.js";
import { formatMissing, formatNumber } from "../services/formatters.js";
import { resolveFilialFromRow } from "../components/filiais.js";
import { dataRecifeISO } from "../utils/datas.js";

export function renderStock(container, payload, onPageChange, options = {}) {
  const rows = payload?.data || [];
  const page = payload?.page || 1;
  const limit = payload?.limit || 50;
  const total = payload?.total || 0;

  container.innerHTML = '<div id="table"></div><div id="pager"></div>';
  renderTable(
    container.querySelector("#table"),
    [
      {
        key: "filial",
        label: "Filial",
        type: "text",
        sortable: true,
        truncate: true,
        filter: true,
        filterType: "select",
        accessor: (row) => resolveFilialFromRow(row),
        formatter: formatMissing,
        exportFormatter: (value, row) => resolveFilialFromRow(row),
      },
      { key: "tipoRegistro", label: "Tipo", type: "text", sortable: true, formatter: formatMissing, filter: true, filterType: "select" },
      { key: "codigo", label: "Codigo", type: "text", sortable: true, formatter: formatMissing, filter: true },
      {
        key: "descricao",
        label: "Descricao",
        type: "text",
        sortable: true,
        truncate: true,
        filter: true,
        accessor: (row) => row?.descricaoDisplay || row?.descricao,
        formatter: formatMissing,
        exportFormatter: (value, row) => row?.descricaoDisplay || value,
      },
      { key: "unidade", label: "Unidade", type: "text", sortable: true, formatter: formatMissing, filter: true, filterType: "select" },
      { key: "quantidade", label: "Quantidade", type: "number", sortable: true, formatter: formatNumber, sum: true, filter: true },
    ],
    rows,
    {
      state: options.tableState,
      onSearchChange: options.onSearchChange,
      onSortChange: options.onSortChange,
      onRefresh: options.onRefresh,
      onPageChange: onPageChange,
      pagination: { page, limit, total },
      emptyMessage: "Nenhum registro de estoque retornado para os filtros informados.",
      showClearFilters: true,
      onClearFilters: options.onClearFilters,
      title: "Estoque",
      exportName: options.exportName || `estoque_${dataRecifeISO()}`,
      pdfDescription: "Estoque de produtos e tanques por filial no período filtrado.",
    }
  );
}
