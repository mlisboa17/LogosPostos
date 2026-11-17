import { z } from "zod";

const text = (max = 500) => z.string().max(max);
const count = z.number().int().nonnegative();
const decimal = z.string().regex(/^(?:0|[1-9]\d{0,29})(?:\.\d{1,30})?$/);
const dateOnly = z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine((value) => {
  const date = new Date(`${value}T00:00:00.000Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
});
const timestamp = z.string().datetime({ offset: true });
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const source = z.string().regex(/^OFX-SINTETICO-[A-Za-z0-9._-]+:[a-f0-9]{64}$/);
const identity = {
  empresa_codigo: z.literal(0),
  conta_webposto_codigo: z.literal(0),
  banco: z.literal("BANCO-FICTICIO"),
  conta_sufixo: z.literal("CONTA-SINTETICA"),
  data: dateOnly,
  valor: decimal,
  fitid: z.string().max(200).regex(/^FITID-SINTETICO-[A-Za-z0-9-]+$/),
  origem_extrato: source,
  hash_extrato: hash,
};
const description = z.literal("PIX ENVIADO - FAVORECIDO FICTICIO");
const candidate = z.object({
  ...identity,
  favorecido: z.literal("FAVORECIDO FICTICIO"),
  descricao_extrato: description,
  tipo: z.enum(["imposto", "QR Code", "boleto", "PIX pessoa"]),
  sugestao_plano_codigo: z.null(),
  sugestao_plano_nome: z.literal(""),
  sugestao_centro_codigo: z.null(),
  sugestao_centro_nome: z.literal(""),
  sugestao_fornecedor_codigo: z.null(),
  sugestao_fornecedor_nome: z.literal(""),
  origem_sugestao: z.literal("pendente de evidência; revisão humana obrigatória"),
  observacao: z.literal("Candidato provável; não confirmado como despesa sem lançamento."),
  status_triagem: z.literal("PENDENTE_REVISAO"),
  evidencia_conciliacao: z.literal(
    "Cobertura ERP não verificada; candidato pendente de revisão humana. " +
    "Não é possível concluir conciliação ou ausência de lançamento."
  ),
}).strict();
const evidence = z.object({
  ...identity,
  origem: z.literal("OFX:BANCO-FICTICIO"),
  descricao: description,
  classificacao: z.literal("CLASSIFICACAO_DESCONHECIDA"),
  status: z.literal("AMBIGUO"),
  evidencia_conciliacao: z.literal("FITID repetido com dados divergentes entre extratos."),
  origens_extrato: z.array(source).max(20),
}).strict();
const snapshot = z.object({
  endpoint: z.enum(["/INTEGRACAO/V1/TITULOS_PAGAR", "/INTEGRACAO/V1/MOVIMENTOS_CONTA"]),
  empresa_codigo: z.literal(0),
  data_inicial: dateOnly,
  data_final: dateOnly,
  capturado_em: timestamp,
  origem_atualizada_em: timestamp,
  sha256: hash,
  declaracao_cobertura: z.enum(["DECLARADA", "INCOMPLETA", "NAO_DECLARADA"]),
  status_cobertura: z.literal("COBERTURA_NAO_VERIFICADA"),
}).strict();
const reportSchema = z.object({
  schema_version: z.literal(1),
  sintetico: z.literal(true),
  cnpj_sintetico: z.literal("00.000.000/0000-00"),
  referencia_temporal: timestamp,
  max_idade_horas: z.number().int().min(1).max(168),
  snapshots: z.object({ titulos: snapshot, movimentos: snapshot }).strict(),
  resumo: z.object({
    unidade_codigo: z.literal(0),
    unidade_nome: z.literal("EMPRESA-SINTETICA-001"),
    data_de: dateOnly,
    data_ate: dateOnly,
    despesas: z.array(candidate).max(5000),
    total_geral: decimal,
    totais_por_tipo: z.record(text(100), z.tuple([count, decimal])),
    debitos_ignorados_qtd: z.literal(0),
    debitos_ignorados_total: z.literal("0"),
    debitos_registrados_qtd: z.literal(0),
    debitos_registrados_total: z.literal("0"),
    debitos_com_titulo: z.array(z.never()).max(0),
    debitos_com_titulo_qtd: z.literal(0),
    debitos_com_titulo_total: z.literal("0"),
    movimentacoes_auditadas: z.array(evidence).max(5000),
    triagem_completa: z.boolean(),
    fontes_nao_mapeadas: z.array(source).max(500),
    fontes_cobertura_incompleta: z.array(source).max(500),
  }).strict(),
}).strict();

export type Fin02DemoReport = z.infer<typeof reportSchema>;

function shiftedDate(value: string, days: number): string {
  const date = new Date(`${value}T00:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function canonicalDecimal(value: string): string {
  const [whole, fraction = ""] = value.split(".");
  const trimmed = fraction.replace(/0+$/, "");
  return `${whole}${trimmed ? `.${trimmed}` : ""}`;
}

function sumDecimals(values: string[]): string {
  const scale = Math.max(0, ...values.map((value) => value.split(".")[1]?.length ?? 0));
  const sum = values.reduce((total, value) => {
    const [whole, fraction = ""] = value.split(".");
    return total + BigInt(`${whole}${fraction.padEnd(scale, "0")}`);
  }, BigInt(0));
  const digits = sum.toString().padStart(scale + 1, "0");
  return canonicalDecimal(scale ? `${digits.slice(0, -scale)}.${digits.slice(-scale)}` : digits);
}

function validateConsistency(report: Fin02DemoReport): void {
  const { resumo, snapshots } = report;
  if (resumo.data_de > resumo.data_ate) throw new Error("O período do resumo está invertido.");
  if (
    snapshots.titulos.endpoint !== "/INTEGRACAO/V1/TITULOS_PAGAR" ||
    snapshots.movimentos.endpoint !== "/INTEGRACAO/V1/MOVIMENTOS_CONTA" ||
    snapshots.titulos.data_inicial !== shiftedDate(resumo.data_de, -45) ||
    snapshots.titulos.data_final !== shiftedDate(resumo.data_ate, 45) ||
    snapshots.movimentos.data_inicial !== resumo.data_de ||
    snapshots.movimentos.data_final !== resumo.data_ate
  ) throw new Error("Os metadados dos snapshots não correspondem ao resumo FIN-02.");
  const reference = Date.parse(report.referencia_temporal);
  const maxAge = report.max_idade_horas * 60 * 60 * 1000;
  const now = Date.now();
  if (reference > now + 5 * 60 * 1000 || now - reference > maxAge) {
    throw new Error("O relatório está desatualizado ou tem timestamp inconsistente.");
  }
  for (const item of Object.values(snapshots)) {
    const captured = Date.parse(item.capturado_em);
    const updated = Date.parse(item.origem_atualizada_em);
    if (
      updated > captured || captured > reference ||
      reference - updated > maxAge || now - updated > maxAge ||
      now - captured > maxAge
    ) throw new Error("Os snapshots estão desatualizados ou têm timestamps inconsistentes.");
  }
  for (const item of [...resumo.despesas, ...resumo.movimentacoes_auditadas]) {
    if (
      item.data < resumo.data_de || item.data > resumo.data_ate ||
      !item.origem_extrato.endsWith(`:${item.hash_extrato}`)
    ) throw new Error("Data ou hash de origem incompatível com o contrato sintético.");
  }
  if (sumDecimals(resumo.despesas.map((item) => item.valor)) !== canonicalDecimal(resumo.total_geral)) {
    throw new Error("O total geral não corresponde aos valores dos candidatos.");
  }
  const tipos = new Map<string, string[]>();
  for (const item of resumo.despesas) {
    tipos.set(item.tipo, [...(tipos.get(item.tipo) ?? []), item.valor]);
  }
  if (Object.keys(resumo.totais_por_tipo).length !== tipos.size) {
    throw new Error("Os totais por tipo não correspondem aos candidatos.");
  }
  for (const [tipo, valores] of tipos) {
    const total = resumo.totais_por_tipo[tipo];
    if (!total || total[0] !== valores.length || canonicalDecimal(total[1]) !== sumDecimals(valores)) {
      throw new Error("Os totais por tipo não correspondem aos candidatos.");
    }
  }
}

export function parseFin02DemoReport(value: unknown): Fin02DemoReport {
  const parsed = reportSchema.safeParse(value);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    const field = issue.path.length ? issue.path.join(".") : "arquivo";
    throw new Error(`Formato FIN-02 inválido em ${field}: ${issue.message}`);
  }
  validateConsistency(parsed.data);
  return parsed.data;
}

export const FIN02_DEMO_MAX_FILE_BYTES = 1024 * 1024;
