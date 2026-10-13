export type UKMTOIncidentType = "attack" | "suspicious_activity" | "hijack" | "advisory" | "military_interaction" | "unknown";

export type MaritimeEventCategory = UKMTOIncidentType
  | "security"
  | "piracy"
  | "war_conflict"
  | "port_disruption"
  | "chokepoint"
  | "weather"
  | "marine_casualty";

export type MaritimeEventSeverity = "low" | "medium" | "high" | "critical" | "unknown";

export interface IntelligenceSource {
  id: string;
  name: string;
  url?: string;
}

export interface MaritimeIntelligenceEvent {
  id: string;
  title: string;
  category: MaritimeEventCategory;
  severity: MaritimeEventSeverity;
  occurredAt: string | null;
  publishedAt?: string | null;
  lastSeenAt?: string | null;
  sourceUpdatedAt?: string | null;
  locationPrecision?: string;
  region?: string | null;
  vesselType?: string | null;
  latitude: number | null;
  longitude: number | null;
  locationName: string;
  summary: string;
  potentialImpact?: string[];
  sources: IntelligenceSource[];
  relatedVesselCount?: number;
  relatedVoyageCount?: number;
}
