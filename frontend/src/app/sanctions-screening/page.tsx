import { AppShell } from "@/components/app-shell";
import { SanctionsScreeningWorkbench } from "@/components/sanctions-screening/sanctions-screening-workbench";
import "./sanctions-screening.css";

export default function SanctionsScreeningPage() {
  return (
    <AppShell activeSection="sanctions-screening" context="制裁筛查">
      <SanctionsScreeningWorkbench />
    </AppShell>
  );
}
