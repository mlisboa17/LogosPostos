import React, { useState, useEffect } from 'react';
import { Download, Calendar, AlertCircle, CheckCircle2, Loader, Eye, Edit2, Trash2, Plus } from 'lucide-react';

const LogosAuditoriaClient = () => {
  // ============ CONFIG ============
  const API_BASE = "https://api.webposto.com.br";
  const API_TOKEN = "seu_token_aqui"; // DO .env WEBPOSTO_BEARER_TOKEN
  const UNIDADES = [
    { id: "real_01", nome: "Real" },
    { id: "casa_caiada_01", nome: "Casa Caiada" },
    { id: "vip_01", nome: "VIP" }
  ];

  // ============ STATE ============
  const [startDate, setStartDate] = useState('2026-04-01');
  const [endDate, setEndDate] = useState('2026-04-12');
  const [selectedUnidade, setSelectedUnidade] = useState("real_01");
  const [activeTab, setActiveTab] = useState("export"); // export, despesas, fechamentos, resumo

  // Data states
  const [despesas, setDespesas] = useState([]);
  const [fechamentos, setFechamentos] = useState(null);
  const [resumo, setResumo] = useState(null);
  const [despesasPorCategoria, setDespesasPorCategoria] = useState({});

  // UI states
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState({});
  const [successMessages, setSuccessMessages] = useState({});

  // Form states
  const [novaDesesa, setNovaDesesa] = useState({
    categoria: "gelo",
    valor: "",
    operador: "",
    descricao: ""
  });

  const [editingExpense, setEditingExpense] = useState(null);

  // ============ HTTP HELPERS ============
  const headers = {
    "Authorization": `Bearer ${API_TOKEN}`,
    "Content-Type": "application/json"
  };

  const apiCall = async (method, endpoint, body = null) => {
    try {
      const options = {
        method,
        headers
      };

      if (body) {
        options.body = JSON.stringify(body);
      }

      const response = await fetch(`${API_BASE}${endpoint}`, options);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`API Error [${method} ${endpoint}]:`, error);
      throw error;
    }
  };

  // ============ API METHODS ============
  const handleGetDespesas = async () => {
    setLoading(true);
    setErrors({ ...errors, despesas: null });
    try {
      const data = await apiCall("GET", `/auditoria/despesas/${selectedUnidade}`);
      setDespesas(data);
      setSuccessMessages({ ...successMessages, despesas: `✓ ${data.length} despesas carregadas` });
      setTimeout(() => setSuccessMessages(prev => ({ ...prev, despesas: null })), 3000);
    } catch (error) {
      setErrors({ ...errors, despesas: error.message });
    } finally {
      setLoading(false);
    }
  };

  const handleGetFechamentos = async () => {
    setLoading(true);
    setErrors({ ...errors, fechamentos: null });
    try {
      const data = await apiCall("GET", `/auditoria/fechamentos/${selectedUnidade}`);
      setFechamentos(data);
      setSuccessMessages({ ...successMessages, fechamentos: `✓ ${data.total_caixas} fechamentos carregados` });
      setTimeout(() => setSuccessMessages(prev => ({ ...prev, fechamentos: null })), 3000);
    } catch (error) {
      setErrors({ ...errors, fechamentos: error.message });
    } finally {
      setLoading(false);
    }
  };

  const handleGetResumo = async () => {
    setLoading(true);
    setErrors({ ...errors, resumo: null });
    try {
      const data = await apiCall("GET", `/auditoria/resumo/${selectedUnidade}`);
      setResumo(data);
      setSuccessMessages({ ...successMessages, resumo: "✓ Resumo carregado com sucesso" });
      setTimeout(() => setSuccessMessages(prev => ({ ...prev, resumo: null })), 3000);
    } catch (error) {
      setErrors({ ...errors, resumo: error.message });
    } finally {
      setLoading(false);
    }
  };

  const handleGetDespesasPorCategoria = async () => {
    setLoading(true);
    setErrors({ ...errors, categoria: null });
    try {
      const data = await apiCall("GET", `/auditoria/despesas-por-categoria/${selectedUnidade}`);
      setDespesasPorCategoria(data);
      setSuccessMessages({ ...successMessages, categoria: "✓ Despesas por categoria carregadas" });
      setTimeout(() => setSuccessMessages(prev => ({ ...prev, categoria: null })), 3000);
    } catch (error) {
      setErrors({ ...errors, categoria: error.message });
    } finally {
      setLoading(false);
    }
  };

  const handleRegistrarDespesa = async () => {
    setLoading(true);
    setErrors({ ...errors, registrar: null });
    try {
      const payload = {
        id: `exp_${Date.now()}`,
        unidade_id: selectedUnidade,
        caixa_tipo: "pista",
        horario: new Date().toISOString(),
        categoria: novaDesesa.categoria,
        valor: parseFloat(novaDesesa.valor),
        operador: novaDesesa.operador,
        descricao: novaDesesa.descricao || undefined,
        status_justificativa: "pendente",
        tem_documento: false
      };

      const data = await apiCall("POST", "/auditoria/registrar-despesa", payload);

      setDespesas([...despesas, data]);
      setNovaDesesa({ categoria: "gelo", valor: "", operador: "", descricao: "" });
      setSuccessMessages({ ...successMessages, registrar: "✓ Despesa registrada com sucesso" });
      setTimeout(() => setSuccessMessages(prev => ({ ...prev, registrar: null })), 3000);
    } catch (error) {
      setErrors({ ...errors, registrar: error.message });
    } finally {
      setLoading(false);
    }
  };

  const handleExportJSON = (data, filename) => {
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  // ============ UI COMPONENTS ============
  const ErrorMessage = ({ message }) => {
    if (!message) return null;
    return (
      <div className="flex items-start gap-2 p-3 rounded mb-4 bg-red-900/30 border border-red-700 text-red-300 text-sm">
        <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
        <div>
          <p className="font-medium">Erro</p>
          <p className="text-xs opacity-75">{message}</p>
        </div>
      </div>
    );
  };

  const SuccessMessage = ({ message }) => {
    if (!message) return null;
    return (
      <div className="flex items-start gap-2 p-3 rounded mb-4 bg-green-900/30 border border-green-700 text-green-300 text-sm">
        <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" />
        <p className="font-medium">{message}</p>
      </div>
    );
  };

  const LoadingButton = ({ onClick, children, disabled, color = "blue" }) => {
    const colors = {
      blue: "bg-blue-600 hover:bg-blue-700",
      green: "bg-green-600 hover:bg-green-700",
      amber: "bg-amber-600 hover:bg-amber-700"
    };

    return (
      <button
        onClick={onClick}
        disabled={loading || disabled}
        className={`${colors[color]} disabled:bg-slate-700 text-white font-semibold py-2 px-4 rounded flex items-center justify-center gap-2 transition w-full`}
      >
        {loading ? (
          <>
            <div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
            Carregando...
          </>
        ) : (
          children
        )}
      </button>
    );
  };

  // ============ RENDER ============
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">Logos Auditoria</h1>
          <p className="text-slate-400">Sistema integrado de auditoria com API webPosto</p>
        </div>

        {/* Config Section */}
        <div className="bg-slate-900 border border-slate-700 rounded-lg p-6 mb-8">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">Unidade</label>
              <select
                value={selectedUnidade}
                onChange={(e) => setSelectedUnidade(e.target.value)}
                className="w-full px-4 py-2 bg-slate-800 border border-slate-600 rounded text-white focus:border-blue-500 focus:outline-none"
              >
                {UNIDADES.map(u => (
                  <option key={u.id} value={u.id}>{u.nome}</option>
                ))}
              </select>
            </div>
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

        {/* Tabs */}
        <div className="flex gap-2 mb-6 border-b border-slate-700">
          {[
            { id: "export", label: "📤 Exportar", icon: "Download" },
            { id: "despesas", label: "💰 Despesas", icon: "Eye" },
            { id: "fechamentos", label: "📊 Fechamentos", icon: "Eye" },
            { id: "resumo", label: "📈 Resumo/Insights", icon: "Eye" }
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 font-semibold transition border-b-2 ${
                activeTab === tab.id
                  ? "text-blue-400 border-blue-400"
                  : "text-slate-400 border-transparent hover:text-slate-300"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Panel */}
          <div className="lg:col-span-2">
            {/* EXPORT TAB */}
            {activeTab === "export" && (
              <div className="space-y-4">
                <SuccessMessage message={successMessages.despesas} />
                <ErrorMessage message={errors.despesas} />

                <div className="bg-slate-900 border border-slate-700 rounded-lg p-6">
                  <h3 className="text-lg font-bold mb-4 text-green-400">Exportar Despesas</h3>
                  <LoadingButton onClick={handleGetDespesas} color="green">
                    <Download className="w-4 h-4" />
                    Carregar & Exportar
                  </LoadingButton>
                </div>

                <SuccessMessage message={successMessages.fechamentos} />
                <ErrorMessage message={errors.fechamentos} />

                <div className="bg-slate-900 border border-slate-700 rounded-lg p-6">
                  <h3 className="text-lg font-bold mb-4 text-blue-400">Exportar Fechamentos</h3>
                  <LoadingButton onClick={handleGetFechamentos} color="blue">
                    <Download className="w-4 h-4" />
                    Carregar & Exportar
                  </LoadingButton>
                </div>

                <SuccessMessage message={successMessages.resumo} />
                <ErrorMessage message={errors.resumo} />

                <div className="bg-slate-900 border border-slate-700 rounded-lg p-6">
                  <h3 className="text-lg font-bold mb-4 text-amber-400">Exportar Resumo</h3>
                  <LoadingButton onClick={handleGetResumo} color="amber">
                    <Download className="w-4 h-4" />
                    Carregar & Exportar
                  </LoadingButton>
                </div>
              </div>
            )}

            {/* DESPESAS TAB */}
            {activeTab === "despesas" && (
              <div className="space-y-4">
                <SuccessMessage message={successMessages.despesas} />
                <ErrorMessage message={errors.despesas} />

                <div className="bg-slate-900 border border-slate-700 rounded-lg p-6">
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="text-lg font-bold text-green-400">Despesas Registradas</h3>
                    <LoadingButton onClick={handleGetDespesas} disabled={loading} color="green">
                      <Eye className="w-4 h-4" />
                      Atualizar
                    </LoadingButton>
                  </div>

                  {despesas.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="border-b border-slate-600">
                          <tr>
                            <th className="text-left py-2 px-2">Hora</th>
                            <th className="text-left py-2 px-2">Categoria</th>
                            <th className="text-right py-2 px-2">Valor</th>
                            <th className="text-left py-2 px-2">Operador</th>
                            <th className="text-left py-2 px-2">Status</th>
                            <th className="text-center py-2 px-2">Doc</th>
                          </tr>
                        </thead>
                        <tbody>
                          {despesas.map(d => (
                            <tr key={d.id} className="border-b border-slate-700 hover:bg-slate-800">
                              <td className="py-2 px-2 text-xs text-slate-400">{new Date(d.horario).toLocaleTimeString('pt-BR')}</td>
                              <td className="py-2 px-2 font-medium text-white">{d.categoria}</td>
                              <td className="py-2 px-2 text-right text-green-400 font-semibold">R$ {d.valor.toFixed(2)}</td>
                              <td className="py-2 px-2 text-slate-300">{d.operador}</td>
                              <td className="py-2 px-2">
                                <span className={`px-2 py-1 rounded text-xs font-semibold ${
                                  d.status_justificativa === 'justificada' ? 'bg-green-900 text-green-300' :
                                  d.status_justificativa === 'pendente' ? 'bg-yellow-900 text-yellow-300' :
                                  'bg-red-900 text-red-300'
                                }`}>
                                  {d.status_justificativa}
                                </span>
                              </td>
                              <td className="py-2 px-2 text-center">
                                {d.tem_documento ? (
                                  <CheckCircle2 className="w-4 h-4 text-green-400 inline" />
                                ) : (
                                  <AlertCircle className="w-4 h-4 text-red-400 inline" />
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-slate-400 text-center py-4">Nenhuma despesa carregada. Clique em "Atualizar".</p>
                  )}
                </div>
              </div>
            )}

            {/* FECHAMENTOS TAB */}
            {activeTab === "fechamentos" && (
              <div className="space-y-4">
                <SuccessMessage message={successMessages.fechamentos} />
                <ErrorMessage message={errors.fechamentos} />

                <div className="bg-slate-900 border border-slate-700 rounded-lg p-6">
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="text-lg font-bold text-blue-400">Fechamentos do Dia</h3>
                    <LoadingButton onClick={handleGetFechamentos} disabled={loading} color="blue">
                      <Eye className="w-4 h-4" />
                      Atualizar
                    </LoadingButton>
                  </div>

                  {fechamentos && (
                    <div className="space-y-4">
                      <div className="bg-slate-800 rounded p-4">
                        <p className="text-sm text-slate-300">📊 <strong>{fechamentos.total_caixas}</strong> caixas | 💰 <strong>R$ {fechamentos.resumo?.faturamento_total.toFixed(2)}</strong> faturamento</p>
                      </div>

                      {fechamentos.fechamentos.map(f => (
                        <div key={f.id} className="bg-slate-800 rounded p-4 border border-slate-700">
                          <div className="grid grid-cols-2 gap-4 text-sm">
                            <div>
                              <p className="text-slate-400">Caixa</p>
                              <p className="font-semibold text-white">{f.caixa_tipo}</p>
                            </div>
                            <div>
                              <p className="text-slate-400">Horário</p>
                              <p className="font-semibold text-white">{new Date(f.horario_abertura).toLocaleTimeString('pt-BR')} - {new Date(f.horario_fechamento).toLocaleTimeString('pt-BR')}</p>
                            </div>
                            <div>
                              <p className="text-slate-400">Faturamento</p>
                              <p className="font-semibold text-green-400">R$ {f.faturamento_bruto.toFixed(2)}</p>
                            </div>
                            <div>
                              <p className="text-slate-400">Quebra</p>
                              <p className={`font-semibold ${f.quebra_caixa > 10 ? 'text-red-400' : 'text-yellow-400'}`}>R$ {f.quebra_caixa.toFixed(2)}</p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* RESUMO TAB */}
            {activeTab === "resumo" && (
              <div className="space-y-4">
                <SuccessMessage message={successMessages.resumo} />
                <ErrorMessage message={errors.resumo} />

                <div className="bg-slate-900 border border-slate-700 rounded-lg p-6">
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="text-lg font-bold text-amber-400">Resumo & Insights Estoicos</h3>
                    <LoadingButton onClick={handleGetResumo} disabled={loading} color="amber">
                      <Eye className="w-4 h-4" />
                      Atualizar
                    </LoadingButton>
                  </div>

                  {resumo && (
                    <div className="grid grid-cols-2 gap-4">
                      <div className="bg-slate-800 rounded p-4">
                        <p className="text-slate-400 text-sm">Faturamento</p>
                        <p className="text-2xl font-bold text-green-400">R$ {resumo.faturamento_total.toFixed(2)}</p>
                      </div>
                      <div className="bg-slate-800 rounded p-4">
                        <p className="text-slate-400 text-sm">Despesas</p>
                        <p className="text-2xl font-bold text-yellow-400">R$ {resumo.despesas_operacionais.toFixed(2)}</p>
                      </div>
                      <div className="bg-slate-800 rounded p-4">
                        <p className="text-slate-400 text-sm">Quebra Total</p>
                        <p className={`text-2xl font-bold ${resumo.quebra_total > 10 ? 'text-red-400' : 'text-blue-400'}`}>R$ {resumo.quebra_total.toFixed(2)}</p>
                      </div>
                      <div className="bg-slate-800 rounded p-4">
                        <p className="text-slate-400 text-sm">Desvio %</p>
                        <p className={`text-2xl font-bold ${resumo.outlier_unidade ? 'text-red-400' : 'text-green-400'}`}>{resumo.desvio_percentual_media_despesas.toFixed(1)}%</p>
                      </div>
                      <div className="bg-slate-800 rounded p-4">
                        <p className="text-slate-400 text-sm">Caixas Fechados</p>
                        <p className="text-2xl font-bold text-blue-400">{resumo.caixas_fechados}</p>
                      </div>
                      <div className="bg-slate-800 rounded p-4">
                        <p className="text-slate-400 text-sm">Sem Documento</p>
                        <p className="text-2xl font-bold text-red-400">{resumo.despesas_sem_documento_total}</p>
                      </div>

                      {resumo.outlier_unidade && (
                        <div className="col-span-2 bg-red-900/30 border border-red-700 rounded p-4">
                          <p className="text-red-300 font-semibold">⚠️ OUTLIER: Unidade tem desvio anormal de despesas (|desvio| > 10%)</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Sidebar: Registrar Despesa */}
          <div className="bg-slate-900 border border-slate-700 rounded-lg p-6 h-fit">
            <h3 className="text-lg font-bold mb-4 text-blue-400">➕ Registrar Despesa</h3>

            <SuccessMessage message={successMessages.registrar} />
            <ErrorMessage message={errors.registrar} />

            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">Categoria</label>
                <select
                  value={novaDesesa.categoria}
                  onChange={(e) => setNovaDesesa({ ...novaDesesa, categoria: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded text-white text-sm focus:border-blue-500 focus:outline-none"
                >
                  <option value="gelo">Gelo</option>
                  <option value="luz">Luz</option>
                  <option value="vale_operador">Vale Operador</option>
                  <option value="manutencao">Manutenção</option>
                  <option value="combustivel">Combustível</option>
                  <option value="limpeza">Limpeza</option>
                  <option value="insumos">Insumos</option>
                  <option value="outros">Outros</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">Valor (R$)</label>
                <input
                  type="number"
                  step="0.01"
                  value={novaDesesa.valor}
                  onChange={(e) => setNovaDesesa({ ...novaDesesa, valor: e.target.value })}
                  placeholder="0.00"
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded text-white text-sm focus:border-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">Operador</label>
                <input
                  type="text"
                  value={novaDesesa.operador}
                  onChange={(e) => setNovaDesesa({ ...novaDesesa, operador: e.target.value })}
                  placeholder="Nome"
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded text-white text-sm focus:border-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">Descrição</label>
                <textarea
                  value={novaDesesa.descricao}
                  onChange={(e) => setNovaDesesa({ ...novaDesesa, descricao: e.target.value })}
                  placeholder="Opcional"
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded text-white text-sm focus:border-blue-500 focus:outline-none resize-none"
                  rows="2"
                />
              </div>

              <LoadingButton
                onClick={handleRegistrarDespesa}
                disabled={!novaDesesa.valor || !novaDesesa.operador}
                color="blue"
              >
                <Plus className="w-4 h-4" />
                Registrar
              </LoadingButton>
            </div>

            {/* Despesas por Categoria */}
            <div className="mt-8 pt-6 border-t border-slate-700">
              <h4 className="text-sm font-bold mb-3 text-slate-300">Resumo por Categoria</h4>
              <LoadingButton onClick={handleGetDespesasPorCategoria} disabled={loading} color="blue">
                <Eye className="w-4 h-4" />
                Carregar
              </LoadingButton>

              {Object.keys(despesasPorCategoria).length > 0 && (
                <div className="mt-3 space-y-2 text-sm">
                  {Object.entries(despesasPorCategoria).map(([cat, data]) => (
                    <div key={cat} className="bg-slate-800 rounded p-2">
                      <p className="font-semibold text-slate-300">{cat.toUpperCase()}</p>
                      <p className="text-slate-400 text-xs">R$ {data.total.toFixed(2)} ({data.qtd}x) • {data.sem_documento} sem doc</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LogosAuditoriaClient;