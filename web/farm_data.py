"""
Demo farm data for 農家A and 農家B.

When testmap.kmz is available, polygons are loaded from it.
Otherwise, placeholder polygons near Ibaraki, Japan are used.
"""

import os
from kml_parser import parse_kmz_file

# Placeholder polygons (Ibaraki, Japan area)
_PLACEHOLDER_FARMS = {
    "farm_a": {
        "id": "farm_a",
        "name": "農家A",
        "owner": "田中太郎",
        "location": "茨城県つくば市",
        "total_area_ha": 12.4,
        "num_flights": 28,
        "weather": {"temp_c": 18, "condition": "晴れ", "humidity": 62, "wind_kmh": 12},
        "google_my_maps_url": "https://www.google.com/maps/d/edit",
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
        "google_my_maps_url": "https://www.google.com/maps/d/edit",
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


def _try_load_kmz():
    """Try loading testmap.kmz and map polygons to farm_a / farm_b."""
    kmz_path = os.path.join(os.path.dirname(__file__), "..", "testmap.kmz")
    if not os.path.exists(kmz_path):
        return None

    try:
        polygons = parse_kmz_file(kmz_path)
    except Exception as e:
        print(f"[farm_data] KMZ parse error (will use placeholders): {e}")
        return None

    if not polygons:
        print("[farm_data] No polygons in KMZ (network may be needed). Using placeholders.")
        return None

    # Try to assign polygons to farms based on name containing 農家A / 農家B
    farm_a_polys = []
    farm_b_polys = []
    for poly in polygons:
        name = poly["name"]
        if "農家A" in name or "A" in name.upper().split("農家")[-1][:2]:
            farm_a_polys.append(poly)
        elif "農家B" in name or "B" in name.upper().split("農家")[-1][:2]:
            farm_b_polys.append(poly)

    # If no clear mapping, split evenly
    if not farm_a_polys and not farm_b_polys:
        mid = len(polygons) // 2
        farm_a_polys = polygons[:max(mid, 1)]
        farm_b_polys = polygons[max(mid, 1):]

    def _poly_to_farmland(poly, idx):
        coords = poly["coordinates"]
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        center = (sum(lats) / len(lats), sum(lons) / len(lons))
        return {
            "name": poly["name"],
            "area_ha": round(abs((max(lats) - min(lats)) * (max(lons) - min(lons)) * 111000 * 91000) / 10000, 1),
            "crop": "---",
            "polygon": coords,
            "center": center,
        }

    result = {}
    if farm_a_polys:
        farmlands = [_poly_to_farmland(p, i) for i, p in enumerate(farm_a_polys)]
        result["farm_a"] = dict(_PLACEHOLDER_FARMS["farm_a"])
        result["farm_a"]["farmlands"] = farmlands
        result["farm_a"]["total_area_ha"] = round(sum(f["area_ha"] for f in farmlands), 1)

    if farm_b_polys:
        farmlands = [_poly_to_farmland(p, i) for i, p in enumerate(farm_b_polys)]
        result["farm_b"] = dict(_PLACEHOLDER_FARMS["farm_b"])
        result["farm_b"]["farmlands"] = farmlands
        result["farm_b"]["total_area_ha"] = round(sum(f["area_ha"] for f in farmlands), 1)

    return result if result else None


def get_farms():
    """Return farm data dict. Uses KMZ data if available, else placeholders."""
    kmz_data = _try_load_kmz()
    if kmz_data:
        # Merge with placeholders for any missing farm
        farms = dict(_PLACEHOLDER_FARMS)
        farms.update(kmz_data)
        return farms
    return dict(_PLACEHOLDER_FARMS)


def get_farm(farm_id):
    """Return a single farm by ID, or None."""
    return get_farms().get(farm_id)
