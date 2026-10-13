import { AppShell } from "@/components/app-shell";
import { MaritimeIntelligenceWorkspace } from "@/components/maritime-intelligence/maritime-intelligence-workspace";
import "./maritime-intelligence.css";

export default function MaritimeIntelligencePage() {
  return (
    <AppShell activeSection="maritime-intelligence" context="情报监测">
      <MaritimeIntelligenceWorkspace />
    </AppShell>
  );
}
