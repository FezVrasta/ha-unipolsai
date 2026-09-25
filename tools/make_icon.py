#!/usr/bin/env python3
"""Generate the brand icon.

    python tools/make_icon.py

Writes `icon.svg` and renders every PNG size from it. The SVG is build output — change
this script and re-run it, never edit the SVG by hand, or the next run silently reverts
your edit.

The glyph is a car with a signal fanning out above it: what the Unibox is, a black box
that reports the car's position. Drawn from primitives rather than one clever path, so
it stays editable, and with no SVG filters at all, which sidesteps both of librsvg's
usual traps (the `feComponentTransfer` seam and blur radii landing in the wrong
coordinate space).
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

# Pillow comes in with the test requirements; this script is developer tooling and is
# never imported by the integration.
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

#: The artboard. Home Assistant only serves the 256 and 512 renders, but the source is
#: drawn at 1024 so the geometry below is in round numbers.
SIZE = 1024

#: Apple's app-icon corner, as a fraction of the width, with Figma's equivalent
#: corner-smoothing value. These two numbers *are* the iOS icon shape; see squircle().
CORNER_RADIUS_RATIO = 0.2237
CORNER_SMOOTHING = 0.6

#: Deep navy tile so the glyph reads on a light or a dark theme without a `dark_`
#: variant, with Unipol's red on the signal for identity. Not their logo: a car and a
#: signal are generic, a wordmark would not be ours to ship.
TILE_TOP = "#1B2942"
TILE_BOTTOM = "#0E1726"
GLYPH = "#FFFFFF"
SIGNAL = "#E4002B"

#: Wheel centres and the car's vertical placement, before optical correction.
WHEELS = ((372, 648), (652, 648))
ARCH_R = 82
TYRE_R = 60
HUB_R = 24

#: The signal fans out from a point just above the roof.
SIGNAL_ORIGIN = (512, 384)
SIGNAL_RADII = (104, 182, 260)
SIGNAL_WIDTH = 34
SIGNAL_SPAN = (212, 328)

#: An app icon fills its mask. Drawn at a comfortable size then scaled about the
#: artboard centre, so the geometry above stays in readable numbers.
GLYPH_SCALE = 1.16


def squircle(size: float) -> str:
    """Return the iOS app-icon shape as an SVG path, inscribed in a `size` square.

    Not a superellipse. The obvious implementation — `|x|^n + |y|^n = 1` with n
    around 5 — is the shape most people mean by "squircle", but it is not the one
    Apple uses, and the difference is visible: a superellipse curves continuously
    everywhere, so the edges that should be flat bow outward. Side by side against
    a real app icon it reads as pillowed.

    Apple's mask is a *rounded rectangle with continuous curvature*, as produced by
    `UIBezierPath(roundedRect:cornerRadius:)`: genuinely straight edges, with the
    corner easing curvature in over a longer run than a circular arc would. This is
    the construction Figma exposes as "corner smoothing", at the iOS values.

    A circular corner is still wrong for the reason you would expect — curvature
    jumps from 0 to 1/r at the join — but the fix is smoothing the transition, not
    abandoning the straight edge.
    """
    radius = size * CORNER_RADIUS_RATIO
    budget = size / 2

    # Keep the corner inside the space available to it; without the cap a large
    # radius yields a self-intersecting path rather than a clipped one.
    smoothing = min(CORNER_SMOOTHING, budget / radius - 1)
    p = min((1 + smoothing) * radius, budget)

    arc_measure = math.radians(90 * (1 - smoothing))
    arc = math.sin(arc_measure / 2) * radius * math.sqrt(2)

    angle_alpha = (math.pi / 2 - arc_measure) / 2
    angle_beta = math.radians(45 * smoothing)
    c = radius * math.tan(angle_alpha / 2) * math.cos(angle_beta)
    d = c * math.tan(angle_beta)

    # The straight run into each corner splits 2:1 between the two off-curve
    # control points. That ratio is what ramps curvature smoothly.
    b = (p - arc - c - d) / 3
    a = 2 * b

    def f(value: float) -> str:
        return f"{value:.4f}"

    return " ".join(
        [
            f"M {f(size - p)} 0",
            f"c {f(a)} 0 {f(a + b)} 0 {f(a + b + c)} {f(d)}",
            f"a {f(radius)} {f(radius)} 0 0 1 {f(arc)} {f(arc)}",
            f"c {f(d)} {f(c)} {f(d)} {f(b + c)} {f(d)} {f(a + b + c)}",
            f"L {f(size)} {f(size - p)}",
            f"c 0 {f(a)} 0 {f(a + b)} {f(-d)} {f(a + b + c)}",
            f"a {f(radius)} {f(radius)} 0 0 1 {f(-arc)} {f(arc)}",
            f"c {f(-c)} {f(d)} {f(-(b + c))} {f(d)} {f(-(a + b + c))} {f(d)}",
            f"L {f(p)} {f(size)}",
            f"c {f(-a)} 0 {f(-(a + b))} 0 {f(-(a + b + c))} {f(-d)}",
            f"a {f(radius)} {f(radius)} 0 0 1 {f(-arc)} {f(-arc)}",
            f"c {f(-d)} {f(-c)} {f(-d)} {f(-(b + c))} {f(-d)} {f(-(a + b + c))}",
            f"L 0 {f(p)}",
            f"c 0 {f(-a)} 0 {f(-(a + b))} {f(d)} {f(-(a + b + c))}",
            f"a {f(radius)} {f(radius)} 0 0 1 {f(arc)} {f(-arc)}",
            f"c {f(c)} {f(-d)} {f(b + c)} {f(-d)} {f(a + b + c)} {f(-d)}",
            "Z",
        ]
    )


def arc(centre: tuple[float, float], radius: float, start: float, end: float) -> str:
    """Return an arc path. Angles are degrees, SVG convention: 270 is straight up."""
    cx, cy = centre
    x1 = cx + radius * math.cos(math.radians(start))
    y1 = cy + radius * math.sin(math.radians(start))
    x2 = cx + radius * math.cos(math.radians(end))
    y2 = cy + radius * math.sin(math.radians(end))
    large = 1 if abs(end - start) > 180 else 0
    return f"M{x1:.2f},{y1:.2f}A{radius},{radius} 0 {large} 1 {x2:.2f},{y2:.2f}"


def car_body() -> str:
    """Return the car's side profile: a bonnet, a cabin and a tail."""
    return (
        "M246,646"
        "L246,570"
        "C246,546 263,528 287,523"
        "L368,506"
        "L432,430"
        "C445,415 463,406 483,406"
        "L592,406"
        "C616,406 638,418 651,438"
        "L702,508"
        "L768,522"
        "C792,527 808,547 808,571"
        "L808,646"
        "Z"
    )


