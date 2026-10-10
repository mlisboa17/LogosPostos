import assert from "node:assert/strict";
import { test } from "node:test";

globalThis.window = { location: { origin: "http://localhost" } };
const { carregarPainelDiretor, renderPainelDiretor } = await import("../../frontend/pages/directorDashboard.js");
const { apiClient } = await import("../../frontend/services/apiClient.js");

const dados = {
  saude_robo: {
    ultima_execucao: "2026-10-09T11:00:00-03:00",
    dia_processado: "2026-10-08",
    unidades_processadas: [5555, 74014],
    unidades_com_falha: [74014],
    resumo_gerado: true,
    alerta_atraso: true,
    execucao_sem_unidades: false,
    alerta_operacional: true,
    limite_horas: 26,
  },
  unidades: [{
    empresa_codigo: 5555,
    nome: "Unidade <script>ruim</script>",
    fechamento: {
      dia: "2026-10-08",
      quebra_total: "-15.20",
      faltas_sem_desconto: 1,
      faltas_sem_desconto_total: "15.20",
      caixas_parados: 1,
      caixas_parados_dias: 3,
    },
    recebimentos_a_maior_total: "20.00",
    recebimentos_a_menor_total: "5.50",
    pendencias_abertas: 4,
    adquirentes: [
      { nome: "PAGBANK", situacao: "ativo" },
      { nome: "PREMMIA", situacao: "pendente" },
    ],
  }, {
    empresa_codigo: 74014,
    nome: "Unidade sem dados",
    fechamento: null,
    recebimentos_a_maior_total: null,
    recebimentos_a_menor_total: null,
    pendencias_abertas: null,
    adquirentes: [{ nome: "PAGBANK", situacao: "credencial inválida" }],
  }],
  placar: {
    mes: "2026-10",
    total_postos: 3,
    postos_com_snapshot: 2,
    postos_com_projecao: 2,
    postos_com_nivel: 2,
    contagens: { bronze: 1, prata: 0, ouro: 1 },
    percentuais: { bronze: 50, prata: 0, ouro: 50 },
    postos: [{
      empresa_codigo: 5555,
      nome: "AP Casa Caiada",
      com_snapshot: true,
      dia_snapshot: "2026-10-08",
      projecao: "12345.67",
      nivel_projetado: "ouro",
    }, {
      empresa_codigo: 74014,
      nome: "Posto sem snapshot",
      com_snapshot: false,
      dia_snapshot: null,
      projecao: null,
      nivel_projetado: null,
    }],
  },
};

test("painel mostra projeção, status do robô, pendências filtradas e escapa conteúdo", () => {
  const html = renderPainelDiretor(dados, "diretor");
  assert.match(html, /Painel do Diretor/);
  assert.match(html, /Atenção: execução atrasada/);
  assert.match(html, /Atualizar agora/);
  assert.match(html, /50%/);
  assert.match(html, /Ouro · 12\.345,67 L/);
  assert.match(html, /08\/10\/2026/);
  assert.match(html, /view=pendencias&amp;unidade=5555/);
  assert.match(html, /credencial inválida/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /Sem dados/);
  assert.match(html, /Pendências indisponíveis/);
});

test("gerente não recebe ação de atualização manual do diretor", () => {
  assert.doesNotMatch(renderPainelDiretor(dados, "gerente"), /Atualizar agora/);
});

test("execução recente sem unidade processada aparece em alerta operacional", () => {
  const html = renderPainelDiretor({
    ...dados,
    saude_robo: {
      ...dados.saude_robo,
      alerta_atraso: false,
      execucao_sem_unidades: true,
      alerta_operacional: true,
      unidades_processadas: [],
    },
  }, "diretor");
  assert.match(html, /Atenção: nenhuma unidade processada/);
});

test("saúde renderiza estados ok, atenção laranja e falha vermelha", () => {
  const base = {
    ...dados,
    saude_robo: {
      ...dados.saude_robo,
      alerta_atraso: false,
      execucao_sem_unidades: false,
      unidades_com_falha: [],
      alerta_operacional: false,
    },
  };
  const ok = renderPainelDiretor({
    ...base,
    saude_robo: { ...base.saude_robo, estado: "ok" },
  });
  assert.match(ok, /dd-health--ok/);
  assert.match(ok, /Execução dentro do prazo/);

  const atencao = renderPainelDiretor({
    ...base,
    saude_robo: {
      ...base.saude_robo,
      estado: "atencao",
      alerta_operacional: true,
      unidades_com_aviso: [74014],
      avisos: [{
        unidade_nome: "Conveniencia 24h",
        unidade_codigo: 74014,
        adquirente: "PAGBANK",
        mensagem: "credencial inválida",
      }],
    },
  });
  assert.match(atencao, /dd-health--warning/);
  assert.match(atencao, /border-left-color:#f59e0b/);
  assert.match(atencao, /Conveniencia 24h \(74014\) · PAGBANK: credencial inválida/);

  const falha = renderPainelDiretor({
    ...base,
    saude_robo: {
      ...base.saude_robo,
      estado: "falha",
      alerta_operacional: true,
      unidades_com_falha: [74014],
    },
  });
  assert.match(falha, /dd-health--alert/);
  assert.match(falha, /Atenção: execução com falhas/);
});

test("painel carrega apenas os endpoints de leitura do resumo persistido", async (t) => {
  const chamadas = [];
  t.mock.method(apiClient, "get", async (url) => {
    chamadas.push(url);
    return url.includes("painel-resumo") ? dados.placar : {
      saude_robo: dados.saude_robo,
      unidades: dados.unidades,
    };
  });
  const alvo = { innerHTML: "", querySelector: () => null };
  await carregarPainelDiretor(alvo, { papel: "gerente" });
  assert.deepEqual(chamadas, [
    "/api/v1/cash-audit/painel-diretor",
    "/api/v1/commercial/painel-resumo",
  ]);
  assert.match(alvo.innerHTML, /Painel do Diretor/);
  assert.doesNotMatch(alvo.innerHTML, /Atualizar agora/);
});
