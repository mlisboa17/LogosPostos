import { CockpitShell } from "@/components/cockpit-shell";
import { CashAuditLive } from "@/components/cash-audit-live";

export default function AuditoriaPage() {
  return (
    <CockpitShell title="Auditoria de Caixa">
      <CashAuditLive />
    </CockpitShell>
  );
}
