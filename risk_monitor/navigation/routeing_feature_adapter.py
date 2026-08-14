from __future__ import annotations


ROUTE_PRIOR_LINE_TYPES = {
    "recommended_track",
    "deep_water_route",
    "route_density_corridor",
}


def adapt_routeing_features_for_prior(features):
    adapted = []
    for feature in features or []:
        geometry = feature.get("geometry") or {}
        properties = feature.get("properties") or feature
        routeing_type = (
            properties.get("routeing_type")
            or properties.get("type")
            or "other"
        )
        geometry_kind = properties.get("geometry_kind")
        if geometry.get("type") != "LineString":
            continue
        if geometry_kind and geometry_kind != "line":
            continue
        if routeing_type not in ROUTE_PRIOR_LINE_TYPES:
            continue

        adapted.append(
            {
                "id": properties.get("feature_id") or feature.get("id"),
                "name": properties.get("name"),
                "type": routeing_type,
                "geometry": geometry,
                "source": properties.get("source_id") or feature.get("source"),
                "source_version": properties.get("source_version"),
                "official": bool(properties.get("official")),
                "source_type": properties.get("source_type"),
                "bbox": properties.get("bbox") or feature.get("bbox"),
            }
        )
    return adapted
