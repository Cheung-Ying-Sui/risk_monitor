import type {
  InsuranceActivity,
  InsuranceApplication,
  InsurancePolicy,
  InsuranceTask,
  InsuredCargo,
  InsuredVessel,
} from "@/types/insurance";

export const insuranceApplications: InsuranceApplication[] = [
  { id: "APP-260815-01", status: "draft", client: "Sinochem Agro", insuranceType: "Marine Cargo", subject: "Fertilizer · 8,500 MT", vessel: "COSCO SHIPPING LOTUS", voyage: "Shanghai → Santos", sumInsured: 4_800_000, currency: "USD", createdAt: "2026-08-15", owner: "Simon", risk: "normal" },
  { id: "APP-260814-07", status: "pending", client: "Syngenta China", insuranceType: "Marine Cargo", subject: "Seeds · 1,240 MT", vessel: "EVER GIVEN", voyage: "Qingdao → Rotterdam", sumInsured: 7_200_000, currency: "USD", createdAt: "2026-08-14", owner: "Simon", risk: "elevated" },
  { id: "APP-260812-03", status: "quoted", client: "Sinochem Holdings", insuranceType: "Vessel", subject: "SINOCHEM VOYAGER", vessel: "SINOCHEM VOYAGER", sumInsured: 32_000_000, currency: "USD", createdAt: "2026-08-12", owner: "A. Zhang", risk: "normal" },
  { id: "APP-260811-05", status: "submitted", client: "China Jinmao", insuranceType: "Marine Cargo", subject: "Steel Coil · 12,600 MT", vessel: "PACIFIC HORIZON", voyage: "Ningbo → Jebel Ali", sumInsured: 9_650_000, currency: "USD", createdAt: "2026-08-11", owner: "M. Liu", risk: "elevated" },
  { id: "APP-260809-02", status: "bound", client: "Sinochem Energy", insuranceType: "Marine Cargo", subject: "Base Oil · 18,200 MT", vessel: "OCEAN CREST", voyage: "Singapore → Tianjin", sumInsured: 13_400_000, currency: "USD", createdAt: "2026-08-09", owner: "Simon", risk: "normal" },
  { id: "APP-260807-04", status: "pending", client: "Sinochem Plastics", insuranceType: "Marine Cargo", subject: "Polyethylene · 6,700 MT", vessel: "MAERSK HAMBURG", voyage: "Busan → Hamburg", sumInsured: 5_100_000, currency: "USD", createdAt: "2026-08-07", owner: "J. Chen", risk: "high" },
];

export const insurancePolicies: InsurancePolicy[] = [
  { id: "POL-01", policyNumber: "MC-2026-00128", client: "Sinochem Agro", insuranceType: "Marine Cargo", subject: "Fertilizer Programme", sumInsured: 12_400_000, currency: "USD", insurer: "PICC", inception: "2026-08-01", expiry: "2027-07-31", status: "active" },
  { id: "POL-02", policyNumber: "HV-2026-00042", client: "Sinochem Shipping", insuranceType: "Vessel", subject: "SINOCHEM VOYAGER", sumInsured: 32_000_000, currency: "USD", insurer: "China Re", inception: "2026-06-15", expiry: "2027-06-14", status: "active" },
  { id: "POL-03", policyNumber: "MC-2026-00121", client: "Sinochem Energy", insuranceType: "Marine Cargo", subject: "Energy Cargo Programme", sumInsured: 28_600_000, currency: "USD", insurer: "CPIC", inception: "2025-08-22", expiry: "2026-08-21", status: "expiring" },
  { id: "POL-04", policyNumber: "MC-2026-00109", client: "Syngenta China", insuranceType: "Marine Cargo", subject: "Seeds & Crop Inputs", sumInsured: 18_900_000, currency: "USD", insurer: "Ping An", inception: "2026-03-01", expiry: "2027-02-28", status: "active" },
];

