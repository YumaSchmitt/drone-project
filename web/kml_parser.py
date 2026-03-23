"""
KML parser for Google My Maps and standard KML files.
Extracts polygon coordinates as (lat, lon) tuples.
"""

import xml.etree.ElementTree as ET
from typing import List, Dict, Tuple
import re

# KML can be namespaced or not
KML_NS = "http://www.opengis.net/kml/2.2"
KML_NS2 = "http://earth.google.com/kml/2.2"
KML_NS3 = "http://earth.google.com/kml/2.1"


def _find_ns(root: ET.Element) -> str:
    """Auto-detect the KML namespace from the root tag."""
    tag = root.tag
    m = re.match(r'\{(.+)\}', tag)
    return m.group(1) if m else ""


def _iter_tag(root: ET.Element, ns: str, tag: str):
    if ns:
        yield from root.iter(f"{{{ns}}}{tag}")
    else:
        yield from root.iter(tag)


def _find_tag(el: ET.Element, ns: str, path: str):
    if ns:
        parts = path.split("/")
        xpath = "/".join(f"{{{ns}}}{p}" for p in parts)
        return el.find(xpath)
    return el.find(path)


def _parse_coord_string(text: str) -> List[Tuple[float, float]]:
    """Parse KML coordinates text (lon,lat[,alt] ...) → list of (lat, lon)."""
    pts = []
    for token in text.strip().split():
        token = token.strip()
        if not token:
            continue
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                lon, lat = float(parts[0]), float(parts[1])
                pts.append((lat, lon))
            except ValueError:
                continue
    return pts


def parse_kml_string(kml_text: str) -> List[Dict]:
    """
    Parse a KML string and return a list of polygon dicts:
        [{"name": str, "coordinates": [(lat, lon), ...]}, ...]
    """
    try:
        root = ET.fromstring(kml_text)
    except ET.ParseError as e:
        raise ValueError(f"Invalid KML: {e}")

    ns = _find_ns(root)
    polygons = []

    for placemark in _iter_tag(root, ns, "Placemark"):
        name_el = _find_tag(placemark, ns, "name")
        name = (name_el.text or "Unnamed").strip() if name_el is not None else "Unnamed"

        # Standard Polygon
        for poly_el in _iter_tag(placemark, ns, "Polygon"):
            coords_el = _find_tag(poly_el, ns,
                                  "outerBoundaryIs/LinearRing/coordinates")
            if coords_el is None:
                # try without outer boundary
                coords_el = _find_tag(poly_el, ns, "coordinates")
            if coords_el is not None and coords_el.text:
                pts = _parse_coord_string(coords_el.text)
                if pts:
                    polygons.append({"name": name, "coordinates": pts})

        # MultiGeometry containing polygons
        for mg in _iter_tag(placemark, ns, "MultiGeometry"):
            for poly_el in _iter_tag(mg, ns, "Polygon"):
                coords_el = _find_tag(poly_el, ns,
                                      "outerBoundaryIs/LinearRing/coordinates")
                if coords_el is not None and coords_el.text:
                    pts = _parse_coord_string(coords_el.text)
                    if pts:
                        polygons.append({"name": name, "coordinates": pts})

    return polygons


def parse_kml_file(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return parse_kml_string(f.read())
