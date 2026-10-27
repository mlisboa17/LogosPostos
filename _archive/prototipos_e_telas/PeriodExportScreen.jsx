import React, { useState } from 'react';
import { Download, Calendar, AlertCircle, CheckCircle2 } from 'lucide-react';

const API_BASE =
  (typeof window !== 'undefined' && window.LOGOS_API_BASE) ||
  (typeof process !== 'undefined' && process.env && process.env.REACT_APP_LOGOS_API_BASE) ||
  'http://localhost:8000';

const UNITS = [
  { id: 1, name: 'Real' },
  { id: 2, name: 'Casa Caiada' },
  { id: 3, name: 'VIP' },
];

function eachDay(startStr, endStr) {
  const out = [];
  const a = new Date(`${startStr}T12:00:00`);
  const b = new Date(`${endStr}T12:00:00`);
  if (a > b) return out;
  for (let d = new Date(a); d <= b; d.setDate(d.getDate() + 1)) {
    out.push(d.toISOString().split('T')[0]);
  }
  return out;
}

async function fetchClosuresFromApi(startDate, endDate) {
  const closures = [];
  const errors = [];
  const days = eachDay(startDate, endDate);
  if (days.length === 0) throw new Error('Período inválido (data inicial > final).');

  for (const day of days) {
    for (const u of UNITS) {
      const url = `${API_BASE}/auditoria/fechamentos/${u.id}?data=${encodeURIComponent(day)}`;
      const res = await fetch(url);
      if (res.status === 404) continue;
      if (!res.ok) {
        errors.push(`${url} → ${res.status}`);
        continue;
      }
      const body = await res.json();
      const list = body.fechamentos || [];
      for (const f of list) {
        closures.push({
          id: String(f.id),
          unit: u.name,
          unitId: u.id,
          date: day,
          cashier: f.operador_fechamento,
          grossRevenue: f.faturamento_bruto,
          closingBalance: f.saldo_informado_dinheiro,
          discrepancy: f.quebra_caixa,
          status: f.status === 'fechado' ? 'closed' : 'pending',
        });
      }
    }
  }
  return { closures, errors };
}

async function fetchExpensesFromApi(startDate, endDate) {
  const expenses = [];
  const errors = [];
  const days = eachDay(startDate, endDate);
  if (days.length === 0) throw new Error('Período inválido (data inicial > final).');

  for (const day of days) {
    for (const u of UNITS) {
      const url = `${API_BASE}/auditoria/despesas/${u.id}?data=${encodeURIComponent(day)}`;
      const res = await fetch(url);
      if (res.status === 404) continue;
      if (!res.ok) {
        errors.push(`${url} → ${res.status}`);
        continue;
      }
      const arr = await res.json();
      if (!Array.isArray(arr)) continue;
      for (const d of arr) {
        const hora = d.horario || '';
        expenses.push({
          id: String(d.id),
          unit: u.name,
          unitId: u.id,
          date: hora.slice(0, 10) || day,
          category: d.categoria,
          amount: d.valor,
          operator: d.operador,
          description: d.descricao || '',
          hasReceipt: !!d.tem_documento,
          justificationStatus: d.status_justificativa || 'pending',
        });
      }
    }
  }
  return { expenses, errors };
}

function downloadJson(filename, obj) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