def build(dx: float = 0.0, dy: float = 0.0) -> str:
    """Return the SVG source, with the glyph nudged by `dx`/`dy`."""
    signal = "".join(
        f'      <path d="{arc(SIGNAL_ORIGIN, r, *SIGNAL_SPAN)}"/>\n'
        for r in SIGNAL_RADII
    )
    arches = "".join(
        f'      <circle cx="{x}" cy="{y}" r="{ARCH_R}"/>\n' for x, y in WHEELS
    )
    tyres = "".join(
        f'      <circle cx="{x}" cy="{y}" r="{TYRE_R}"/>\n' for x, y in WHEELS
    )
    hubs = "".join(
        f'      <circle cx="{x}" cy="{y}" r="{HUB_R}"/>\n' for x, y in WHEELS
    )
    return f"""\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" \
width="{SIZE}" height="{SIZE}">
  <title>UnipolSai Unibox</title>

  <!-- Generated by tools/make_icon.py. Do not edit; re-run the script. -->

  <defs>
    <linearGradient id="tile" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{TILE_TOP}"/>
      <stop offset="1" stop-color="{TILE_BOTTOM}"/>
    </linearGradient>
  </defs>

  <path d="{squircle(SIZE)}" fill="url(#tile)"/>

  <g transform="translate({dx:.2f},{dy:.2f}) translate({SIZE / 2:.1f},{SIZE / 2:.1f}) scale({GLYPH_SCALE}) translate({-SIZE / 2:.1f},{-SIZE / 2:.1f})">
    <g fill="none" stroke="{SIGNAL}" stroke-width="{SIGNAL_WIDTH / GLYPH_SCALE:.1f}" \
stroke-linecap="round">
{signal}    </g>

    <path d="{car_body()}" fill="{GLYPH}"/>

    <!-- Wheel arches punch the tile colour back out of the body, then the tyres and
         hubs sit in the holes. Cheaper to read than one path with arcs in it. -->
    <g fill="{TILE_BOTTOM}">
{arches}    </g>
    <g fill="{GLYPH}">
{tyres}    </g>
    <g fill="{TILE_BOTTOM}">
{hubs}    </g>
  </g>
</svg>
"""


