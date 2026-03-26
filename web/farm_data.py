"""
Demo farm data for 農家A and 農家B.

Polygon data is loaded from the shared Google My Maps:
  https://www.google.com/maps/d/u/0/edit?mid=1EbZB0IZa5odksjfC1PAUYrDT2mKPNRg

If the map is unreachable (no network), placeholder polygons near
Ibaraki, Japan are used instead.
"""

import os
from kml_parser import parse_kml_string, parse_kmz_bytes

GOOGLE_MY_MAPS_MID = "1EbZB0IZa5odksjfC1PAUYrDT2mKPNRg"
GOOGLE_MY_MAPS_URL = f"https://www.google.com/maps/d/u/0/edit?mid={GOOGLE_MY_MAPS_MID}&usp=sharing"
_KML_EXPORT_URL    = f"https://www.google.com/maps/d/kml?mid={GOOGLE_MY_MAPS_MID}&forcekml=1"

# Placeholder polygons (Ibaraki, Japan area) — used when network is unavailable
_PLACEHOLDER_FARMS = {
    "farm_a": {
        "id": "farm_a",
        "name": "農家A",
        "owner": "田中太郎",
        "location": "茨城県つくば市",
        "total_area_ha": 12.4,
        "num_flights": 28,
        "weather": {"temp_c": 18, "condition": "晴れ", "humidity": 62, "wind_kmh": 12},
        "google_my_maps_url": GOOGLE_MY_MAPS_URL,
        "farmlands": [
            {
                "name": "水田1号",
                "area_ha": 5.2,
                "crop": "米",
                "polygon": [
                    (36.5030, 140.3300),
                    (36.5030, 140.3360),
                    (36.5005, 140.3360),
                    (36.5005, 140.3300),
                ],
                "center": (36.5018, 140.3330),
            },
            {
                "name": "畑2号",
                "area_ha": 7.2,
                "crop": "大豆",
                "polygon": [
                    (36.4980, 140.3310),
                    (36.4980, 140.3380),
                    (36.4955, 140.3380),
                    (36.4955, 140.3310),
                ],
                "center": (36.4968, 140.3345),
            },
        ],
    },
    "farm_b": {
        "id": "farm_b",
        "name": "農家B",
        "owner": "佐藤花子",
        "location": "茨城県土浦市",
        "total_area_ha": 8.7,
        "num_flights": 15,
        "weather": {"temp_c": 17, "condition": "曇り", "humidity": 70, "wind_kmh": 8},
        "google_my_maps_url": GOOGLE_MY_MAPS_URL,
        "farmlands": [
            {
                "name": "畑A-1",
                "area_ha": 3.5,
                "crop": "キャベツ",
                "polygon": [
                    (36.4900, 140.3200),
                    (36.4900, 140.3250),
                    (36.4880, 140.3250),
                    (36.4880, 140.3200),
                ],
                "center": (36.4890, 140.3225),
            },
            {
                "name": "畑A-2",
                "area_ha": 5.2,
                "crop": "にんじん",
                "polygon": [
                    (36.4870, 140.3220),
                    (36.4870, 140.3290),
                    (36.4845, 140.3290),
                    (36.4845, 140.3220),
                ],
                "center": (36.4858, 140.3255),
            },
        ],
    },
}


def _poly_to_farmland(poly):
    coords = poly["coordinates"]
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    center = (sum(lats) / len(lats), sum(lons) / len(lons))
    # Rough area estimate in hectares
    area_ha = round(
        abs((max(lats) - min(lats)) * (max(lons) - min(lons)) * 111_000 * 91_000) / 10_000, 1
    )
    return {
        "name": poly["name"],
        "area_ha": area_ha,
        "crop": "---",
        "polygon": coords,
        "center": center,
    }


def _assign_polygons(polygons):
    """Split parsed polygons into farm_a / farm_b by name."""
    farm_a_polys, farm_b_polys, unassigned = [], [], []
    for poly in polygons:
        name = poly["name"]
        if "農家A" in name:
            farm_a_polys.append(poly)
        elif "農家B" in name:
            farm_b_polys.append(poly)
        else:
            unassigned.append(poly)

    # If names don't contain 農家A/B, split unassigned evenly
    if not farm_a_polys and not farm_b_polys and unassigned:
        mid = max(len(unassigned) // 2, 1)
        farm_a_polys = unassigned[:mid]
        farm_b_polys = unassigned[mid:]

    result = {}
    for farm_id, polys in [("farm_a", farm_a_polys), ("farm_b", farm_b_polys)]:
        if not polys:
            continue
        farmlands = [_poly_to_farmland(p) for p in polys]
        farm = dict(_PLACEHOLDER_FARMS[farm_id])
        farm["farmlands"] = farmlands
        farm["total_area_ha"] = round(sum(f["area_ha"] for f in farmlands), 1)
        result[farm_id] = farm
    return result or None


def _try_fetch_google_my_maps():
    """Fetch polygon data directly from the Google My Maps KML export."""
    import requests
    try:
        resp = requests.get(_KML_EXPORT_URL, timeout=10,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        content = resp.content
        # Response may be KMZ (zip) or plain KML
        if content[:2] == b'PK':
            polygons = parse_kmz_bytes(content)
        else:
            polygons = parse_kml_string(resp.text)
        if polygons:
            print(f"[farm_data] Loaded {len(polygons)} polygon(s) from Google My Maps")
            return _assign_polygons(polygons)
    except Exception as e:
        print(f"[farm_data] Google My Maps fetch failed (will use placeholders): {e}")
    return None


def _try_load_kmz():
    """Fallback: try loading testmap.kmz which contains a NetworkLink to the same map."""
    from kml_parser import parse_kmz_file
    kmz_path = os.path.join(os.path.dirname(__file__), "..", "testmap.kmz")
    if not os.path.exists(kmz_path):
        return None
    try:
        polygons = parse_kmz_file(kmz_path)
        if polygons:
            return _assign_polygons(polygons)
    except Exception as e:
        print(f"[farm_data] KMZ parse error: {e}")
    return None


def get_farms():
    """Return farm data. Tries Google My Maps → KMZ → placeholder."""
    data = _try_fetch_google_my_maps() or _try_load_kmz()
    if data:
        farms = dict(_PLACEHOLDER_FARMS)
        farms.update(data)
        return farms
    return dict(_PLACEHOLDER_FARMS)


def get_farm(farm_id):
    return get_farms().get(farm_id)
