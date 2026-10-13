const configuredBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();

export function getRiskZonesGeoJsonUrl() {
  const baseUrl = configuredBaseUrl || "http://localhost:8000";
  return `${baseUrl.replace(/\/$/, "")}/api/v1/risk-zones`;
}
