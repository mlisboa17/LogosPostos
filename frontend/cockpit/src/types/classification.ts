export type EstadoRevisao =
  | "PENDENTE_REVISAO"
  | "CLASSIFICADO"
  | "BLOQUEADO"
  | "CANCELADO";

export interface ItemFilaRevisao {
  id: number;
  hash_idempotencia: string;
  empresa_codigo: number;
  conta_financeira_codigo: number;
  data_movimento: string;
  valor: number;
  valor_formatado: string;
  descricao: string;
  referencia_evidencias?: string | null;
  sugestao_plano_codigo?: number | null;
  sugestao_plano_descricao?: string | null;
  confianca_ia: number;
  justificativa_ia?: string | null;
  travas_encontradas: string[];
  status: EstadoRevisao;
  decisao_humana?: string | null;
  plano_definitivo_codigo?: number | null;
  plano_definitivo_descricao?: string | null;
  centro_custo_definitivo_codigo?: number | null;
  revisor?: string | null;
  revisado_em?: string | null;
  versao: number;
  criado_em: string;
  atualizado_em: string;
}

export interface HistoricoEvento {
  id: number;
  acao: string;
  status_anterior?: string | null;
  status_novo: string;
  usuario_ou_sistema: string;
  justificativa?: string | null;
  detalhes?: string | null;
  timestamp: string;
}

export interface PlanoContaFolha {
  plano_conta_codigo: number;
  descricao: string;
  hierarquia: string;
  grupo?: string | null;
  natureza: string;
}

export interface MetricasRevisaoIA {
  total_avaliados: number;
  acertos_ia: number;
  taxa_acerto_ia: number;
  total_pendentes: number;
  total_bloqueados: number;
  total_classificados: number;
  total_cancelados: number;
}
