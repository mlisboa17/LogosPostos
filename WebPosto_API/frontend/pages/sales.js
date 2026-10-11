import { renderTable } from "../components/table.js";
import { formatCurrency, formatMissing } from "../services/formatters.js";
import { formatarData as formatDate, dataRecifeISO } from "../utils/datas.js";
import { resolveFilialFromRow } from "../components/filiais.js";

// Função helper para formatar números decimais comuns de forma amigável no Brasil (ex: 12.500 ou 12.500,5)
function formatDecimalBr(num, decimals = 1) {
  const n = Number(num);
  if (!Number.isFinite(n)) return "0";
  return n.toLocaleString("pt-BR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function renderSales(container, payload, onPageChange, options = {}) {
  // Inicializa o estado persistente do sub-view se ainda não existir
  window.salesActiveSubview = window.salesActiveSubview || "detailed";

  const rows = payload?.data || [];
  const page = payload?.page || 1;
  const limit = payload?.limit || 50;
  const total = payload?.total || 0;
  const fuelSummary = options.fuelSummary || [];

  // Criar estrutura básica de abas de sub-view no topo
  container.innerHTML = `
    <nav class="subtabs" style="display: flex; gap: 15px; margin-bottom: 20px; border-bottom: 2px solid #eaeaea; padding-bottom: 0;">
      <button id="btnSubtabDetailed" class="tab-button" style="cursor: pointer; padding: 10px 20px; border: none; background: none; font-size: 15px; font-weight: bold; border-bottom: 3px solid ${window.salesActiveSubview === "detailed" ? "#0056b3" : "transparent"}; color: ${window.salesActiveSubview === "detailed" ? "#0056b3" : "#666"}; transition: all 0.2s;">
        Detalhado
      </button>
      <button id="btnSubtabFuels" class="tab-button" style="cursor: pointer; padding: 10px 20px; border: none; background: none; font-size: 15px; font-weight: bold; border-bottom: 3px solid ${window.salesActiveSubview === "fuels" ? "#0056b3" : "transparent"}; color: ${window.salesActiveSubview === "fuels" ? "#0056b3" : "#666"}; transition: all 0.2s;">
        Combustíveis
      </button>
    </nav>
    <div id="salesSubContent"></div>
  `;

  // Adicionar handlers de clique nas abas
  const btnDetailed = container.querySelector("#btnSubtabDetailed");
  const btnFuels = container.querySelector("#btnSubtabFuels");
  const subContentNode = container.querySelector("#salesSubContent");

  btnDetailed.addEventListener("click", () => {
    window.salesActiveSubview = "detailed";
    renderSubView();
  });

  btnFuels.addEventListener("click", () => {
    window.salesActiveSubview = "fuels";
    renderSubView();
  });

  // Função interna para renderizar o sub-view ativo
  function renderSubView() {
    // Atualizar classes visuais das abas
    btnDetailed.style.borderBottomColor = window.salesActiveSubview === "detailed" ? "#0056b3" : "transparent";
    btnDetailed.style.color = window.salesActiveSubview === "detailed" ? "#0056b3" : "#666";
    btnFuels.style.borderBottomColor = window.salesActiveSubview === "fuels" ? "#0056b3" : "transparent";
    btnFuels.style.color = window.salesActiveSubview === "fuels" ? "#0056b3" : "#666";

    subContentNode.innerHTML = "";

    if (window.salesActiveSubview === "detailed") {
      // VISÃO DETALHADA (comportamento original)
      const tableDiv = document.createElement("div");
      tableDiv.id = "table";
      const pagerDiv = document.createElement("div");
      pagerDiv.id = "pager";
      subContentNode.appendChild(tableDiv);
      subContentNode.appendChild(pagerDiv);

      renderTable(
        tableDiv,
        [
          { key: "data", label: "Data", type: "date", sortable: true, formatter: formatDate, filter: true },
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
          { key: "vendaCodigo", label: "Venda", type: "text", sortable: true, formatter: formatMissing, filter: true },
          { key: "cliente", label: "Cliente", type: "text", sortable: true, truncate: true, formatter: formatMissing, filter: true },
          { key: "itens", label: "Itens", type: "number", sortable: true, formatter: formatMissing, sum: true, filter: true },
          { key: "formaPagamento", label: "Forma pagamento", type: "text", sortable: true, formatter: formatMissing, filter: true, filterType: "select" },
          { key: "totalVenda", label: "Total venda", type: "currency", sortable: true, formatter: formatCurrency, sum: true, filter: true },
        ],
        rows,
        {
          state: options.tableState,
          onSearchChange: options.onSearchChange,
          onSortChange: options.onSortChange,
          onRefresh: options.onRefresh,
          onPageChange: onPageChange,
          pagination: { page, limit, total },
          emptyMessage: "Nenhuma venda encontrada para os filtros informados.",
          showClearFilters: true,
          onClearFilters: options.onClearFilters,
          title: "Vendas",
          exportName: options.exportName || `vendas_${String(rows[0]?.data || dataRecifeISO())}`,
          pdfDescription: "Vendas detalhadas por filial para o período filtrado.",
        }
      );
    } else {
      // VISÃO ANALÍTICA (Consolidada de combustíveis)
      const totalLitrosVendido = fuelSummary.reduce((acc, f) => acc + Number(f.litros || 0), 0);
      const totalFaturamento = fuelSummary.reduce((acc, f) => acc + Number(f.valor || 0), 0);
      const precoMedioGeral = totalLitrosVendido > 0 ? totalFaturamento / totalLitrosVendido : 0;

      let combustivelLider = "N/A";
      let maxLitros = -1;
      fuelSummary.forEach((f) => {
        if (Number(f.litros || 0) > maxLitros) {
          maxLitros = Number(f.litros || 0);
          combustivelLider = f.combustivelDisplay || f.combustivel;
        }
      });

      const summaryDiv = document.createElement("div");
      summaryDiv.className = "cards";
      summaryDiv.style.marginBottom = "25px";
      summaryDiv.innerHTML = `
        <article class="card">
          <div class="label">Litros vendidos</div>
          <div class="value" style="color: #2b7a78;">${formatDecimalBr(totalLitrosVendido, 1)} L</div>
        </article>
        <article class="card">
          <div class="label">Faturamento</div>
          <div class="value" style="color: #17252a;">${formatCurrency(String(totalFaturamento))}</div>
        </article>
        <article class="card">
          <div class="label">Preço médio litro</div>
          <div class="value" style="color: #3b5998;">${formatCurrency(String(precoMedioGeral))} / L</div>
        </article>
        <article class="card">
          <div class="label">Combustível líder</div>
          <div class="value" style="color: #d9534f; font-size: 1.15rem; word-break: break-word;">${combustivelLider}</div>
        </article>
      `;
      subContentNode.appendChild(summaryDiv);

      const fuelTableDiv = document.createElement("div");
      fuelTableDiv.id = "fuelTable";
      subContentNode.appendChild(fuelTableDiv);

      renderTable(
        fuelTableDiv,
        [
          {
            key: "combustivel",
            label: "Combustível",
            type: "text",
            sortable: true,
            filter: true,
            accessor: (row) => row?.combustivelDisplay || row?.combustivel,
            exportFormatter: (value, row) => row?.combustivelDisplay || value,
          },
          { key: "litros", label: "Litros vendidos", type: "number", sortable: true, formatter: (v) => `${formatDecimalBr(v, 1)} L`, sum: true },
          { key: "valor", label: "Faturamento", type: "currency", sortable: true, formatter: formatCurrency, sum: true },
          { key: "ticketMedioLitro", label: "Preço médio litro", type: "currency", sortable: true, formatter: formatCurrency },
          { key: "participacao", label: "Participação", type: "number", sortable: true, formatter: (v) => `${v}%` },
        ],
        fuelSummary,
        {
          state: options.tableState,
          onRefresh: options.onRefresh,
          emptyMessage: "Nenhum combustível retornado para o período selecionado.",
          title: "Visão Comercial de Combustíveis",
          exportName: `comercial_combustiveis_${options.exportName || new Date().toISOString().slice(0, 10)}`,
          pdfDescription: "Volume físico e faturamento por produto e participação no mix de vendas no período filtrado.",
        }
      );
    }
  }

  // Primeira renderização
  renderSubView();
}
