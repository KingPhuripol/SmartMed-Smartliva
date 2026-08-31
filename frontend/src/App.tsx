import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type {
  AgentId,
  ClinicalData,
  PhysicianReview,
  PipelineProgress,
  Region,
  ReviewEvent,
  ReviewEventKind,
  StageId,
  StageStatus,
  StudyRecord,
} from './domain'
import { AGENT_IDS, createReview, pendingAgents } from './domain'
import {
  analysisPipeline,
  createIntake,
  createSyntheticIntake,
  decodeImage,
} from './engine'
import { createDemoScan } from './lib/demoScan'
import { type ClinicalBenchmarkCase } from './lib/clinicalCases'
import { TopBar } from './components/TopBar'
import { UploadScreen } from './components/UploadScreen'
import { PipelineScreen } from './components/screens/PipelineScreen'
import { RejectScreen } from './components/screens/RejectScreen'
import { StudyViewer } from './components/viewer/StudyViewer'
import type { AnnotationTool } from './components/viewer/LayerControls'
import { ReviewConsole } from './components/review/ReviewConsole'
import { StudyReportModal } from './components/StudyReportModal'
import { FeedbackModal } from './components/FeedbackModal'
import { HistoryModal, type EHRRecord } from './components/HistoryModal'
import { PatientIntakeModal } from './components/PatientIntakeModal'
import { Toast } from './components/ui/Toast'

type Phase = 'upload' | 'running' | 'reject' | 'review'

const DEMO_WIDTH = 960
const DEMO_HEIGHT = 720

let eventSeq = 0

function appendEvent(
  review: PhysicianReview,
  kind: ReviewEventKind,
  summary: string,
  agentId?: AgentId,
): ReviewEvent[] {
  eventSeq += 1
  return [
    ...review.events,
    {
      eventId: `ev-${eventSeq}`,
      at: new Date().toISOString(),
      actor: 'physician',
      kind,
      agentId,
      summary,
    },
  ]
}

