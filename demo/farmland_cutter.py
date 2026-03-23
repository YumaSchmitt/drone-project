"""
FarmlandCutter — cuts video and images to a GPS-defined farmland boundary.

Usage:
    cutter = FarmlandCutter(gps_bounds, farmland_polygon)
    cutter.cut_image("input.jpg", "output.jpg")
    cutter.cut_video("input.mp4", "output.mp4")

The farmland_polygon is a list of (lat, lon) tuples defining the boundary.
The gps_bounds defines what GPS area the full video/image frame covers.
"""

import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional

from gps_utils import GPSBounds, build_mask, crop_to_polygon, tight_crop


class FarmlandCutter:
    def __init__(
        self,
        gps_bounds: GPSBounds,
        farmland_polygon: List[Tuple[float, float]],
        tight: bool = False,
        background_color: Tuple[int, int, int] = (0, 0, 0),
    ):
        """
        Args:
            gps_bounds: The GPS bounding box of the full video/image frame.
            farmland_polygon: List of (lat, lon) tuples defining the farm boundary.
            tight: If True, also crop the output to the bounding box of the polygon.
            background_color: RGB color for areas outside the polygon.
        """
        self.bounds = gps_bounds
        self.polygon = farmland_polygon
        self.tight = tight
        self.background_color = background_color

    def _get_mask(self, width: int, height: int) -> np.ndarray:
        polygon_px = self.bounds.polygon_to_pixels(self.polygon, width, height)
        return build_mask(polygon_px, width, height)

    def cut_image(self, input_path: str, output_path: str) -> None:
        img = cv2.imread(input_path)
        if img is None:
            raise FileNotFoundError(f"Cannot read image: {input_path}")
        h, w = img.shape[:2]
        mask = self._get_mask(w, h)
        result = crop_to_polygon(img, mask, self.background_color)
        if self.tight:
            result = tight_crop(result, mask)
        cv2.imwrite(output_path, result)
        print(f"Image saved: {output_path}")

    def cut_video(
        self,
        input_path: str,
        output_path: str,
        progress: bool = True,
    ) -> None:
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {input_path}")

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        mask = self._get_mask(w, h)

        # Determine output dimensions
        if self.tight:
            ys, xs = np.where(mask > 0)
            x0, x1 = int(xs.min()), int(xs.max())
            y0, y1 = int(ys.min()), int(ys.max())
            out_w, out_h = x1 - x0 + 1, y1 - y0 + 1
        else:
            x0, y0 = 0, 0
            out_w, out_h = w, h

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(output_path, fourcc, fps, (out_w, out_h))

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            result = crop_to_polygon(frame, mask, self.background_color)
            if self.tight:
                result = result[y0:y1+1, x0:x1+1]
            out.write(result)
            frame_idx += 1
            if progress and frame_idx % 30 == 0:
                pct = frame_idx / total * 100 if total > 0 else 0
                print(f"  Processing frame {frame_idx}/{total} ({pct:.0f}%)")

        cap.release()
        out.release()
        print(f"Video saved: {output_path}  ({frame_idx} frames)")

    def preview_polygon(self, width: int = 800, height: int = 600) -> np.ndarray:
        """Return an image showing the polygon overlay for inspection."""
        canvas = np.zeros((height, width, 3), dtype=np.uint8)
        mask = self._get_mask(width, height)
        canvas[mask == 255] = (34, 139, 34)   # farmland = green
        polygon_px = self.bounds.polygon_to_pixels(self.polygon, width, height)
        cv2.polylines(canvas, [polygon_px], isClosed=True,
                      color=(0, 255, 255), thickness=3)
        for pt in polygon_px:
            cv2.circle(canvas, tuple(pt), 6, (0, 200, 255), -1)
        return canvas
