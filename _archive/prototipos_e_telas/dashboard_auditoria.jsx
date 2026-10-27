/**
 * Dashboard Logos Auditoria - React/Tailwind
 * Dark mode, pragmático, focado em dados
 * Consome endpoints: /despesas, /fechamentos, /resumo
 */

import React, { useState, useEffect } from 'react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { AlertCircle, TrendingDown, DollarSign, Activity } from 'lucide-react';

const API_BASE = 'http://localhost:8000/auditoria';
const UNIDADES = ['real_01', 'casa_caiada_01', 'vip_01'];
const COLORS = ['#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6', '#8b5cf6'];

export default function DashboardAuditoria() {
  // States
  const [unidadeSelecionada, setUnidadeSelecionada] = useState('real_01');
  const [data, setData] = useState(new Date().toISOString().split('T')[0]);
  const [resumo, setResumo] = useState(null);
  const [despesas, setDespesas] = useState([]);
  const [fechamentos, setFechamentos] = useState(null);
  const [comparativoUnidades, setComparativoUnidades] = useState([]);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState(null);

  // Fetch dados
  useEffect(() => {
    carregarDados();
  }, [unidadeSelecionada, data]);

  const carregarDados = async () => {
    setLoading(true);
    setErro(null);
    try {
      // Resumo (KPIs)
      const resResumo = await fetch(`${API_BASE}/resumo/${unidadeSelecionada}`);
      if (resResumo.ok) {
        setResumo(await resResumo.json());
      }

      // Despesas
      const resDespesas = await fetch(`${API_BASE}/despesas/${unidadeSelecionada}`);
      if (resDespesas.ok) {
        setDespesas(await resDespesas.json());
      }

      // Fechamentos
      const resFechamentos = await fetch(`${API_BASE}/fechamentos/${unidadeSelecionada}`);
      if (resFechamentos.ok) {
        const data = await resFechamentos.json();
        setFechamentos(data);
      }

      // Comparativo unidades
      await carregarComparativo();
    } catch (e) {
      setErro(`Erro ao carregar dados: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const carregarComparativo = async () => {
    try {
      const dados = await Promise.all(
        UNIDADES.map(async (unidade) => {
          const res = await fetch(`${API_BASE}/resumo/${unidade}`);
          return res.ok ? { ...(await res.json()), unidade_id: unidade } : null;
        })
      );
      setComparativoUnidades(dados.filter(Boolean));
    } catch (e) {
      console.error('Erro ao carregar comparativo:', e);
    }
  };

  // Card KPI
  const CardKpi = ({ titulo, valor, subtitulo, icon: Icon, alerta }) => (
    <div className={`bg-gray-900 border rounded-lg p-6 ${alerta ? 'border-red-500' : 'border-gray-700'}`}>
      <div className="flex justify-between items-start">
        <div>
          <p className="text-gray-400 text-sm font-medium">{titulo}</p>
          <p className="text-2xl font-bold text-white mt-2">{valor}</p>
          {subtitulo && <p className="text-gray-500 text-xs mt-1">{subtitulo}</p>}
        </div>
        <Icon className={`w-6 h-6 ${alerta ? 'text-red-500' : 'text-blue-500'}`} />
      </div>
    </div>
  );

  // Tabela Movimentações
  const TabelaMovimentacoes = () => {
    if (!fechamentos || !fechamentos.fechamentos || fechamentos.fechamentos.length === 0) {
      return <p className="text-gray-400 text-sm">Sem dados de movimentações</p>;
    }

    const movs = fechamentos.fechamentos[0]?.movimentacoes || [];
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700">
              <th className="text-left py-2 px-3 text-gray-400 font-medium">Espécie</th>
              <th className="text-right py-2 px-3 text-gray-400 font-medium">Esperado</th>
              <th className="text-right py-2 px-3 text-gray-400 font-medium">Informado</th>
              <th className="text-right py-2 px-3 text-gray-400 font-medium">Diferença</th>
              <th className="text-right py-2 px-3 text-gray-400 font-medium">Variação %</th>
            </tr>
          </thead>
          <tbody>
            {movs.map((mov, idx) => (
              <tr key={idx} className="border-b border-gray-800 hover:bg-gray-800/50">
                <td className="py-3 px-3 text-white capitalize">{mov.especie}</td>
                <td className="py-3 px-3 text-right text-gray-300">R$ {mov.valor_esperado.toFixed(2)}</td>
                <td className="py-3 px-3 text-right text-gray-300">R$ {mov.valor_informado.toFixed(2)}</td>
                <td className={`py-3 px-3 text-right font-medium ${mov.diferenca > 0 ? 'text-red-400' : 'text-green-400'}`}>
                  R$ {mov.diferenca.toFixed(2)}
                </td>
                <td className={`py-3 px-3 text-right font-medium ${Math.abs(mov.variacao_percentual) > 1 ? 'text-orange-400' : 'text-green-400'}`}>
                  {mov.variacao_percentual.toFixed(2)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  // Tabela Despesas
  const TabelaDespesas = () => {
    if (!despesas || despesas.length === 0) {
      return <p className="text-gray-400 text-sm">Sem despesas registradas</p>;
    }

    return (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700">
              <th className="text-left py-2 px-3 text-gray-400 font-medium">Horário</th>
              <th className="text-left py-2 px-3 text-gray-400 font-medium">Categoria</th>
              <th className="text-right py-2 px-3 text-gray-400 font-medium">Valor</th>
              <th className="text-left py-2 px-3 text-gray-400 font-medium">Operador</th>
              <th className="text-center py-2 px-3 text-gray-400 font-medium">Documento</th>
              <th className="text-left py-2 px-3 text-gray-400 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {despesas.map((desp, idx) => (
              <tr key={idx} className={`border-b border-gray-800 hover:bg-gray-800/50 ${!desp.tem_documento ? 'bg-red-900/20' : ''}`}>
                <td className="py-3 px-3 text-gray-300 text-xs">
                  {new Date(desp.horario).toLocaleTimeString('pt-BR')}
                </td>
                <td className="py-3 px-3 text-white capitalize">{desp.categoria.replace('_', ' ')}</td>
                <td className="py-3 px-3 text-right text-gray-300">R$ {desp.valor.toFixed(2)}</td>
                <td className="py-3 px-3 text-gray-400 text-xs">{desp.operador}</td>
                <td className="py-3 px-3 text-center">
                  {desp.tem_documento ? (
                    <span className="text-green-400 text-xs font-medium">✓</span>
                  ) : (
                    <span className="text-red-400 text-xs font-medium">✗</span>
                  )}
                </td>
                <td className="py-3 px-3">
                  <span className={`text-xs px-2 py-1 rounded ${
                    desp.status_justificativa === 'justificada' ? 'bg-green-900/40 text-green-400' : 'bg-yellow-900/40 text-yellow-400'
                  }`}>
                    {desp.status_justificativa}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  // Painel Insights Estoico
  const PainelInsights = () => {
    if (!resumo) return null;

    const insights = [];

    if (resumo.outlier_unidade) {
      insights.push({
        tipo: 'warning',
        msg: `⚠️ Unidade outlier: desvio de ${resumo.desvio_percentual_media_despesas.toFixed(1)}% vs padrão 5%`
      });
    }

    if (resumo.quebra_total > 10) {
      insights.push({
        tipo: 'critical',
        msg: `🔴 Quebra crítica: R$ ${resumo.quebra_total.toFixed(2)} (${resumo.quebra_percentual.toFixed(2)}%)`
      });
    }

    if (resumo.despesas_sem_documento_total > 0) {
      insights.push({
        tipo: 'warning',
        msg: `📄 ${resumo.despesas_sem_documento_total} despesa(s) sem documento anexo`
      });
    }

    if (resumo.despesas_sem_categoria_total > 0) {
      insights.push({
        tipo: 'warning',
        msg: `🏷️ ${resumo.despesas_sem_categoria_total} despesa(s) sem categoria`
      });
    }

    if (resumo.caixas_com_quebra_acima_10 > 0) {
      insights.push({
        tipo: 'warning',
        msg: `${resumo.caixas_com_quebra_acima_10} caixa(s) com quebra > R$ 10`
      });
    }

    if (resumo.caixas_em_auditoria > 0) {
      insights.push({
        tipo: 'info',
        msg: `🔍 ${resumo.caixas_em_auditoria} caixa(s) em auditoria`
      });
    }

    if (insights.length === 0) {
      insights.push({
        tipo: 'success',
        msg: '✓ Sem anomalias detectadas'
      });
    }

    return (
      <div className="space-y-2">
        {insights.map((insight, idx) => (
          <div
            key={idx}
            className={`p-3 rounded border text-sm ${
              insight.tipo === 'critical'
                ? 'bg-red-900/20 border-red-700 text-red-300'
                : insight.tipo === 'warning'
                ? 'bg-yellow-900/20 border-yellow-700 text-yellow-300'
                : insight.tipo === 'success'
                ? 'bg-green-900/20 border-green-700 text-green-300'
                : 'bg-blue-900/20 border-blue-700 text-blue-300'
            }`}
          >
            {insight.msg}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-6">Logos Auditoria</h1>

        <div className="flex gap-4 items-end">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">Unidade</label>
            <select
              value={unidadeSelecionada}
              onChange={(e) => setUnidadeSelecionada(e.target.value)}
              className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white text-sm"
            >
              {UNIDADES.map((u) => (
                <option key={u} value={u}>
                  {u === 'real_01' ? 'Real' : u === 'casa_caiada_01' ? 'Casa Caiada' : 'VIP'}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">Data</label>
            <input
              type="date"
              value={data}
              onChange={(e) => setData(e.target.value)}
              className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-white text-sm"
            />
          </div>

          {loading && <p className="text-gray-400 text-sm">Carregando...</p>}
        </div>
      </div>

      {erro && (
        <div className="bg-red-900/20 border border-red-700 rounded p-3 mb-6 text-red-300 text-sm">
          {erro}
        </div>
      )}

      {/* KPIs */}
      {resumo && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <CardKpi
            titulo="Faturamento Bruto"
            valor={`R$ ${resumo.faturamento_total.toFixed(2)}`}
            subtitulo={`${(resumo.faturamento_total > 0 ? (resumo.despesas_operacionais / resumo.faturamento_total * 100) : 0).toFixed(1)}% em despesas`}
            icon={DollarSign}
          />

          <CardKpi
            titulo="Despesas Operacionais"
            valor={`R$ ${resumo.despesas_operacionais.toFixed(2)}`}
            subtitulo={`Desvio: ${resumo.desvio_percentual_media_despesas.toFixed(1)}%`}
            icon={Activity}
          />

          <CardKpi
            titulo="Saldo em Espécie"
            valor={`R$ ${resumo.saldo_especie_total.toFixed(2)}`}
            subtitulo={`${resumo.caixas_fechados} caixas fechados`}
            icon={DollarSign}
          />

          <CardKpi
            titulo="Quebra de Caixa"
            valor={`R$ ${resumo.quebra_total.toFixed(2)}`}
            subtitulo={`${resumo.quebra_percentual.toFixed(2)}% do faturamento`}
            icon={TrendingDown}
            alerta={resumo.quebra_total > 10}
          />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Comparativo Unidades */}
          {comparativoUnidades.length > 0 && (
            <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4">Comparativo: Despesas vs Faturamento</h3>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={comparativoUnidades}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="unidade_id" stroke="#9ca3af" />
                  <YAxis stroke="#9ca3af" />
                  <Tooltip contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151' }} />
                  <Legend />
                  <Bar dataKey="faturamento_total" fill="#3b82f6" name="Faturamento" />
                  <Bar dataKey="despesas_operacionais" fill="#ef4444" name="Despesas" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Movimentações */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-4">Movimentação por Espécie</h3>
            <TabelaMovimentacoes />
          </div>

          {/* Despesas */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-4">Auditoria de Despesas</h3>
            <TabelaDespesas />
          </div>
        </div>

        {/* Sidebar Insights */}
        <div className="bg-gray-900 border border-gray-700 rounded-lg p-6 h-fit">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-yellow-500" />
            Insights do Auditor
          </h3>
          <PainelInsights />
        </div>
      </div>

      {/* Footer */}
      <div className="mt-8 text-center text-gray-500 text-xs">
        <p>Logos Auditoria v1.0 • API: {API_BASE}</p>
      </div>
    </div>
  );
}
