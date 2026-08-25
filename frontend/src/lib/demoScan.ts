import { LIVER_POLYGON } from './geometry'

/**
 * Procedural B-mode ultrasound generator.
 *
 * The demo build ships without DICOM data, so the "sample study" is synthesised
 * here: a curvilinear sector with speckle, an echogenic (fatty) parenchyma,
 * portal triads, a diaphragm and an anechoic cyst — positioned to line up with
 * the mock inference geometry in `mockEngine.ts`.
 *
 * Tissue boundaries are built from smooth masks rather than hard thresholds so
 * nothing reads as a drawn shape once speckle is applied.
 */

const W = 960
const H = 720
/** Width/height ratio — used to work in isotropic units. */
const ASPECT = W / H

/** Sector geometry, in canvas pixels. */
const APEX_X = W / 2
const APEX_Y = -40
const HALF_ANGLE = (40 * Math.PI) / 180
const R_NEAR = 96
const R_FAR = 762

/** Anechoic cyst — matches the primary YOLOv8 detection. */
export const CYST = { cx: 0.615, cy: 0.47, r: 0.052 }
/** Low-confidence hyperechoic nodule — sits below the default threshold. */
export const NODULE = { cx: 0.375, cy: 0.56, r: 0.038 }

/* ------------------------------------------------------------------ maths */

function clamp01(x: number): number {
  return x < 0 ? 0 : x > 1 ? 1 : x
}

/** Hermite ramp; also handles edge0 > edge1 for an inverted ramp. */
function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = clamp01((x - edge0) / (edge1 - edge0))
  return t * t * (3 - 2 * t)
}

function mix(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

/** Deterministic PRNG so the sample study is byte-identical every session. */
function mulberry32(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Cheap hash-based value noise on an integer lattice. */
function hashNoise(x: number, y: number, seed: number): number {
  let h = Math.imul(x, 374761393) + Math.imul(y, 668265263) + Math.imul(seed, 2246822519)
  h = Math.imul(h ^ (h >>> 13), 1274126177)
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296
}

function distanceToSegment(
  px: number,
  py: number,
  ax: number,
  ay: number,
  bx: number,
  by: number,
): number {
  const dx = bx - ax
  const dy = by - ay
  const lenSq = dx * dx + dy * dy
  const t = lenSq === 0 ? 0 : clamp01(((px - ax) * dx + (py - ay) * dy) / lenSq)
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy))
}

/* --------------------------------------------------- anatomy definitions */

/** Portal triads, as quadratic Béziers in isotropic (u, v) space. */
const VESSELS = [
  { p0: [0.62, 0.73], p1: [0.66, 0.54], p2: [0.53, 0.4], r: 0.011 },
  { p0: [0.67, 0.56], p1: [0.79, 0.55], p2: [0.95, 0.5], r: 0.007 },
  { p0: [0.45, 0.37], p1: [0.56, 0.34], p2: [0.73, 0.34], r: 0.005 },
] as const

/** Liver capsule in isotropic units. */
const LIVER_UV = LIVER_POLYGON.map(([x, y]) => [x * ASPECT, y] as [number, number])

function polygonDistance(u: number, v: number): number {
  let best = Infinity
  for (let i = 0, j = LIVER_UV.length - 1; i < LIVER_UV.length; j = i++) {
    const d = distanceToSegment(u, v, LIVER_UV[j][0], LIVER_UV[j][1], LIVER_UV[i][0], LIVER_UV[i][1])
    if (d < best) best = d
  }
  return best
}

