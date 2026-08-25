/** Ordered polygon of the liver capsule in normalised image space (0..1). */
export const LIVER_POLYGON: Array<[number, number]> = [
  [0.33, 0.268],
  [0.47, 0.245],
  [0.61, 0.258],
  [0.7, 0.31],
  [0.762, 0.392],
  [0.822, 0.482],
  [0.8, 0.572],
  [0.73, 0.646],
  [0.622, 0.7],
  [0.496, 0.722],
  [0.376, 0.706],
  [0.282, 0.652],
  [0.22, 0.566],
  [0.202, 0.47],
  [0.245, 0.372],
  [0.292, 0.31],
]

/** Simple ray-casting point-in-polygon test. */
export function pointInPolygon(
  px: number,
  py: number,
  polygon: Array<[number, number]>,
): boolean {
  let inside = false
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i]
    const [xj, yj] = polygon[j]
    const intersects =
      yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi
    if (intersects) inside = !inside
  }
  return inside
}

/**
 * Rect of an `object-contain` image inside a container, in container pixels.
 * Returns a zero-size rect until both measurements are available.
 */
export function containRect(
  containerW: number,
  containerH: number,
  naturalW: number,
  naturalH: number,
): { left: number; top: number; width: number; height: number } {
  if (!containerW || !containerH || !naturalW || !naturalH) {
    return { left: 0, top: 0, width: 0, height: 0 }
  }
  const scale = Math.min(containerW / naturalW, containerH / naturalH)
  const width = naturalW * scale
  const height = naturalH * scale
  return {
    left: (containerW - width) / 2,
    top: (containerH - height) / 2,
    width,
    height,
  }
}
