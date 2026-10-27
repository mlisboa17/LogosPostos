export type SeveridadeAlerta = "vermelho" | "laranja";

export interface CaixaInfo {
  codigo: number;
  empresa_codigo: number;
  data: string;
  turno: string;
  pdv_codigo: number;
  centro_custo?: number | null;
  funcionario_codigo: number;
  abertura: string;
  fechamento?: string | null;
  fechado: boolean;
  consolidado: boolean;
  bloqueado: boolean;
  apurado?: number | string | null;
}

export interface LinhaModalidade {
  modalidade: string;
  rotulo: string;
  apresentado: number | string;
  apurado: number | string;
  diferenca: number | string;
}

export interface SangriaInfo {
  codigo: number;
  empresa_codigo: number;
  caixa_codigo: number;
  data_hora: string;
  valor: number | string;
  tipo?: string | null;
}

export interface AlertaCaixa {
  codigo: string;
  severidade: SeveridadeAlerta;
  mensagem: string;
  valor?: number | string | null;
  referencia?: number | null;
}

export interface MovimentoDespesa {
  codigo: number;
  caixa_codigo: number;
  tipo: string;
  valor: number | string;
  plano_conta_codigo?: string | null;
  descricao?: string | null;
  plano_conta_nome?: string | null;
  centro_custo?: number | null;
}

export interface DescontoFalta {
  situacao: "sem_desconto" | "descontado" | "divergente";
  falta: number | string;
  total_vale: number | string;
  diferenca: number | string;
}

export interface FuncionarioFechamento {
  codigo: number;
  nome: string;
  funcao?: string | null;
  responsavel?: boolean;
  valor_apurado: number | string;
  valor_declarado: number | string;
  quebra_sobra: number | string;
  vales_associados: number | string;
  tem_vale_falta?: boolean;
  valor_vale_falta?: number | string;
  status_vale?: "com_vale" | "pendente_sem_vale" | "sem_falta" | string;
  alertas?: string[];
}

export interface AuditoriaCaixaItem {
  caixa: CaixaInfo;
  modalidades: LinhaModalidade[];
  sangrias?: SangriaInfo[];
  total_sangrias?: number | string;
  alertas: AlertaCaixa[];
  informativos?: string[];
  despesas?: MovimentoDespesa[];
  desconto_falta?: DescontoFalta | null;
  funcionarios_participantes?: FuncionarioFechamento[];
  quebra: number | string;
  severidade?: SeveridadeAlerta | null;
}

export interface ProvenienciaAuditoria {
  execucao_id: string;
  executado_em: string;
  versao_regra: string;
  fonte_sangrias?: string;
  extratos?: string[];
  outras_fontes?: string[];
}

export interface ResultadoAuditoriaFechamento {
  empresa_codigo: number;
  inicio: string;
  fim: string;
  quebra_total: number | string;
  total_sangrias?: number | string;
  caixas: AuditoriaCaixaItem[];
  proveniencia: ProvenienciaAuditoria;
  execucoes?: ProvenienciaAuditoria[];
}

export interface RelatorioCaixaItem {
  unidade: number;
  nome: string;
  markdown: string;
}

export interface RelatorioCaixaResponse {
  dia: string;
  relatorios: RelatorioCaixaItem[];
}

export interface PendenciaCaixa {
  id: string;
  unidade: number;
  dia: string;
  tipo: string;
  severidade: SeveridadeAlerta;
  status: "aberta" | "justificada" | "aprovada" | "recusada";
  mensagem: string;
  valor?: number | string | null;
  funcionario_codigo?: number | null;
  vencida?: boolean;
}

export interface CentroCustoItem {
  codigo: number;
  nome: string;
  tipo: string;
}

export interface FuncionarioItem {
  codigo: number;
  nome: string;
}

export interface PdvItem {
  codigo: number;
  nome: string;
}

export interface TipoDataItem {
  valor: string;
  rotulo: string;
}

export interface ModoVisualizacaoItem {
  valor: "analitico" | "consolidado";
  rotulo: string;
}

export interface FiltrosOperacionaisResponse {
  unidade: number;
  centros_custo: CentroCustoItem[];
  turnos: string[];
  pdvs: PdvItem[];
  funcionarios: FuncionarioItem[];
  tipos_data: TipoDataItem[];
  modos_visualizacao?: ModoVisualizacaoItem[];
}

export interface FechamentoFiltrosParams {
  centro_custo?: number;
  turno?: string;
  funcionario_codigo?: number;
  pdv_codigo?: number;
  tipo_data?: string;
  consolidado?: boolean;
}

export interface ModalidadeConsolidada {
  modalidade: string;
  rotulo: string;
  apresentado: number;
  apurado: number;
  diferenca: number;
}

export interface DiaConsolidado {
  data: string;
  totalCaixas: number;
  pdvs: number[];
  funcionarios: number[];
  turnos: string[];
  apuradoTotal: number;
  declaradoTotal: number;
  quebraTotal: number;
  severidade: SeveridadeAlerta | null;
  caixas: AuditoriaCaixaItem[];
  modalidadesConsolidadas: ModalidadeConsolidada[];
  alertasTotais: AlertaCaixa[];
  despesasTotais: MovimentoDespesa[];
}


