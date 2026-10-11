import { APP_CONFIG } from "../config.js";
import { fetchSales, fetchFinancialExpenses, fetchStock } from "./api.js";
import { somarDias } from "../utils/datas.js";

/**
 * Snapshots Service (Etapa 6) - Snapshot History Engine
 * Guarda chaves passadas e permite ler de sessao de API com limitacao (ontem, 7d, 30d).
 */

class SnapshotService {
  constructor() {}

  /**
   * Pega o offset de uma data para snapshots comparativos. 
   * @param {string} hojeISO Data de hoje no formato YYYY-MM-DD 
   */
  async getSnapshot(type, hojeISO, empresaCodigo) {
    let dias;

    if (type === "ontem") {
      dias = -1;
    } else if (type === "7dias") {
      dias = -7;
    } else if (type === "30dias") {
      dias = -30;
    } else {
      return null;
    }

    const start = somarDias(hojeISO, dias);
    const end = start;
    
    try {
      const filters = { dataInicial: start, dataFinal: end, empresaCodigo: empresaCodigo || "" };
      
      const pSales = fetchSales(filters, 1, 100).catch(() => ({}));
      const pExp = fetchFinancialExpenses(filters, 1, 100).catch(() => ({}));
      
      const [rs, rx] = await Promise.all([pSales, pExp]);
      
      // Compute simples manual em background
      const salesData = rs.resultados || rs.data || [];
      const expData = rx.resultados || rx.data || [];
      
      let faturamento = 0;
      let vr = 0;
      salesData.forEach((v) => { faturamento += Number(String(v.totalVenda || 0).replace(",", ".")) || 0; vr += 1; });
      
      let despesas = 0;
      expData.forEach((e) => { despesas += Number(String(e.valor || 0).replace(",", ".")) || 0; });
      
      return {
        faturamento,
        despesas,
        margem: faturamento > 0 ? ((faturamento - despesas) / faturamento * 100) : 0,
        ticketMedio: vr > 0 ? faturamento / vr : 0,
        data: start
      };
    } catch(e) {
      return null;
    }
  }
}

export const snapshotService = new SnapshotService();