export const insuredCargo: InsuredCargo[] = [
  { id: "CGO-01", cargo: "Fertilizer Lot 26-0815", commodity: "Urea", quantity: "8,500 MT", vessel: "COSCO SHIPPING LOTUS", origin: "Shanghai", destination: "Santos", sumInsured: 4_800_000, currency: "USD", policyNumber: "MC-2026-00128", status: "pending" },
  { id: "CGO-02", cargo: "Energy Parcel SG-44", commodity: "Base Oil", quantity: "18,200 MT", vessel: "OCEAN CREST", origin: "Singapore", destination: "Tianjin", sumInsured: 13_400_000, currency: "USD", policyNumber: "MC-2026-00121", status: "active" },
  { id: "CGO-03", cargo: "Seeds Shipment QD-18", commodity: "Hybrid Seeds", quantity: "1,240 MT", vessel: "EVER GIVEN", origin: "Qingdao", destination: "Rotterdam", sumInsured: 7_200_000, currency: "USD", policyNumber: "MC-2026-00109", status: "active" },
  { id: "CGO-04", cargo: "Steel Coil NB-72", commodity: "Steel Coil", quantity: "12,600 MT", vessel: "PACIFIC HORIZON", origin: "Ningbo", destination: "Jebel Ali", sumInsured: 9_650_000, currency: "USD", policyNumber: "Pending", status: "pending" },
];

export const insuredVessels: InsuredVessel[] = [
  { id: "VSL-01", vessel: "SINOCHEM VOYAGER", imo: "9876543", mmsi: "413678900", vesselType: "Container Ship", policyNumber: "HV-2026-00042", sumInsured: 32_000_000, currency: "USD", currentVoyage: "Shanghai → Yokohama", risk: "normal", status: "active" },
  { id: "VSL-02", vessel: "OCEAN CREST", imo: "9765128", mmsi: "477234100", vesselType: "Oil Products Tanker", policyNumber: "HV-2026-00038", sumInsured: 41_500_000, currency: "USD", currentVoyage: "Singapore → Tianjin", risk: "elevated", status: "active" },
  { id: "VSL-03", vessel: "PACIFIC HORIZON", imo: "9687342", mmsi: "538009871", vesselType: "Bulk Carrier", policyNumber: "HV-2026-00031", sumInsured: 26_800_000, currency: "USD", currentVoyage: "Ningbo → Jebel Ali", risk: "high", status: "expiring" },
];

export const insuranceTasks: InsuranceTask[] = [
  { id: "TASK-01", type: "quote_expiring", subject: "先正达货运险", due: "2 小时", urgency: "critical" },
  { id: "TASK-02", type: "document_required", subject: "中化农业", due: "4 小时", urgency: "warning" },
  { id: "TASK-03", type: "review_required", subject: "PACIFIC HORIZON 轮", due: "明天", urgency: "warning" },
  { id: "TASK-04", type: "policy_expiring", subject: "海运货物险 MC-2026-00121", due: "5 天", urgency: "normal" },
];

export const insuranceActivities: InsuranceActivity[] = [
  { id: "ACT-01", time: "14:32", description: "Application APP-260814-07 submitted for review", actor: "Simon" },
  { id: "ACT-02", time: "13:48", description: "Policy MC-2026-00128 created", actor: "A. Zhang" },
  { id: "ACT-03", time: "11:24", description: "Cargo information updated for CGO-01", actor: "M. Liu" },
];

export const portfolioExposure = [
  { label: "货物", value: 58, amount: "USD 108.1M" },
  { label: "船舶", value: 31, amount: "USD 57.8M" },
  { label: "其他", value: 11, amount: "USD 20.5M" },
];

export const applicationPipeline = [
  { label: "草稿", value: 4, tone: "neutral" },
  { label: "待处理", value: 7, tone: "warning" },
  { label: "已提交", value: 5, tone: "info" },
  { label: "已报价", value: 3, tone: "quoted" },
  { label: "已承保", value: 18, tone: "positive" },
] as const;
