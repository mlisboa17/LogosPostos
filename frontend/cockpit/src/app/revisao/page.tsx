import { CockpitShell } from "@/components/cockpit-shell";
import { ClassificationReviewLive } from "@/components/classification-review-live";

export default function RevisaoClassificacaoPage() {
  return (
    <CockpitShell title="Fila de Revisão de Classificação">
      <ClassificationReviewLive />
    </CockpitShell>
  );
}