function polygonContains(u: number, v: number): boolean {
  let inside = false
  for (let i = 0, j = LIVER_UV.length - 1; i < LIVER_UV.length; j = i++) {
    const [xi, yi] = LIVER_UV[i]
    const [xj, yj] = LIVER_UV[j]
    if (yi > v !== yj > v && u < ((xj - xi) * (v - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

function curveDistance(u: number, v: number, c: (typeof VESSELS)[number]): number {
  let best = Infinity
  let px: number = c.p0[0]
  let py: number = c.p0[1]
  for (let i = 1; i <= 32; i++) {
    const t = i / 32
    const mt = 1 - t
    const x = mt * mt * c.p0[0] + 2 * mt * t * c.p1[0] + t * t * c.p2[0]
    const y = mt * mt * c.p0[1] + 2 * mt * t * c.p1[1] + t * t * c.p2[1]
    const d = distanceToSegment(u, v, px, py, x, y)
    if (d < best) best = d
    px = x
    py = y
  }
  return best
}

/* ------------------------------------------- coarse structure field cache */

const FW = 320
const FH = 240

interface StructureField {
  liver: Float32Array
  capsule: Float32Array
  lumen: Float32Array
  wall: Float32Array
}

function buildStructureField(): StructureField {
  const liver = new Float32Array(FW * FH)
  const capsule = new Float32Array(FW * FH)
  const lumen = new Float32Array(FW * FH)
  const wall = new Float32Array(FW * FH)

  for (let j = 0; j < FH; j++) {
    const v = j / (FH - 1)
    for (let i = 0; i < FW; i++) {
      const u = (i / (FW - 1)) * ASPECT
      const idx = j * FW + i

      // Perturb the capsule with low-frequency noise so the boundary is organic
      // rather than a traced polygon.
      const wobble =
        (hashNoise(i >> 4, j >> 4, 91) - 0.5) * 0.026 +
        (hashNoise(i >> 6, j >> 6, 113) - 0.5) * 0.03
      const d = Math.max(0, polygonDistance(u, v) + wobble)
      const inside = polygonContains(u, v)
      // Parenchyma fades in gradually — real capsules are not brightness steps.
      liver[idx] = inside ? smoothstep(0, 0.06, d) : 0
      // Capsule itself is a thin specular line straddling the boundary.
      capsule[idx] = Math.exp(-((d / 0.006) ** 2))

      let lum = 0
      let wal = 0
      for (const c of VESSELS) {
        const cd = curveDistance(u, v, c)
        lum = Math.max(lum, smoothstep(c.r, c.r * 0.45, cd))
        wal = Math.max(wal, Math.exp(-(((cd - c.r * 1.15) / (c.r * 0.55)) ** 2)))
      }
      lumen[idx] = lum
      wall[idx] = wal
    }
  }

  return { liver, capsule, lumen, wall }
}

/** Bilinear sample of a coarse field at normalised coordinates. */
function sample(field: Float32Array, nx: number, ny: number): number {
  const fx = clamp01(nx) * (FW - 1)
  const fy = clamp01(ny) * (FH - 1)
  const x0 = Math.floor(fx)
  const y0 = Math.floor(fy)
  const x1 = Math.min(FW - 1, x0 + 1)
  const y1 = Math.min(FH - 1, y0 + 1)
  const tx = fx - x0
  const ty = fy - y0
  const a = field[y0 * FW + x0]
  const b = field[y0 * FW + x1]
  const c = field[y1 * FW + x0]
  const d = field[y1 * FW + x1]
  return mix(mix(a, b, tx), mix(c, d, tx), ty)
}

/* --------------------------------------------------------------- shading */

function sectorGate(x: number, y: number): number {
  const dx = x - APEX_X
  const dy = y - APEX_Y
  const r = Math.hypot(dx, dy)
  if (r < R_NEAR - 14 || r > R_FAR) return 0
  const angle = Math.abs(Math.atan2(dx, dy))
  if (angle > HALF_ANGLE) return 0
  const edge = smoothstep(HALF_ANGLE, HALF_ANGLE - 0.045, angle)
  const far = smoothstep(R_FAR, R_FAR - 28, r)
  const near = smoothstep(R_NEAR - 14, R_NEAR + 4, r)
  return edge * far * near
}

/** Base echogenicity at a normalised coordinate, before speckle. */
function echogenicity(nx: number, ny: number, field: StructureField): number {
  const u = nx * ASPECT
  const v = ny

  let e = 0.4 // generic soft tissue

  // Subcutaneous fat and rectus sheath — soft echogenic laminae up top.
  const nearField = smoothstep(0.15, 0.045, ny)
  if (nearField > 0) {
    const bands = 0.5 + 0.5 * Math.sin(ny * 132 + 0.6)
    e = mix(e, 0.34 + bands * 0.2, nearField)
  }

  // Fatty parenchyma: only modestly brighter than the surrounding tissue, so the
  // organ is defined by its capsule and vessels rather than a painted blob.
  e = mix(e, 0.54, sample(field.liver, nx, ny))
  e += sample(field.capsule, nx, ny) * 0.15

  // Diaphragm — bright specular arc behind the right lobe.
  const dia = Math.abs(Math.hypot((nx - 0.5) / 0.4, (ny - 0.15) / 0.6) - 1)
  e = mix(e, 0.92, Math.exp(-((dia / 0.014) ** 2)) * 0.8)

  // Portal triads: echogenic walls, then the anechoic lumen carved out.
  e = mix(e, 0.88, sample(field.wall, nx, ny) * 0.8)
  e = mix(e, 0.12, sample(field.lumen, nx, ny) * 0.92)

  // Hyperechoic nodule (the low-confidence detection).
  const dNod = Math.hypot(u - NODULE.cx * ASPECT, v - NODULE.cy) / (NODULE.r * ASPECT)
  e = mix(e, 0.72, smoothstep(1.05, 0.6, dNod))

  // Simple cyst — thin bright wall, anechoic centre.
  const cystR = CYST.r * ASPECT
  const du = u - CYST.cx * ASPECT
  const dv = v - CYST.cy
  const dCyst = Math.hypot(du, dv) / cystR
  e = mix(e, 0.95, Math.exp(-(((dCyst - 1.03) / 0.13) ** 2)) * 0.7)
  e = mix(e, 0.035, smoothstep(1.02, 0.84, dCyst))

  // Posterior acoustic enhancement — a soft wedge that fades with depth.
  const behind = smoothstep(0, 0.09, dv - cystR * 0.5) * smoothstep(0.4, 0.08, dv)
  const lateral = smoothstep(cystR * 1.15, cystR * 0.2, Math.abs(du))
  e *= 1 + 0.34 * behind * lateral

  // Edge shadowing at the cyst margins.
  const edgeBand = Math.exp(-(((Math.abs(du) - cystR) / (cystR * 0.3)) ** 2))
  e *= 1 - 0.26 * behind * edgeBand

  return e
}

function drawHud(ctx: CanvasRenderingContext2D) {
  ctx.save()
  ctx.font = "500 15px 'JetBrains Mono', ui-monospace, monospace"
  ctx.fillStyle = 'rgba(203, 213, 225, 0.72)'
  ctx.textBaseline = 'top'
  ctx.fillText('SMARTLIVA  ·  ABDOMEN / LIVER', 22, 20)
  ctx.fillText('DEMO STUDY — SYNTHETIC B-MODE', 22, 42)

  ctx.textAlign = 'right'
  ctx.fillText('C5-2  4.0 MHz', W - 22, 20)
  ctx.fillText('MI 0.8   TIS 0.3', W - 22, 42)
  ctx.textAlign = 'left'

  ctx.font = "400 14px 'JetBrains Mono', ui-monospace, monospace"
  ctx.fillStyle = 'rgba(148, 163, 184, 0.68)'
  ctx.fillText('GAIN 62   DR 70   DEPTH 16.0 cm   FR 34 Hz', 22, H - 34)

  // Depth ruler, 2 cm graduations over a 16 cm field.
  ctx.strokeStyle = 'rgba(203, 213, 225, 0.5)'
  ctx.fillStyle = 'rgba(203, 213, 225, 0.6)'
  ctx.lineWidth = 1
  ctx.font = "400 12px 'JetBrains Mono', ui-monospace, monospace"
  for (let cm = 2; cm <= 16; cm += 2) {
    const y = (cm / 16) * (H - 90) + 60
    const long = cm % 4 === 0
    ctx.beginPath()
    ctx.moveTo(W - 34, y)
    ctx.lineTo(W - (long ? 52 : 44), y)
    ctx.stroke()
    if (long) {
      ctx.textAlign = 'right'
      ctx.fillText(String(cm), W - 58, y + 4)
      ctx.textAlign = 'left'
    }
  }
  ctx.restore()
}

let cached: string | null = null

/** Renders the sample study once and memoises the resulting data URL. */
export function createDemoScan(): string {
  if (cached) return cached

  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')
  if (!ctx) return ''

  ctx.fillStyle = '#000000'
  ctx.fillRect(0, 0, W, H)

  const field = buildStructureField()
  const rand = mulberry32(20260809)
  const image = ctx.createImageData(W, H)
  const data = image.data

  for (let y = 0; y < H; y++) {
    const ny = y / H
    // Depth-dependent attenuation — pronounced, as expected in steatosis.
    const attenuation = Math.exp(-Math.max(0, (y - 60) / H) * 1.25)

    for (let x = 0; x < W; x++) {
      const idx = (y * W + x) * 4
      const gate = sectorGate(x, y)
      if (gate <= 0.001) {
        data[idx + 3] = 255
        continue
      }

      const base = echogenicity(x / W, ny, field)

      // Multiplicative speckle across three scales, plus a noise floor.
      const fine = hashNoise(x >> 1, y >> 1, 7)
      const mid = hashNoise(x >> 2, (y >> 2) + 1, 31)
      const coarse = hashNoise(x >> 4, y >> 4, 19)
      const speckle = 0.42 + 0.72 * fine + 0.3 * mid + 0.2 * coarse

      let v = base * speckle * attenuation * gate
      v += (rand() - 0.5) * 0.03
      // Mild S-curve for the display dynamic range.
      v = clamp01(v)
      v = v * v * (3 - 2 * v) * 1.08

      const g = Math.max(0, Math.min(255, Math.round(v * 255)))
      data[idx] = g
      data[idx + 1] = g
      data[idx + 2] = g
      data[idx + 3] = 255
    }
  }

  ctx.putImageData(image, 0, 0)

  // Soften the raw pixel field so it reads as a real transducer image.
  const blurred = document.createElement('canvas')
  blurred.width = W
  blurred.height = H
  const bctx = blurred.getContext('2d')
  if (bctx) {
    bctx.filter = 'blur(0.8px)'
    bctx.drawImage(canvas, 0, 0)
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, W, H)
    ctx.drawImage(blurred, 0, 0)
  }

  drawHud(ctx)

  cached = canvas.toDataURL('image/png')
  return cached
}
