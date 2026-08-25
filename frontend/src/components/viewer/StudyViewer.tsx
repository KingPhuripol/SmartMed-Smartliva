import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { AgentId, Region, RegionSource, StudyRecord } from "../../domain";
import { AGENT_IDS } from "../../domain";
import { buildRegionKey } from "../../lib/regionKey";
import { ImageCanvas } from "./ImageCanvas";
import { RegionLayer } from "./RegionLayer";
import { LayerControls } from "./LayerControls";
import type { AnnotationTool } from "./LayerControls";

interface StudyViewerProps {
  study: StudyRecord;
  /** When set, only this source and the liver outline are drawn. */
  isolatedSource?: RegionSource | null;
  tool: AnnotationTool;
  /** Agent the physician is correcting; marks drawn now belong to it. */
  linkTo?: AgentId | null;
  annotations: Region[];
  onAddAnnotation: (region: Region) => void;
  highlightRegionId: string | null;
}

let annotationSeq = 0;

/** Constant distance between the bottom of the image and the toolbar. */
const FRAME_GAP = 20;

/**
 * Left pane — the image plus every layer drawn over it.
 *
 * Region visibility is per-source, so the physician can isolate one agent's
 * reasoning ("show me only what the fibrosis agent looked at") or view all four
 * at once. Their own marks are just another layer with its own colour.
 */
