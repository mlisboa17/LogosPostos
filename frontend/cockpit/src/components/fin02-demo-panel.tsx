"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  FIN02_DEMO_MAX_FILE_BYTES, parseFin02DemoReport, type Fin02DemoReport,
} from "@/lib/fin02-demo-schema";

const MAX_FILE_SIZE_LABEL = "1 MiB";

function formatDate(value: string): string {
  return new Date(`${value}T00:00:00.000Z`).toLocaleDateString("pt-BR", { timeZone: "UTC" });
}

function coverageLabel(declaration: string): string {
  switch (declaration) {
    case "DECLARADA": return "Cobertura declarada pela fonte; não verificada";
    case "INCOMPLETA": return "Fonte declara cobertura incompleta";
    default: return "Fonte não declara cobertura";
  }
}

export function Fin02DemoPanel() {
  const selectionId = useRef(0);
  const [report, setReport] = useState<Fin02DemoReport | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const currentSelection = ++selectionId.current;
    const file = event.currentTarget.files?.[0];
    setReport(null);
    setFileName(null);
    setErrorMessage(null);
    if (!file) return;
    if (file.size > FIN02_DEMO_MAX_FILE_BYTES) {
      setErrorMessage(`Arquivo rejeitado: o limite é ${MAX_FILE_SIZE_LABEL}.`);
      return;
    }
    try {
      const content = await file.text();
      if (currentSelection !== selectionId.current) return;
      const payload: unknown = JSON.parse(content);
      const parsedReport = parseFin02DemoReport(payload);
      if (currentSelection !== selectionId.current) return;
      setReport(parsedReport);
      setFileName(file.name);
    } catch (error) {
      if (currentSelection !== selectionId.current) return;
      setErrorMessage(error instanceof Error
        ? `Arquivo rejeitado: ${error.message}`
        : "Arquivo rejeitado: não foi possível ler o JSON FIN-02.");
    }
  };

  const candidates = report?.resumo.despesas ?? [];
  const ambiguities = report?.resumo.movimentacoes_auditadas.filter((item) => item.status === "AMBIGUO") ?? [];

  return (
    <Card id="fin02-demo-panel" aria-labelledby="fin02-demo-title" className="border-amber-800/50 bg-slate-900/90">
      <CardHeader>
        <CardTitle id="fin02-demo-title">DEMONSTRAÇÃO — DADOS SINTÉTICOS</CardTitle>
        <CardDescription>FIN-02 · Visualização local de arquivo JSON sintético. Não altera a fila de classificação.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p role="note" className="text-sm text-amber-200">
          Somente empresa e conta código 0; CNPJ sintético deliberadamente inválido.
          Os marcadores sintéticos não autenticam origem nem autorizam operações.
          Nenhum resultado confirma despesa sem lançamento ou libera operação financeira.
        </p>
        <div className="space-y-2">
          <label htmlFor="fin02-json-file">Selecionar relatório FIN-02 JSON sintético</label>
          <input id="fin02-json-file" type="file" accept=".json,application/json"
            onChange={handleFileChange} aria-describedby="fin02-file-help fin02-file-status"
            className="block w-full rounded-md border border-slate-700 p-2 text-sm" />
          <p id="fin02-file-help" className="text-xs text-slate-400">
            Leitura somente neste navegador; sem upload, persistência ou envio à rede.
            Tamanho máximo: {MAX_FILE_SIZE_LABEL}.
          </p>
          {errorMessage ? (
            <p id="fin02-file-status" role="alert" className="text-sm text-red-300">{errorMessage}</p>
          ) : (
            <p id="fin02-file-status" role="status" aria-live="polite">
              {fileName ? `Arquivo carregado localmente: ${fileName}` : "Nenhum arquivo carregado."}
            </p>
          )}
        </div>
        {report && (
          <div className="space-y-5">
            <div className="flex flex-wrap gap-2">
              <Badge>CANDIDATOS: {candidates.length}</Badge>
              <Badge>AMBIGUIDADES: {ambiguities.length}</Badge>
              <Badge>COBERTURA_NAO_VERIFICADA</Badge>
            </div>
            <section aria-labelledby="fin02-coverage-title" className="space-y-2">
              <h3 id="fin02-coverage-title">Origem e cobertura</h3>
              <p>{report.resumo.unidade_nome} · período {formatDate(report.resumo.data_de)} a{" "}
                {formatDate(report.resumo.data_ate)} · triagem de fontes completa:{" "}
                {report.resumo.triagem_completa ? "sim" : "não"} · cobertura ERP: não verificada.</p>
              <p>CNPJ sintético (inválido): {report.cnpj_sintetico} · sintetico: true.</p>
              <p>Contrato FIN-02: versão {report.schema_version} · Referência da exportação:{" "}
                {new Date(report.referencia_temporal).toLocaleString("pt-BR")} · idade máxima dos snapshots: {report.max_idade_horas} h.</p>
              <ul className="space-y-1 text-sm">
                {Object.entries(report.snapshots).map(([name, snapshot]) => (
                  <li key={name}>
                    {name === "titulos" ? "Títulos" : "Movimentos"}: {snapshot.endpoint};{" "}
                    {coverageLabel(snapshot.declaracao_cobertura)}; {snapshot.status_cobertura};{" "}
                    captura {new Date(snapshot.capturado_em).toLocaleString("pt-BR")};{" "}
                    atualização {new Date(snapshot.origem_atualizada_em).toLocaleString("pt-BR")};{" "}
                    período {formatDate(snapshot.data_inicial)} a {formatDate(snapshot.data_final)};{" "}
                    SHA-256 <code className="break-all">{snapshot.sha256}</code>.
                  </li>
                ))}
              </ul>
              <p className="break-all text-sm">Fontes não mapeadas: {report.resumo.fontes_nao_mapeadas.join(", ")}.</p>
              <p className="break-all text-sm">Fontes com cobertura incompleta: {report.resumo.fontes_cobertura_incompleta.join(", ")}.</p>
            </section>
            <section aria-labelledby="fin02-candidates-title">
              <h3 id="fin02-candidates-title">Candidatos pendentes de revisão humana</h3>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader><TableRow>
                    <TableHead>Origem / conta</TableHead><TableHead>FITID / data</TableHead>
                    <TableHead>Valor (decimal)</TableHead><TableHead>Estado / evidência</TableHead>
                  </TableRow></TableHeader>
                  <TableBody>{candidates.map((item) => (
                    <TableRow key={`${item.fitid}-${item.origem_extrato}`}>
                      <TableCell className="max-w-72 break-all">{item.origem_extrato}<div>{item.banco} · {item.conta_sufixo}</div></TableCell>
                      <TableCell><code>{item.fitid}</code><div>{formatDate(item.data)}</div></TableCell>
                      <TableCell className="font-mono">{item.valor}</TableCell>
                      <TableCell>{item.status_triagem}<div>{item.evidencia_conciliacao}</div></TableCell>
                    </TableRow>
                  ))}</TableBody>
                </Table>
              </div>
            </section>
            <section aria-labelledby="fin02-ambiguities-title">
              <h3 id="fin02-ambiguities-title">Ambiguidades para revisão humana</h3>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader><TableRow>
                    <TableHead>Origem / conta</TableHead><TableHead>FITID / data</TableHead>
                    <TableHead>Valor (decimal)</TableHead><TableHead>Ambiguidade / evidência</TableHead>
                  </TableRow></TableHeader>
                  <TableBody>{ambiguities.map((item) => (
                    <TableRow key={`${item.fitid}-${item.origem_extrato}`}>
                      <TableCell className="max-w-72 break-all">{item.origem_extrato}<div>{item.banco} · {item.conta_sufixo}</div></TableCell>
                      <TableCell><code>{item.fitid}</code><div>{formatDate(item.data)}</div></TableCell>
                      <TableCell className="font-mono">{item.valor}</TableCell>
                      <TableCell>AMBIGUO · {item.classificacao}<div>{item.evidencia_conciliacao}</div>
                        <div className="max-w-72 break-all">Origens: {item.origens_extrato.join(", ")}</div></TableCell>
                    </TableRow>
                  ))}</TableBody>
                </Table>
              </div>
            </section>
            <p className="text-xs text-slate-400">
              FIN-02 não fornece score de confiança. Candidato ou ambiguidade não significa despesa
              confirmada, perda ou autorização de lançamento; esta prévia não oferece ações financeiras.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