const PeriodExportScreen = () => {
  const today = new Date().toISOString().split('T')[0];
  const monthStart = `${today.slice(0, 7)}-01`;

  const [startDate, setStartDate] = useState(monthStart);
  const [endDate, setEndDate] = useState(today);
  const [loadingClosures, setLoadingClosures] = useState(false);
  const [loadingExpenses, setLoadingExpenses] = useState(false);
  const [closureStatus, setClosureStatus] = useState(null);
  const [expenseStatus, setExpenseStatus] = useState(null);
  const [closurePreview, setClosurePreview] = useState(null);
  const [expensePreview, setExpensePreview] = useState(null);

  const handleExportClosures = async () => {
    setLoadingClosures(true);
    setClosureStatus(null);
    setClosurePreview(null);
    try {
      const { closures, errors } = await fetchClosuresFromApi(startDate, endDate);
      if (closures.length === 0 && errors.length > 0) {
        throw new Error(errors.join(' | '));
      }
      const payload = {
        source: 'Logos Auditoria API',
        apiBase: API_BASE,
        period: { startDate, endDate },
        units: UNITS.map((u) => u.name),
        closures,
        fetchWarnings: errors,
      };
      setClosurePreview(payload);
      downloadJson(`fechamentos_${startDate}_${endDate}.json`, payload);
      let cmsg = `✓ ${closures.length} fechamento(s) exportados (API real).`;
      if (errors.length) {
        cmsg += ` Avisos: ${errors.slice(0, 3).join('; ')}${errors.length > 3 ? '…' : ''}`;
      }
      setClosureStatus({
        type: 'success',
        message: cmsg,
        timestamp: new Date().toLocaleTimeString('pt-BR'),
      });
    } catch (error) {
      setClosureStatus({
        type: 'error',
        message: `✗ ${error.message || error}`,
        timestamp: new Date().toLocaleTimeString('pt-BR'),
      });
    } finally {
      setLoadingClosures(false);
    }
  };

  const handleExportExpenses = async () => {
    setLoadingExpenses(true);
    setExpenseStatus(null);
    setExpensePreview(null);
    try {
      const { expenses, errors } = await fetchExpensesFromApi(startDate, endDate);
      if (expenses.length === 0 && errors.length > 0) {
        throw new Error(errors.join(' | '));
      }
      const missingAttachments = expenses.filter(
        (e) => !e.hasReceipt || e.justificationStatus === 'missing_attachment'
      ).length;
      const payload = {
        source: 'Logos Auditoria API',
        apiBase: API_BASE,
        period: { startDate, endDate },
        expenses,
        fetchWarnings: errors,
      };
      setExpensePreview(payload);
      downloadJson(`despesas_${startDate}_${endDate}.json`, payload);
      setExpenseStatus({
        type: 'success',
        message: `✓ ${expenses.length} despesa(s) exportadas (${missingAttachments} alerta(s) documento).`,
        timestamp: new Date().toLocaleTimeString('pt-BR'),
      });
    } catch (error) {
      setExpenseStatus({
        type: 'error',
        message: `✗ ${error.message || error}`,
        timestamp: new Date().toLocaleTimeString('pt-BR'),
      });
    } finally {
      setLoadingExpenses(false);
    }
  };

  const cPrev = closurePreview;
  const ePrev = expensePreview;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-8">
      <div className="max-w-6xl mx-auto">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">Exportar Auditoria</h1>
          <p className="text-slate-400">
            Dados apenas da API em <code className="text-cyan-400">{API_BASE}</code> — sem mock.
          </p>
        </div>

        <div className="bg-slate-900 border border-slate-700 rounded-lg p-6 mb-8">
          <div className="flex items-center gap-2 mb-4">
            <Calendar className="w-5 h-5 text-blue-400" />
            <h2 className="text-lg font-semibold">Período de Análise</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">Data Inicial</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded text-white focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">Data Final</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded text-white focus:border-blue-500 focus:outline-none"
              />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-slate-900 border border-slate-700 rounded-lg p-6">
            <h3 className="text-xl font-bold mb-4 text-green-400">Fechamentos de Caixa</h3>
            <div className="bg-slate-800 rounded p-4 mb-4 text-sm">
              {cPrev ? (
                <div className="space-y-2 text-slate-300">
                  <p>📊 Registros: {cPrev.closures.length}</p>
                  <p>✅ Fechados: {cPrev.closures.filter((c) => c.status === 'closed').length}</p>
                  <p>⏳ Pendentes: {cPrev.closures.filter((c) => c.status === 'pending').length}</p>
                </div>
              ) : (
                <p className="text-slate-500">Clique em exportar para buscar na API.</p>
              )}
            </div>
            {closureStatus && (
              <div
                className={`flex items-start gap-2 p-3 rounded mb-4 text-sm ${
                  closureStatus.type === 'success'
                    ? 'bg-green-900/30 border border-green-700 text-green-300'
                    : 'bg-red-900/30 border border-red-700 text-red-300'
                }`}
              >
                {closureStatus.type === 'success' ? (
                  <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" />
                ) : (
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                )}
                <div>
                  <p className="font-medium">{closureStatus.message}</p>
                  <p className="text-xs opacity-75">{closureStatus.timestamp}</p>
                </div>
              </div>
            )}
            <button
              type="button"
              onClick={handleExportClosures}
              disabled={loadingClosures}
              className="w-full bg-green-600 hover:bg-green-700 disabled:bg-slate-700 text-white font-semibold py-3 rounded flex items-center justify-center gap-2 transition"
            >
              {loadingClosures ? 'Buscando na API…' : (
                <>
                  <Download className="w-4 h-4" />
                  Exportar fechamentos (API)
                </>
              )}
            </button>
          </div>

          <div className="bg-slate-900 border border-slate-700 rounded-lg p-6">
            <h3 className="text-xl font-bold mb-4 text-amber-400">Despesas de Caixa</h3>
            <div className="bg-slate-800 rounded p-4 mb-4 text-sm">
              {ePrev ? (
                <div className="space-y-2 text-slate-300">
                  <p>💰 Total: R$ {ePrev.expenses.reduce((s, e) => s + e.amount, 0).toFixed(2)}</p>
                  <p>📋 Registros: {ePrev.expenses.length}</p>
                  <p>✓ Com comprovante: {ePrev.expenses.filter((e) => e.hasReceipt).length}</p>
                </div>
              ) : (
                <p className="text-slate-500">Clique em exportar para buscar na API.</p>
              )}
            </div>
            {expenseStatus && (
              <div
                className={`flex items-start gap-2 p-3 rounded mb-4 text-sm ${
                  expenseStatus.type === 'success'
                    ? 'bg-green-900/30 border border-green-700 text-green-300'
                    : 'bg-red-900/30 border border-red-700 text-red-300'
                }`}
              >
                {expenseStatus.type === 'success' ? (
                  <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" />
                ) : (
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                )}
                <div>
                  <p className="font-medium">{expenseStatus.message}</p>
                  <p className="text-xs opacity-75">{expenseStatus.timestamp}</p>
                </div>
              </div>
            )}
            <button
              type="button"
              onClick={handleExportExpenses}
              disabled={loadingExpenses}
              className="w-full bg-amber-600 hover:bg-amber-700 disabled:bg-slate-700 text-white font-semibold py-3 rounded flex items-center justify-center gap-2 transition"
            >
              {loadingExpenses ? 'Buscando na API…' : (
                <>
                  <Download className="w-4 h-4" />
                  Exportar despesas (API)
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PeriodExportScreen;
