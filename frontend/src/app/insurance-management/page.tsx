import { AppShell } from "@/components/app-shell";
import { InsuranceWorkbench } from "@/components/insurance/insurance-workbench";
import "./insurance-management.css";

export default function InsuranceManagementPage() {
  return (
    <AppShell activeSection="insurance-management" context="保单管理">
      <InsuranceWorkbench />
    </AppShell>
  );
}
