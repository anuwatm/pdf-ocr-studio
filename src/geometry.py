"""
Geometry and Coordinate Transformation Module for Local Thai OCR Web
Handles BoundingBox structures, rotation, deskewing transforms,
and accurate bidirectional coordinate mapping between processed images
and reference images.
"""

import math
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass


@dataclass
class Point:
    x: float
    y: float

    def to_list(self) -> List[float]:
        return [round(self.x, 2), round(self.y, 2)]


@dataclass
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    @property
    def area(self) -> float:
        return self.width * self.height

    def to_quad(self) -> List[float]:
        """Convert axis-aligned rect to 8-point quad [x1,y1, x2,y2, x3,y3, x4,y4]"""
        return [
            round(self.x0, 2), round(self.y0, 2),
            round(self.x1, 2), round(self.y0, 2),
            round(self.x1, 2), round(self.y1, 2),
            round(self.x0, 2), round(self.y1, 2),
        ]

    def intersects(self, other: "Rect") -> bool:
        return not (
            self.x1 <= other.x0
            or self.x0 >= other.x1
            or self.y1 <= other.y0
            or self.y0 >= other.y1
        )

    def intersection(self, other: "Rect") -> Optional["Rect"]:
        x0 = max(self.x0, other.x0)
        y0 = max(self.y0, other.y0)
        x1 = min(self.x1, other.x1)
        y1 = min(self.y1, other.y1)
        if x0 < x1 and y0 < y1:
            return Rect(x0, y0, x1, y1)
        return None

    def iou(self, other: "Rect") -> float:
        inter = self.intersection(other)
        if not inter:
            return 0.0
        inter_area = inter.area
        union_area = self.area + other.area - inter_area
        return inter_area / union_area if union_area > 0 else 0.0


def quad_to_rect(quad: List[float]) -> Rect:
    """Convert 8-point quad [x1,y1, x2,y2, x3,y3, x4,y4] to bounding Rect"""
    xs = [quad[i] for i in range(0, 8, 2)]
    ys = [quad[i + 1] for i in range(0, 8, 2)]
    return Rect(min(xs), min(ys), max(xs), max(ys))


class AffineTransform:
    """
    2D Affine Transform matrix:
    [ x' ]   [ a  b  c ] [ x ]
    [ y' ] = [ d  e  f ] [ y ]
    [ 1  ]   [ 0  0  1 ] [ 1 ]
    """

    def __init__(self, a: float = 1.0, b: float = 0.0, c: float = 0.0,
                 d: float = 0.0, e: float = 1.0, f: float = 0.0):
        self.a = float(a)
        self.b = float(b)
        self.c = float(c)
        self.d = float(d)
        self.e = float(e)
        self.f = float(f)

    @classmethod
    def identity(cls) -> "AffineTransform":
        return cls(1.0, 0.0, 0.0, 0.0, 1.0, 0.0)

    @classmethod
    def rotation(cls, angle_degrees: float, cx: float, cy: float,
                  new_cx: Optional[float] = None, new_cy: Optional[float] = None) -> "AffineTransform":
        """
        Rotation of angle_degrees around (cx, cy) and translated to (new_cx, new_cy).
        """
        rad = math.radians(angle_degrees)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        ncx = cx if new_cx is None else new_cx
        ncy = cy if new_cy is None else new_cy

        # x' = cos*(x - cx) - sin*(y - cy) + ncx = cos*x - sin*y + (-cx*cos + cy*sin + ncx)
        # y' = sin*(x - cx) + cos*(y - cy) + ncy = sin*x + cos*y + (-cx*sin - cy*cos + ncy)
        c = -cx * cos_a + cy * sin_a + ncx
        f = -cx * sin_a - cy * cos_a + ncy
        return cls(cos_a, -sin_a, c, sin_a, cos_a, f)

    def inverse(self) -> "AffineTransform":
        det = self.a * self.e - self.b * self.d
        if abs(det) < 1e-12:
            raise ValueError("Transform matrix is singular and cannot be inverted")
        inv_det = 1.0 / det
        inv_a = self.e * inv_det
        inv_b = -self.b * inv_det
        inv_c = (self.b * self.f - self.c * self.e) * inv_det
        inv_d = -self.d * inv_det
        inv_e = self.a * inv_det
        inv_f = (self.c * self.d - self.a * self.f) * inv_det
        return AffineTransform(inv_a, inv_b, inv_c, inv_d, inv_e, inv_f)

    def transform_point(self, x: float, y: float) -> Tuple[float, float]:
        tx = self.a * x + self.b * y + self.c
        ty = self.d * x + self.e * y + self.f
        return (tx, ty)

    def transform_quad(self, quad: List[float]) -> List[float]:
        """Transform 8-point quad [x1,y1, x2,y2, x3,y3, x4,y4]"""
        out = []
        for i in range(0, 8, 2):
            tx, ty = self.transform_point(quad[i], quad[i + 1])
            out.extend([round(tx, 2), round(ty, 2)])
        return out

    def to_dict(self) -> Dict[str, float]:
        return {
            "a": round(self.a, 6),
            "b": round(self.b, 6),
            "c": round(self.c, 6),
            "d": round(self.d, 6),
            "e": round(self.e, 6),
            "f": round(self.f, 6),
        }