export function StudyViewer({
  study,
  isolatedSource = null,
  tool,
  linkTo = null,
  annotations,
  onAddAnnotation,
  highlightRegionId,
}: StudyViewerProps) {
  const assessedAgents = useMemo(
    () => AGENT_IDS.filter((id) => study.agents[id] !== undefined) as AgentId[],
    [study.agents],
  );

  const [visibleSources, setVisibleSources] = useState<Set<RegionSource>>(
    () =>
      new Set<RegionSource>(["segmentation", "physician", ...assessedAgents]),
  );
  // Low by default: the mask is context, and a heavy fill hides the very
  // speckle pattern the physician is checking the agents against.
  const [maskOpacity, setMaskOpacity] = useState(0.22);
  const [dragStart, setDragStart] = useState<[number, number] | null>(null);
  const [dragCurrent, setDragCurrent] = useState<[number, number] | null>(null);
  // Hovering a row in the key lights up its marker; an agent card selected in the
  // review pane still wins, since that is the physician's current subject.
  const [hoveredRegionId, setHoveredRegionId] = useState<string | null>(null);
  // The controls belong to the image, so they take the image's measured width
  // rather than a fixed max-width that only happens to match some aspect ratios.
  const [frameRect, setFrameRect] = useState<{
    left: number;
    top: number;
    width: number;
    height: number;
  } | null>(null);
  // frameRect is measured inside the image area; the toolbar is positioned on
  // the section. This is the offset between the two coordinate spaces. It does
  // not depend on the toolbar, so measuring it introduces no feedback.
  const areaRef = useRef<HTMLDivElement>(null);
  const [areaOffsetTop, setAreaOffsetTop] = useState(0);

  useLayoutEffect(() => {
    const el = areaRef.current;
    if (!el) return;
    const read = () =>
      setAreaOffsetTop(
        el.offsetTop + parseFloat(getComputedStyle(el).paddingTop),
      );
    read();
    window.addEventListener("resize", read);
    return () => window.removeEventListener("resize", read);
  }, []);

  const modelRegions = useMemo(() => {
    const regions: Region[] = [...(study.segmentation?.regions ?? [])];
    for (const agentId of assessedAgents) {
      const output = study.agents[agentId];
      if (output) regions.push(...output.regions);
    }
    return regions;
  }, [study, assessedAgents]);

  const previewRegion: Region | null =
    tool === "box" && dragStart && dragCurrent
      ? {
          regionId: "preview",
          shape: "box",
          points: [dragStart, dragCurrent],
          label: "บริเวณที่สงสัย",
          confidence: null,
          source: "physician",
        }
      : null;

  // Cheap enough to rebuild each render; the drag preview changes constantly.
  const allRegions = [
    ...modelRegions,
    ...annotations,
    ...(previewRegion ? [previewRegion] : []),
  ];
  const keyEntries = buildRegionKey(allRegions);
  // The physician's own marks are never hidden. Isolation exists to quiet the
  // OTHER agents' overlays while one finding is judged — but the marks being
  // drawn right now are the reason the tool was armed, and the box preview is a
  // physician region too, so dropping the source made drawing look broken.
  const shownSources = isolatedSource
    ? new Set<RegionSource>(["segmentation", "physician", isolatedSource])
    : visibleSources;
  const activeRegionId = highlightRegionId ?? hoveredRegionId;

  const toggleSource = (source: RegionSource) => {
    setVisibleSources((prev) => {
      const next = new Set(prev);
      if (next.has(source)) next.delete(source);
      else next.add(source);
      return next;
    });
  };

  const commitAnnotation = (region: Omit<Region, "regionId">) => {
    annotationSeq += 1;
    onAddAnnotation({
      ...region,
      regionId: `phys-${annotationSeq}`,
      ...(linkTo ? { linkedAgentId: linkTo } : {}),
    });
    // Make sure a freshly drawn mark is actually visible.
    setVisibleSources((prev) => new Set(prev).add("physician"));
  };

  return (
    <section
      data-surface="dark"
      className="bg-page text-ink relative flex min-h-[46vh] flex-1 flex-col lg:min-h-0"
    >
      <div className="pointer-events-none absolute inset-0 opacity-40" />

      <div className="no-print relative z-10 flex shrink-0 items-center gap-3 px-5 pt-4">
        <h2 className="text-[13px] font-semibold tracking-[0.14em] text-ink uppercase">
          Image Visualizer
        </h2>
        <span className="tnum hidden text-[11.5px] text-ink-muted sm:inline">
          {study.intake.fileName}
        </span>
        <span className="tnum ml-auto hidden text-[11px] text-ink-muted sm:inline">
          {study.intake.width}×{study.intake.height}
        </span>
      </div>

      <div
        ref={areaRef}
        className="relative min-h-[300px] flex-1 px-5 pt-3 pb-3 lg:min-h-0 lg:pb-60"
      >
        <ImageCanvas
          imageUrl={study.intake.source}
          imageName={study.intake.fileName}
          interactive={tool !== "none"}
          cursor={tool === "none" ? undefined : "crosshair"}
          onFrameRect={setFrameRect}
          onCanvasPointerDown={(point) => {
            if (tool === "point") {
              commitAnnotation({
                shape: "point",
                points: [point],
                label: "จุดที่สงสัย",
                confidence: null,
                source: "physician",
              });
              return;
            }
            if (tool === "box") {
              setDragStart(point);
              setDragCurrent(point);
            }
          }}
          onCanvasPointerMove={(point) => {
            if (tool === "box" && dragStart) setDragCurrent(point);
          }}
          onCanvasPointerUp={(point) => {
            if (tool !== "box" || !dragStart) return;
            const [x1, y1] = dragStart;
            const [x2, y2] = point;
            // Ignore accidental taps that produce a zero-area box.
            if (Math.abs(x2 - x1) > 0.01 && Math.abs(y2 - y1) > 0.01) {
              commitAnnotation({
                shape: "box",
                points: [
                  [Math.min(x1, x2), Math.min(y1, y2)],
                  [Math.max(x1, x2), Math.max(y1, y2)],
                ],
                label: "บริเวณที่สงสัย",
                confidence: null,
                source: "physician",
              });
            }
            setDragStart(null);
            setDragCurrent(null);
          }}
        >
          <RegionLayer
            regions={allRegions}
            visibleSources={shownSources}
            highlightRegionId={activeRegionId}
            fillOpacity={maskOpacity}
            keyEntries={keyEntries}
          />
        </ImageCanvas>
      </div>

      <div className="no-print relative z-20 shrink-0 px-4 pb-4 lg:pointer-events-none lg:absolute lg:inset-x-0 lg:top-0 lg:flex lg:justify-center lg:px-0 lg:pb-0">
        <div
          className="lg:pointer-events-auto lg:w-full"
          style={
            frameRect
              ? {
                  maxWidth: frameRect.width,
                  // 20px below wherever the image ended, for every image.
                  transform: `translateY(${areaOffsetTop + frameRect.top + frameRect.height + FRAME_GAP}px)`,
                }
              : undefined
          }
        >
          <LayerControls
            assessedAgents={assessedAgents}
            visibleSources={shownSources}
            isolated={isolatedSource !== null}
            onToggleSource={toggleSource}
            maskOpacity={maskOpacity}
            onMaskOpacityChange={setMaskOpacity}
            annotationCount={annotations.length}
            keyEntries={keyEntries}
            highlightRegionId={activeRegionId}
            onHighlight={setHoveredRegionId}
          />
        </div>
      </div>
    </section>
  );
}
