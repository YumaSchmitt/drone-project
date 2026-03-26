"""
KML / KMZ parser for Google My Maps and standard KML files.
Extracts polygon coordinates as (lat, lon) tuples.
"""

import xml.etree.ElementTree as ET
import zipfile
import io
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


def parse_kmz_file(path: str) -> List[Dict]:
    """Parse a KMZ file (ZIP containing one or more KML files)."""
    with open(path, "rb") as f:
        return parse_kmz_bytes(f.read())


def parse_kmz_bytes(data: bytes) -> List[Dict]:
    """Parse KMZ bytes (ZIP containing KML files).
    Handles NetworkLink references by fetching the linked KML."""
    polygons = []
    network_links = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if name.lower().endswith(".kml"):
                kml_text = zf.read(name).decode("utf-8", errors="replace")
                found = parse_kml_string(kml_text)
                if found:
                    polygons.extend(found)
                else:
                    # Check for NetworkLink elements
                    network_links.extend(_extract_network_links(kml_text))

    # Fetch NetworkLink URLs if no inline polygons found
    if not polygons and network_links:
        import requests
        for url in network_links:
            # Ensure forcekml=1 for Google My Maps
            if "google.com/maps/d" in url and "forcekml=1" not in url:
                sep = "&" if "?" in url else "?"
                url = url + sep + "forcekml=1"
            try:
                resp = requests.get(url, timeout=15,
                                    headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                content = resp.content
                # Check if response is KMZ (zip)
                if content[:2] == b'PK':
                    polygons.extend(parse_kmz_bytes(content))
                else:
                    polygons.extend(parse_kml_string(resp.text))
            except Exception:
                continue
    return polygons


def _extract_network_links(kml_text: str) -> List[str]:
    """Extract href URLs from NetworkLink elements in KML."""
    try:
        root = ET.fromstring(kml_text)
    except ET.ParseError:
        return []
    ns = _find_ns(root)
    urls = []
    for nl in _iter_tag(root, ns, "NetworkLink"):
        link_el = _find_tag(nl, ns, "Link")
        if link_el is not None:
            href_el = _find_tag(link_el, ns, "href")
            if href_el is not None and href_el.text:
                urls.append(href_el.text.strip())
    return urls
