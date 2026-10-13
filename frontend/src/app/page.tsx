import { AppShell } from "@/components/app-shell";
import MaritimeMap from "./maritime-map";

export default function Home() {
  return (
    <AppShell activeSection="vessel-tracking" context="船队概览">
      <MaritimeMap />
    </AppShell>
  );
}