export default function App() {
  const [phase, setPhase] = useState<Phase>('upload')
  const [pending, setPending] = useState<{ url: string; name: string } | null>(null)
  const [study, setStudy] = useState<StudyRecord | null>(null)
  const [review, setReview] = useState<PhysicianReview | null>(null)

  const [progress, setProgress] = useState<PipelineProgress | null>(null)
  const [statuses, setStatuses] = useState<Partial<Record<StageId, StageStatus>>>({})
  const [highlightRegionId, setHighlightRegionId] = useState<string | null>(null)
  const [focusedAgentId, setFocusedAgentId] = useState<AgentId | null>(null)
  const [markTool, setMarkTool] = useState<AnnotationTool>('none')
  const [markingFor, setMarkingFor] = useState<AgentId | null>(null)

  const [clinicalData, setClinicalData] = useState<ClinicalData | null>(null)
  const [clinicalModalOpen, setClinicalModalOpen] = useState(false)

  const [reportOpen, setReportOpen] = useState(false)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyCount, setHistoryCount] = useState(0)
  const [submitted, setSubmitted] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const objectUrlRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Load History count on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem('smartliva_ehr_records')
      if (stored) {
        const arr = JSON.parse(stored)
        setHistoryCount(arr.length)
      }
    } catch {
      setHistoryCount(0)
    }
  }, [])

  const releaseObjectUrl = useCallback(() => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = null
    }
  }, [])

  useEffect(
    () => () => {
      abortRef.current?.abort()
      releaseObjectUrl()
    },
    [releaseObjectUrl],
  )

  const runPipeline = useCallback(
    async (intake: Parameters<typeof analysisPipeline.run>[0]) => {
      setPending({ url: intake.source, name: intake.fileName })
      setStudy(null)
      setReview(null)
      setSubmitted(false)
      setProgress(null)
      setStatuses({})
      setPhase('running')

      const controller = new AbortController()
      abortRef.current = controller

      const record = await analysisPipeline.run(intake, {
        signal: controller.signal,
        onProgress: (p) => {
          setProgress(p)
          setStatuses((prev) => ({ ...prev, [p.stageId]: p.status }))
        },
      })

      abortRef.current = null
      setStudy(record)
      setStatuses(
        Object.fromEntries(
          record.stages.map((s) => [s.stageId, s.status]),
        ) as Partial<Record<StageId, StageStatus>>,
      )

      if (record.halt) {
        setPhase('reject')
        return
      }
      setReview(createReview(record.studyId, new Date().toISOString()))
      setPhase('review')
    },
    [],
  )

  const handleFile = useCallback(
    async (file: File) => {
      setUploadError(null)
      try {
        releaseObjectUrl()
        const decoded = await decodeImage(file)
        objectUrlRef.current = decoded.objectUrl
        await runPipeline(createIntake(file, decoded, clinicalData))
      } catch {
        setUploadError('ไม่สามารถอ่านไฟล์ภาพนี้ได้ ไฟล์อาจเสียหายหรือไม่ใช่ไฟล์ภาพ')
        setPhase('upload')
      }
    },
    [clinicalData, releaseObjectUrl, runPipeline],
  )

  const handleSample = useCallback(async () => {
    setUploadError(null)
    releaseObjectUrl()
    const dataUrl = createDemoScan()
    const byteSize = Math.round(((dataUrl.length - dataUrl.indexOf(',') - 1) * 3) / 4)
    await runPipeline(
      createSyntheticIntake(
        dataUrl,
        'SAMPLE_LIVER_US_01.png',
        DEMO_WIDTH,
        DEMO_HEIGHT,
        byteSize,
        clinicalData,
      ),
    )
  }, [clinicalData, releaseObjectUrl, runPipeline])

  const handleSelectBenchmarkCase = useCallback(
    async (c: ClinicalBenchmarkCase) => {
      setUploadError(null)
      releaseObjectUrl()
      try {
        const res = await fetch(c.image_url)
        if (!res.ok) throw new Error('Image fetch failed')
        const blob = await res.blob()
        const file = new File([blob], `${c.id}.jpg`, { type: 'image/jpeg' })
        const decoded = await decodeImage(file)
        objectUrlRef.current = decoded.objectUrl
        await runPipeline(createIntake(file, decoded, clinicalData))
      } catch {
        await handleSample()
      }
    },
    [clinicalData, handleSample, releaseObjectUrl, runPipeline],
  )

  const handleReset = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    releaseObjectUrl()
    setPhase('upload')
    setPending(null)
    setStudy(null)
    setReview(null)
    setReportOpen(false)
    setFeedbackOpen(false)
    setSubmitted(false)
    setHighlightRegionId(null)
    setFocusedAgentId(null)
    setUploadError(null)
  }, [releaseObjectUrl])

  /* ------------------------------------------------------------- EHR Save */
  const saveToEHR = useCallback(() => {
    if (!study || !review) return
    try {
      const records: EHRRecord[] = JSON.parse(
        localStorage.getItem('smartliva_ehr_records') || '[]',
      )
      const steatosisVal = study.agents.steatosis?.value || 'S0'
      const fibrosisVal = study.agents.fibrosis?.value || 'F0'
      const flukeVal = study.agents.fluke?.value || 'Negative'
      const lesionsSummary =
        study.agents.lesion?.value?.findings?.map((f) => f.label).join(', ') ||
        'ไม่พบก้อนเนื้อผิดปกติ'

      const newRecord: EHRRecord = {
        id: Date.now(),
        hn: study.studyId,
        docNo: `RPT-${new Date().getFullYear()}-${Math.floor(1000 + Math.random() * 9000)}`,
        timestamp: new Date().toLocaleString('th-TH'),
        s_stage: String(steatosisVal),
        fibrosis_stage: String(fibrosisVal),
        lesions_summary: lesionsSummary,
        liver_fluke: String(flukeVal),
        doctor_note: study.organ?.service?.warnings?.join(', ') || 'ผลตรวจได้รับการยืนยันโดยแพทย์',
        caseTitle: study.intake.fileName,
        imageUrl: study.intake.source,
      }

      records.unshift(newRecord)
      localStorage.setItem('smartliva_ehr_records', JSON.stringify(records))
      setHistoryCount(records.length)
      setSubmitted(true)
      setToast(`บันทึกผลเข้าเวชระเบียน ${study.studyId} เรียบร้อยแล้ว`)
    } catch (e) {
      console.error('Error saving EHR:', e)
      setToast('เกิดข้อผิดพลาดในการบันทึกข้อมูล')
    }
  }, [study, review])

  /* ------------------------------------------------------------- review */

  const markCorrect = useCallback((agentId: AgentId) => {
    setReview((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        verdicts: {
          ...prev.verdicts,
          [agentId]: {
            agentId,
            verdict: 'correct',
            reviewedAt: new Date().toISOString(),
          },
        },
        events: appendEvent(prev, 'verdict_set', `${agentId}: ถูกต้อง`, agentId),
      } as PhysicianReview
    })
  }, [])

  const markIncorrect = useCallback(
    (agentId: AgentId, correctedValue: unknown, reason: string) => {
      setReview((prev) => {
        if (!prev) return prev
        return {
          ...prev,
          verdicts: {
            ...prev.verdicts,
            [agentId]: {
              agentId,
              verdict: 'incorrect',
              correctedValue: correctedValue as any,
              reason,
              reviewedAt: new Date().toISOString(),
            },
          },
          events: appendEvent(
            prev,
            'value_corrected',
            `${agentId}: ${reason}`,
            agentId,
          ),
        } as PhysicianReview
      })
    },
    [],
  )

  const addAnnotation = useCallback((region: Region) => {
    setReview((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        annotations: [...prev.annotations, region],
        events: appendEvent(
          prev,
          'annotation_added',
          `Added ${region.shape} annotation`,
          region.linkedAgentId,
        ),
      }
    })
  }, [])

  const removeAnnotation = useCallback((regionId: string) => {
    setReview((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        annotations: prev.annotations.filter((r) => r.regionId !== regionId),
        events: appendEvent(prev, 'annotation_removed', `Removed annotation ${regionId}`),
      }
    })
  }, [])

  const updateAnnotationLabel = useCallback((regionId: string, label: string) => {
    setReview((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        annotations: prev.annotations.map((r) =>
          r.regionId === regionId ? { ...r, label } : r,
        ),
      }
    })
  }, [])

  const updateAnnotationNote = useCallback((regionId: string, note: string) => {
    setReview((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        annotations: prev.annotations.map((r) =>
          r.regionId === regionId ? { ...r, note } : r,
        ),
      }
    })
  }, [])

  const assessedAgents = useMemo(
    () => (study ? (AGENT_IDS.filter((id) => study.agents[id]) as AgentId[]) : []),
    [study],
  )
  const reviewedCount = review
    ? assessedAgents.length - pendingAgents(review, assessedAgents).length
    : 0

  return (
    <div className="text-ink">
      <div className="no-print flex h-dvh flex-col overflow-hidden">
        <TopBar
          study={phase === 'review' || phase === 'reject' ? study : null}
          reviewed={reviewedCount}
          total={assessedAgents.length}
          historyCount={historyCount}
          onReset={handleReset}
          onOpenHistory={() => setHistoryOpen(true)}
        />

        <main className="relative flex min-h-0 flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
          {phase === 'upload' && (
            <UploadScreen
              onSelectFile={handleFile}
              onUseSample={handleSample}
              onSelectBenchmarkCase={handleSelectBenchmarkCase}
              externalError={uploadError}
              clinicalData={clinicalData}
              onOpenClinicalModal={() => setClinicalModalOpen(true)}
            />
          )}

          {phase === 'running' && pending && (
            <PipelineScreen
              imageUrl={pending.url}
              imageName={pending.name}
              progress={progress}
              statuses={statuses}
            />
          )}

          {phase === 'reject' && study && (
            <RejectScreen study={study} onRetry={handleReset} />
          )}

          {phase === 'review' && study && review && (
            <>
              <StudyViewer
                isolatedSource={focusedAgentId}
                tool={markTool}
                linkTo={markingFor}
                study={study}
                annotations={review.annotations}
                onAddAnnotation={addAnnotation}
                highlightRegionId={highlightRegionId}
              />
              <ReviewConsole
                study={study}
                review={review}
                onMarkCorrect={markCorrect}
                onMarkIncorrect={markIncorrect}
                onHoverRegion={setHighlightRegionId}
                focusedAgentId={focusedAgentId}
                onFocusAgent={setFocusedAgentId}
                markTool={markTool}
                onRequestMark={(agentId, tool) => {
                  setMarkingFor(tool === 'none' ? null : agentId)
                  setMarkTool(tool)
                }}
                onUpdateAnnotationNote={updateAnnotationNote}
                onUpdateAnnotationLabel={updateAnnotationLabel}
                onRemoveAnnotation={removeAnnotation}
                onGenerateReport={() => setReportOpen(true)}
                onSubmitFeedback={saveToEHR}
                submitted={submitted}
              />
            </>
          )}
        </main>
      </div>

      {reportOpen && study && review && (
        <StudyReportModal
          study={study}
          review={review}
          onClose={() => setReportOpen(false)}
        />
      )}

      {feedbackOpen && study && review && (
        <FeedbackModal
          study={study}
          review={review}
          onClose={() => setFeedbackOpen(false)}
          onConfirm={() => {
            setFeedbackOpen(false)
            setSubmitted(true)
            setToast('ส่งข้อมูลเข้าคิวเทรนโมเดลแล้ว')
          }}
        />
      )}

      <PatientIntakeModal
        isOpen={clinicalModalOpen}
        onClose={() => setClinicalModalOpen(false)}
        initialData={clinicalData}
        onSave={(data) => {
          setClinicalData(data)
          setToast('บันทึกข้อมูลทางคลินิกและผลแล็บแล้ว')
        }}
      />

      <HistoryModal
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        onSelectRecord={() => setReportOpen(true)}
      />

      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}
    </div>
  )
}
