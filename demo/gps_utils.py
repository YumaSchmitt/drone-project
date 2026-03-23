"""
GPS utilities for mapping geographic coordinates to image/video pixel coordinates.

For a top-down orthographic view (like Google Earth or drone footage),
the mapping between GPS and pixels is approximately linear within a small area.
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class GPSBounds:
    """Geographic bounding box of a video frame or image."""
    lat_min: float   # bottom
    lat_max: float   # top
    lon_min: float   # left
    lon_max: float   # right

    @classmethod
    def from_center(cls, center_lat: float, center_lon: float,
                    width_meters: float, height_meters: float) -> "GPSBounds":
        """Create bounds from a center point and width/height in meters."""
        # Approximate: 1 degree latitude ≈ 111,320 meters
        # 1 degree longitude ≈ 111,320 * cos(lat) meters
        lat_delta = height_meters / 2 / 111320
        lon_delta = width_meters / 2 / (111320 * np.cos(np.radians(center_lat)))
        return cls(
            lat_min=center_lat - lat_delta,
            lat_max=center_lat + lat_delta,
            lon_min=center_lon - lon_delta,
            lon_max=center_lon + lon_delta,
        )

    def gps_to_pixel(self, lat: float, lon: float,
                     img_width: int, img_height: int) -> Tuple[int, int]:
        """Convert a GPS coordinate to pixel (x, y) in an image."""
        x = (lon - self.lon_min) / (self.lon_max - self.lon_min) * img_width
        # Latitude increases upward, but pixel Y increases downward
        y = (1 - (lat - self.lat_min) / (self.lat_max - self.lat_min)) * img_height
        return int(round(x)), int(round(y))

    def polygon_to_pixels(self, polygon: List[Tuple[float, float]],
                          img_width: int, img_height: int) -> np.ndarray:
        """Convert a list of (lat, lon) GPS coords to pixel coordinates."""
        pts = [self.gps_to_pixel(lat, lon, img_width, img_height)
               for lat, lon in polygon]
        return np.array(pts, dtype=np.int32)


def build_mask(polygon_px: np.ndarray, img_width: int, img_height: int) -> np.ndarray:
    """
    Build a binary mask (0/255) from a pixel polygon.
    Pixels inside the polygon are 255, outside are 0.
    """
    import cv2
    mask = np.zeros((img_height, img_width), dtype=np.uint8)
    cv2.fillPoly(mask, [polygon_px], 255)
    return mask


def crop_to_polygon(img: np.ndarray, mask: np.ndarray,
                    background: Tuple[int, int, int] = (0, 0, 0)) -> np.ndarray:
    """Apply a mask to an image, blacking out (or custom color) the area outside."""
    result = img.copy()
    bg = np.full_like(img, background, dtype=np.uint8)
    outside = mask == 0
    result[outside] = bg[outside]
    return result


def tight_crop(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Crop the image tightly to the bounding box of the masked region."""
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return img
    x0, x1 = xs.min(), xs.max()
    y0, y1 = ys.min(), ys.max()
    return img[y0:y1+1, x0:x1+1]
