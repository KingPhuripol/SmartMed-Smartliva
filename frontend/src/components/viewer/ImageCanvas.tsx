import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { containRect } from '../../lib/geometry'

interface ImageCanvasProps {
  imageUrl: string
  imageName: string
  /** Rendered inside a box that exactly covers the letterboxed image. */
  children?: ReactNode
  caption?: string
  /** Enables pointer capture and reports normalised 0..1 coordinates. */
  onCanvasPointerDown?: (point: [number, number], event: React.PointerEvent) => void
  onCanvasPointerMove?: (point: [number, number], event: React.PointerEvent) => void
  onCanvasPointerUp?: (point: [number, number], event: React.PointerEvent) => void
  interactive?: boolean
  cursor?: string
  /**
   * Where the letterboxed image actually landed, in container pixels, so
   * siblings can align to its edges and sit a constant distance below it
   * regardless of the image's aspect ratio.
   */
  onFrameRect?: (rect: { left: number; top: number; width: number; height: number }) => void
}

/**
 * Measures where an `object-contain` image actually lands inside its container
 * and exposes that box to its children.
 *
 * Every overlay in the app draws in normalised 0..1 space; this component is the
 * single place that space becomes pixels. Keeping the conversion here is why
 * masks, agent regions and physician annotations all stay aligned across screen
 * sizes, zoom levels and images of different aspect ratios.
 */
export function ImageCanvas({
  imageUrl,
  imageName,
  children,
  caption,
  onCanvasPointerDown,
  onCanvasPointerMove,
  onCanvasPointerUp,
  interactive = false,
  cursor,
  onFrameRect,
}: ImageCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const frameRef = useRef<HTMLDivElement>(null)
  const [box, setBox] = useState({ w: 0, h: 0 })
  const [natural, setNatural] = useState({ w: 0, h: 0 })

  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => {
      setBox({ w: entry.contentRect.width, h: entry.contentRect.height })
    })
    observer.observe(el)
    setBox({ w: el.clientWidth, h: el.clientHeight })
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    setNatural({ w: 0, h: 0 })
  }, [imageUrl])

  const rect = containRect(box.w, box.h, natural.w, natural.h)
  const ready = rect.width > 0

  const { left, top, width, height } = rect
  useEffect(() => {
    if (width > 0) onFrameRect?.({ left, top, width, height })
  }, [left, top, width, height, onFrameRect])

  const toNormalised = useCallback((event: React.PointerEvent): [number, number] => {
    const frame = frameRef.current
    if (!frame) return [0, 0]
    const bounds = frame.getBoundingClientRect()
    const x = (event.clientX - bounds.left) / bounds.width
    const y = (event.clientY - bounds.top) / bounds.height
    return [Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))]
  }, [])

  return (
    <div ref={containerRef} className="relative h-full w-full">
      <img
        src={imageUrl}
        alt=""
        aria-hidden="true"
        className="pointer-events-none absolute h-px w-px opacity-0"
        onLoad={(e) =>
          setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })
        }
      />

      {ready && (
        <div
          ref={frameRef}
          className="absolute overflow-hidden rounded-lg ring-1 ring-line"
          style={{
            left: rect.left,
            top: rect.top,
            width: rect.width,
            height: rect.height,
            cursor,
            touchAction: interactive ? 'none' : undefined,
          }}
          onPointerDown={
            interactive
              ? (e) => {
                  e.currentTarget.setPointerCapture(e.pointerId)
                  onCanvasPointerDown?.(toNormalised(e), e)
                }
              : undefined
          }
          onPointerMove={
            interactive ? (e) => onCanvasPointerMove?.(toNormalised(e), e) : undefined
          }
          onPointerUp={
            interactive
              ? (e) => {
                  e.currentTarget.releasePointerCapture(e.pointerId)
                  onCanvasPointerUp?.(toNormalised(e), e)
                }
              : undefined
          }
        >
          {/* Native image dragging starts its own drag-and-drop, which swallows the
              pointer stream mid-gesture — the box preview then never updates and
              the drag looks broken. select-none does not cover this. */}
          <img
            src={imageUrl}
            alt={imageName}
            draggable={false}
            onDragStart={(e) => e.preventDefault()}
            className="block h-full w-full select-none"
          />
          {children}

          {caption && (
            <div className="border-line bg-card/80 pointer-events-none absolute top-2 left-2 rounded-md border px-2 py-1 text-[10px] font-medium tracking-[0.14em] text-ink uppercase backdrop-blur-sm">
              {caption}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