def ink_centroid(png: Path) -> tuple[float, float, float, float]:
    """Return the ink centroid and extent centre of a rendered icon, in artboard units.

    "Ink" is everything that is not the tile: the glyph, weighted by alpha against a
    render of the tile alone would be exact, but comparing against the tile's own
    colours is enough here and needs no second render.
    """
    image = Image.open(png).convert("RGB")
    width, height = image.size
    pixels = image.load()

    # The tile is a vertical gradient, so a pixel is "ink" when it is far from both
    # ends of it. Generous threshold: the glyph is white and red, the tile is navy.
    def is_ink(rgb: tuple[int, int, int]) -> bool:
        r, g, b = rgb
        return r + g + b > 330 or (r > 120 and g < 90 and b < 90)

    total = 0
    sum_x = sum_y = 0
    min_x, max_x, min_y, max_y = width, 0, height, 0
    for y in range(height):
        for x in range(width):
            if is_ink(pixels[x, y]):
                total += 1
                sum_x += x
                sum_y += y
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)
    if not total:
        raise SystemExit("no glyph found in the render")

    scale = SIZE / width
    return (
        sum_x / total * scale,
        sum_y / total * scale,
        (min_x + max_x) / 2 * scale,
        (min_y + max_y) / 2 * scale,
    )


def main() -> None:
    """Write the SVG, correct its centring, and render the PNGs beside it."""
    (component,) = (ROOT / "custom_components").iterdir()
    source = component / "brand" / "icon.svg"
    source.parent.mkdir(parents=True, exist_ok=True)
    render = ROOT / "tools" / "render_brand.py"

    # First pass: draw it as designed, then measure where the ink actually sits.
    source.write_text(build())
    subprocess.run([sys.executable, str(render), str(source)], check=True)

    cx, cy, ex, ey = ink_centroid(source.with_name("icon.png"))
    centre = SIZE / 2
    # Correct most of the way toward the centroid, not all: a shape's extent counts
    # perceptually too, and correcting fully crowds the silhouette against an edge.
    # Then lift it slightly, because the perceived centre of a frame sits above the
    # geometric one.
    dx = 0.7 * (centre - cx) + 0.3 * (centre - ex)
    dy = 0.7 * (centre - cy) + 0.3 * (centre - ey) - SIZE * 0.012
    print(f"ink centroid ({cx:.1f},{cy:.1f}) extent ({ex:.1f},{ey:.1f})")
    print(f"correcting by ({dx:.1f},{dy:.1f})")

    # Second pass: the corrected artwork is what ships.
    source.write_text(build(dx, dy))
    print(f"{source}")
    subprocess.run([sys.executable, str(render), str(source)], check=True)


if __name__ == "__main__":
    main()
