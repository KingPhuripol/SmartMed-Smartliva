import { useState, useMemo } from 'react'
import type { ClinicalData, PatientHistory, LabData, TEData } from '../domain'
import { SparkIcon } from './ui/Icons'

interface PatientIntakeModalProps {
  isOpen: boolean
  onClose: () => void
  initialData?: ClinicalData | null
  onSave: (data: ClinicalData) => void
}

export function PatientIntakeModal({
  isOpen,
  onClose,
  initialData,
  onSave,
}: PatientIntakeModalProps) {
  const [activeTab, setActiveTab] = useState<'history' | 'lab' | 'te'>('history')

  // History State
  const [age, setAge] = useState<string>(initialData?.history?.age?.toString() || '')
  const [gender, setGender] = useState<'M' | 'F' | ''>(initialData?.history?.gender || '')
  const [weight, setWeight] = useState<string>(initialData?.history?.weight_kg?.toString() || '')
  const [height, setHeight] = useState<string>(initialData?.history?.height_cm?.toString() || '')
  const [rawFish, setRawFish] = useState<boolean>(initialData?.history?.raw_fish_consumption ?? false)
  const [flukeHistory, setFlukeHistory] = useState<boolean>(initialData?.history?.fluke_infection_history ?? false)
  const [familyCancer, setFamilyCancer] = useState<boolean>(initialData?.history?.family_cancer_history ?? false)
  const [endemicArea, setEndemicArea] = useState<boolean>(initialData?.history?.endemic_area ?? false)
  const [hbv, setHbv] = useState<boolean>(initialData?.history?.hbv_positive ?? false)
  const [hcv, setHcv] = useState<boolean>(initialData?.history?.hcv_positive ?? false)
  const [alcohol, setAlcohol] = useState<boolean>(initialData?.history?.alcohol_history ?? false)
  const [diabetes, setDiabetes] = useState<boolean>(initialData?.history?.diabetes ?? false)
  const [dyslipidemia, setDyslipidemia] = useState<boolean>(initialData?.history?.dyslipidemia ?? false)

  // Lab State
  const [ast, setAst] = useState<string>(initialData?.lab?.ast?.toString() || '')
  const [alt, setAlt] = useState<string>(initialData?.lab?.alt?.toString() || '')
  const [platelets, setPlatelets] = useState<string>(initialData?.lab?.platelets?.toString() || '')
  const [bilirubin, setBilirubin] = useState<string>(initialData?.lab?.bilirubin?.toString() || '')
  const [alp, setAlp] = useState<string>(initialData?.lab?.alp?.toString() || '')
  const [ggt, setGgt] = useState<string>(initialData?.lab?.ggt?.toString() || '')
  const [afp, setAfp] = useState<string>(initialData?.lab?.afp?.toString() || '')
  const [ca199, setCa199] = useState<string>(initialData?.lab?.ca19_9?.toString() || '')
  const [fbs, setFbs] = useState<string>(initialData?.lab?.fbs?.toString() || '')
  const [hba1c, setHba1c] = useState<string>(initialData?.lab?.hba1c?.toString() || '')

  // TE / View State
  const [stiffness, setStiffness] = useState<string>(initialData?.te?.stiffness_kpa?.toString() || '')
  const [cap, setCap] = useState<string>(initialData?.te?.cap_db_m?.toString() || '')
  const [view, setView] = useState<string>(initialData?.view || 'RH')

  // Live BMI Calculation
  const bmiValue = useMemo(() => {
    const w = parseFloat(weight)
    const h = parseFloat(height)
    if (w > 0 && h > 0) {
      const hM = h / 100
      return (w / (hM * hM)).toFixed(1)
    }
    return null
  }, [weight, height])

  // Live FIB-4 Score Calculation
  const fib4Calculation = useMemo(() => {
    const a = parseFloat(age)
    const astVal = parseFloat(ast)
    const altVal = parseFloat(alt)
    const pltVal = parseFloat(platelets)

    if (a > 0 && astVal > 0 && altVal > 0 && pltVal > 0) {
      const score = (a * astVal) / (pltVal * Math.sqrt(altVal))
      const lowCutoff = a >= 65 ? 2.0 : 1.30
      const highCutoff = 2.67

      let tier: 'low' | 'mid' | 'high' = 'low'
      let label = 'ความเสี่ยงต่ำ (Low Risk: < 1.30)'
      let color = 'text-emerald-700 bg-emerald-50 border-emerald-200'

      if (score < lowCutoff) {
        tier = 'low'
        label = `ความเสี่ยงต่ำ (Low Risk < ${lowCutoff})`
        color = 'text-emerald-700 bg-emerald-50 border-emerald-200'
      } else if (score <= highCutoff) {
        tier = 'mid'
        label = `ก้ำกึ่ง/ปานกลาง (${lowCutoff}–${highCutoff})`
        color = 'text-amber-700 bg-amber-50 border-amber-200'
      } else {
        tier = 'high'
        label = `ความเสี่ยงสูง (High Risk > ${highCutoff})`
        color = 'text-red-700 bg-red-50 border-red-200'
      }

      return { score: score.toFixed(2), tier, label, color }
    }
    return null
  }, [age, ast, alt, platelets])

  // Presets Handler
  const applyPreset = (type: 'clear' | 'normal' | 'fluke' | 'fatty' | 'fibrosis') => {
    if (type === 'clear') {
      setAge(''); setGender(''); setWeight(''); setHeight('')
      setRawFish(false); setFlukeHistory(false); setFamilyCancer(false); setEndemicArea(false)
      setHbv(false); setHcv(false); setAlcohol(false); setDiabetes(false); setDyslipidemia(false)
      setAst(''); setAlt(''); setPlatelets(''); setBilirubin(''); setAlp(''); setGgt('')
      setAfp(''); setCa199(''); setFbs(''); setHba1c('')
      setStiffness(''); setCap(''); setView('RH')
    } else if (type === 'normal') {
      setAge('42'); setGender('M'); setWeight('68'); setHeight('172')
      setRawFish(false); setFlukeHistory(false); setFamilyCancer(false); setEndemicArea(false)
      setHbv(false); setHcv(false); setAlcohol(false); setDiabetes(false); setDyslipidemia(false)
      setAst('24'); setAlt('22'); setPlatelets('245'); setBilirubin('0.7'); setAlp('65'); setGgt('28')
      setAfp('3.2'); setCa199('8.5'); setFbs('88'); setHba1c('5.2')
      setStiffness('4.6'); setCap('195'); setView('RH')
    } else if (type === 'fluke') {
      setAge('56'); setGender('M'); setWeight('62'); setHeight('165')
      setRawFish(true); setFlukeHistory(true); setFamilyCancer(true); setEndemicArea(true)
      setHbv(false); setHcv(false); setAlcohol(true); setDiabetes(false); setDyslipidemia(false)
      setAst('45'); setAlt('38'); setPlatelets('210'); setBilirubin('1.4'); setAlp('145'); setGgt('62')
      setAfp('4.5'); setCa199('42.0'); setFbs('95'); setHba1c('5.6')
      setStiffness('6.2'); setCap('210'); setView('GBH')
    } else if (type === 'fatty') {
      setAge('48'); setGender('F'); setWeight('82'); setHeight('158')
      setRawFish(false); setFlukeHistory(false); setFamilyCancer(false); setEndemicArea(false)
      setHbv(false); setHcv(false); setAlcohol(false); setDiabetes(true); setDyslipidemia(true)
      setAst('52'); setAlt('68'); setPlatelets('260'); setBilirubin('0.9'); setAlp('85'); setGgt('55')
      setAfp('2.8'); setCa199('12.0'); setFbs('126'); setHba1c('6.8')
      setStiffness('5.8'); setCap('290'); setView('RH')
    } else if (type === 'fibrosis') {
      setAge('58'); setGender('M'); setWeight('70'); setHeight('168')
      setRawFish(false); setFlukeHistory(false); setFamilyCancer(false); setEndemicArea(false)
      setHbv(true); setHcv(false); setAlcohol(false); setDiabetes(false); setDyslipidemia(false)
      setAst('85'); setAlt('42'); setPlatelets('115'); setBilirubin('1.8'); setAlp('98'); setGgt('72')
      setAfp('28.5'); setCa199('18.0'); setFbs('102'); setHba1c('5.8')
      setStiffness('14.2'); setCap('240'); setView('RH')
    }
  }

  const handleSave = () => {
    const historyData: PatientHistory = {
      age: age ? parseInt(age, 10) : undefined,
      gender: gender ? (gender as 'M' | 'F') : undefined,
      weight_kg: weight ? parseFloat(weight) : undefined,
      height_cm: height ? parseFloat(height) : undefined,
      bmi: bmiValue ? parseFloat(bmiValue) : undefined,
      raw_fish_consumption: rawFish,
      fluke_infection_history: flukeHistory,
      family_cancer_history: familyCancer,
      endemic_area: endemicArea,
      hbv_positive: hbv,
      hcv_positive: hcv,
      alcohol_history: alcohol,
      diabetes: diabetes,
      dyslipidemia: dyslipidemia,
    }

    const labData: LabData = {
      ast: ast ? parseFloat(ast) : undefined,
      alt: alt ? parseFloat(alt) : undefined,
      platelets: platelets ? parseFloat(platelets) : undefined,
      bilirubin: bilirubin ? parseFloat(bilirubin) : undefined,
      alp: alp ? parseFloat(alp) : undefined,
      ggt: ggt ? parseFloat(ggt) : undefined,
      afp: afp ? parseFloat(afp) : undefined,
      ca19_9: ca199 ? parseFloat(ca199) : undefined,
      fbs: fbs ? parseFloat(fbs) : undefined,
      hba1c: hba1c ? parseFloat(hba1c) : undefined,
    }

    const teData: TEData = {
      stiffness_kpa: stiffness ? parseFloat(stiffness) : undefined,
      cap_db_m: cap ? parseFloat(cap) : undefined,
    }

    const clinical: ClinicalData = {
      view: view || 'RH',
      history: historyData,
      lab: labData,
      te: teData,
      biomarkers: fib4Calculation
        ? {
            fib4_score: parseFloat(fib4Calculation.score),
            fib4_risk_tier: fib4Calculation.label,
            calculated: true,
          }
        : undefined,
    }

    onSave(clinical)
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-3xl rounded-2xl bg-card border border-line shadow-2xl overflow-hidden flex flex-col max-h-[90vh] animate-rise">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-line px-6 py-4 bg-sunken">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 text-medical border border-emerald-200">
              <span className="text-xl">📋</span>
            </div>
            <div>
              <h3 className="text-lg font-bold text-ink">กรอกข้อมูลผู้ป่วย & ผลแล็บ (Clinical Intake)</h3>
              <p className="text-xs text-ink-muted">
                ข้อมูลประวัติเสี่ยง, ผลเลือดทางห้องปฏิบัติการ และดัชนีคะแนน FIB-4
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-ink-muted hover:bg-card hover:text-ink transition cursor-pointer"
          >
            ✕
          </button>
        </div>

        {/* Quick Presets Bar */}
        <div className="flex flex-wrap items-center gap-1.5 px-6 py-2.5 bg-emerald-50/50 border-b border-line text-xs">
          <span className="font-semibold text-ink-muted flex items-center gap-1">
            <SparkIcon className="h-3.5 w-3.5 text-amber-500" />
            ตัวอย่างเคสทดสอบ:
          </span>
          <button
            type="button"
            onClick={() => applyPreset('normal')}
            className="rounded-md border border-line bg-card px-2.5 py-1 text-ink hover:border-medical hover:text-medical transition cursor-pointer"
          >
            🟢 ตับปกติ
          </button>
          <button
            type="button"
            onClick={() => applyPreset('fluke')}
            className="rounded-md border border-line bg-card px-2.5 py-1 text-ink hover:border-red-500 hover:text-red-600 transition cursor-pointer font-medium"
          >
            🔴 เสี่ยงพยาธิใบไม้/CCA สูง
          </button>
          <button
            type="button"
            onClick={() => applyPreset('fatty')}
            className="rounded-md border border-line bg-card px-2.5 py-1 text-ink hover:border-amber-500 hover:text-amber-600 transition cursor-pointer"
          >
            🟡 ไขมันพอกตับ (MASLD)
          </button>
          <button
            type="button"
            onClick={() => applyPreset('fibrosis')}
            className="rounded-md border border-line bg-card px-2.5 py-1 text-ink hover:border-purple-500 hover:text-purple-600 transition cursor-pointer"
          >
            🟣 พังผืดสูง / ไวรัสบี
          </button>
          <button
            type="button"
            onClick={() => applyPreset('clear')}
            className="ml-auto rounded-md text-ink-muted hover:text-red-500 px-2 py-1 transition cursor-pointer"
          >
            ล้างข้อมูล
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-line px-6 pt-2 bg-card">
          <button
            type="button"
            onClick={() => setActiveTab('history')}
            className={`pb-3 px-4 text-sm font-semibold border-b-2 transition-all cursor-pointer ${
              activeTab === 'history'
                ? 'border-medical text-medical'
                : 'border-transparent text-ink-muted hover:text-ink'
            }`}
          >
            1. ข้อมูลทั่วไป & ประวัติเสี่ยง
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('lab')}
            className={`pb-3 px-4 text-sm font-semibold border-b-2 transition-all cursor-pointer ${
              activeTab === 'lab'
                ? 'border-medical text-medical'
                : 'border-transparent text-ink-muted hover:text-ink'
            }`}
          >
            2. ผลตรวจเลือด (Labs)
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('te')}
            className={`pb-3 px-4 text-sm font-semibold border-b-2 transition-all cursor-pointer ${
              activeTab === 'te'
                ? 'border-medical text-medical'
                : 'border-transparent text-ink-muted hover:text-ink'
            }`}
          >
            3. FibroScan & มุมตรวจ
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* TAB 1: HISTORY */}
          {activeTab === 'history' && (
            <div className="space-y-5">
              {/* Demographics Row */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div>
                  <label className="block text-xs font-bold text-ink mb-1">อายุ (ปี)</label>
                  <input
                    type="number"
                    value={age}
                    onChange={(e) => setAge(e.target.value)}
                    placeholder="เช่น 55"
                    className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-ink mb-1">เพศ</label>
                  <select
                    value={gender}
                    onChange={(e) => setGender(e.target.value as any)}
                    className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none cursor-pointer"
                  >
                    <option value="">-- ไม่ระบุ --</option>
                    <option value="M">ชาย (Male)</option>
                    <option value="F">หญิง (Female)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-bold text-ink mb-1">น้ำหนัก (กก.)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={weight}
                    onChange={(e) => setWeight(e.target.value)}
                    placeholder="เช่น 68.5"
                    className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold text-ink mb-1">ส่วนสูง (ซม.)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={height}
                    onChange={(e) => setHeight(e.target.value)}
                    placeholder="เช่น 170"
                    className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none"
                  />
                </div>
              </div>

              {bmiValue && (
                <div className="flex items-center gap-2 text-xs font-medium text-ink bg-sunken p-2.5 rounded-xl border border-line">
                  <span>⚖️ ดัชนีมวลกาย (BMI):</span>
                  <span className="font-bold text-medical">{bmiValue} kg/m²</span>
                  <span className="text-ink-muted">
                    ({parseFloat(bmiValue) >= 25 ? 'น้ำหนักเกิน/โรคอ้วน' : 'เกณฑ์ปกติ'})
                  </span>
                </div>
              )}

              {/* Risk Factors Group */}
              <div className="border-t border-line pt-4">
                <h4 className="text-xs font-bold uppercase tracking-wider text-ink-muted mb-3 flex items-center gap-1.5">
                  <span>🦠</span> ปัจจัยเสี่ยงพยาธิใบไม้ตับ & มะเร็งท่อน้ำดี (CCA Risk Factors)
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <label className="flex items-start gap-2.5 rounded-xl border border-line bg-sunken p-3 cursor-pointer hover:border-medical transition">
                    <input
                      type="checkbox"
                      checked={rawFish}
                      onChange={(e) => setRawFish(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-line text-medical focus:ring-medical"
                    />
                    <div>
                      <p className="text-xs font-bold text-ink">ประวัติรับประทานปลาน้ำจืดดิบ</p>
                      <p className="text-[11px] text-ink-muted">ก้อยปลา, ลาบปลาดิบ, ปลาส้มสุกๆ ดิบๆ</p>
                    </div>
                  </label>

                  <label className="flex items-start gap-2.5 rounded-xl border border-line bg-sunken p-3 cursor-pointer hover:border-medical transition">
                    <input
                      type="checkbox"
                      checked={flukeHistory}
                      onChange={(e) => setFlukeHistory(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-line text-medical focus:ring-medical"
                    />
                    <div>
                      <p className="text-xs font-bold text-ink">เคยตรวจพบ/รักษาพยาธิใบไม้ตับ</p>
                      <p className="text-[11px] text-ink-muted">เคยกินยา Praziquantel หรือพบไข่พยาธิ</p>
                    </div>
                  </label>

                  <label className="flex items-start gap-2.5 rounded-xl border border-line bg-sunken p-3 cursor-pointer hover:border-medical transition">
                    <input
                      type="checkbox"
                      checked={familyCancer}
                      onChange={(e) => setFamilyCancer(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-line text-medical focus:ring-medical"
                    />
                    <div>
                      <p className="text-xs font-bold text-ink">ประวัติมะเร็งท่อน้ำดีในครอบครัว</p>
                      <p className="text-[11px] text-ink-muted">ญาติสายตรงมีประวัติมะเร็งตับ/ท่อน้ำดี</p>
                    </div>
                  </label>

                  <label className="flex items-start gap-2.5 rounded-xl border border-line bg-sunken p-3 cursor-pointer hover:border-medical transition">
                    <input
                      type="checkbox"
                      checked={endemicArea}
                      onChange={(e) => setEndemicArea(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-line text-medical focus:ring-medical"
                    />
                    <div>
                      <p className="text-xs font-bold text-ink">ภูมิลำเนาในพื้นที่ระบาด</p>
                      <p className="text-[11px] text-ink-muted">ภาคตะวันออกเฉียงเหนือหรือภาคเหนือ</p>
                    </div>
                  </label>
                </div>
              </div>

              {/* Hepatitis & Lifestyle */}
              <div className="border-t border-line pt-4">
                <h4 className="text-xs font-bold uppercase tracking-wider text-ink-muted mb-3 flex items-center gap-1.5">
                  <span>🧬</span> ไวรัสตับอักเสบ & พฤติกรรมสุขภาพ
                </h4>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <label className="flex items-center gap-2 rounded-xl border border-line bg-sunken p-2.5 cursor-pointer hover:border-medical">
                    <input
                      type="checkbox"
                      checked={hbv}
                      onChange={(e) => setHbv(e.target.checked)}
                      className="h-4 w-4 rounded text-medical"
                    />
                    <span className="text-xs font-semibold text-ink">ไวรัสตับ B (HBsAg+)</span>
                  </label>

                  <label className="flex items-center gap-2 rounded-xl border border-line bg-sunken p-2.5 cursor-pointer hover:border-medical">
                    <input
                      type="checkbox"
                      checked={hcv}
                      onChange={(e) => setHcv(e.target.checked)}
                      className="h-4 w-4 rounded text-medical"
                    />
                    <span className="text-xs font-semibold text-ink">ไวรัสตับ C (HCV+)</span>
                  </label>

                  <label className="flex items-center gap-2 rounded-xl border border-line bg-sunken p-2.5 cursor-pointer hover:border-medical">
                    <input
                      type="checkbox"
                      checked={alcohol}
                      onChange={(e) => setAlcohol(e.target.checked)}
                      className="h-4 w-4 rounded text-medical"
                    />
                    <span className="text-xs font-semibold text-ink">ดื่มสุราประจำ</span>
                  </label>

                  <label className="flex items-center gap-2 rounded-xl border border-line bg-sunken p-2.5 cursor-pointer hover:border-medical">
                    <input
                      type="checkbox"
                      checked={diabetes}
                      onChange={(e) => setDiabetes(e.target.checked)}
                      className="h-4 w-4 rounded text-medical"
                    />
                    <span className="text-xs font-semibold text-ink">เบาหวาน (DM)</span>
                  </label>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: LAB TESTS */}
          {activeTab === 'lab' && (
            <div className="space-y-5">
              {/* FIB-4 Banner */}
              {fib4Calculation && (
                <div className={`p-4 rounded-xl border ${fib4Calculation.color} flex items-center justify-between`}>
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">📊</span>
                    <div>
                      <p className="text-xs font-bold uppercase tracking-wider">
                        ดัชนีคะแนนพังผืดตับ (FIB-4 Index Calculator)
                      </p>
                      <p className="text-sm font-bold mt-0.5">
                        คะแนน FIB-4: <span className="text-lg">{fib4Calculation.score}</span> — {fib4Calculation.label}
                      </p>
                    </div>
                  </div>
                  <span className="text-[11px] font-mono bg-white/80 dark:bg-black/40 px-2.5 py-1 rounded-md border border-line">
                    (Age × AST) / (PLT × √ALT)
                  </span>
                </div>
              )}

              {/* Liver Function Tests (LFTs) */}
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-ink-muted mb-3">
                  ผลการตรวจการทำงานของตับ (Liver Function Tests)
                </h4>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div>
                    <label className="block text-xs font-bold text-ink mb-1">AST / SGOT (U/L)</label>
                    <input
                      type="number"
                      step="0.1"
                      value={ast}
                      onChange={(e) => setAst(e.target.value)}
                      placeholder="ปกติ < 35"
                      className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-ink mb-1">ALT / SGPT (U/L)</label>
                    <input
                      type="number"
                      step="0.1"
                      value={alt}
                      onChange={(e) => setAlt(e.target.value)}
                      placeholder="ปกติ < 40"
                      className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-ink mb-1">เกล็ดเลือด (10⁹/L)</label>
                    <input
                      type="number"
                      step="1"
                      value={platelets}
                      onChange={(e) => setPlatelets(e.target.value)}
                      placeholder="ปกติ 150-450"
                      className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-ink mb-1">Total Bilirubin (mg/dL)</label>
                    <input
                      type="number"
                      step="0.1"
                      value={bilirubin}
                      onChange={(e) => setBilirubin(e.target.value)}
                      placeholder="ปกติ 0.2-1.2"
                      className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Biliary & Tumor Markers */}
              <div className="border-t border-line pt-4">
                <h4 className="text-xs font-bold uppercase tracking-wider text-ink-muted mb-3 flex items-center gap-1.5">
                  <span>🎯</span> เอนไซม์ท่อน้ำดี & สารบ่งชี้มะเร็ง (Biliary & Tumor Markers)
                </h4>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div>
                    <label className="block text-xs font-bold text-ink mb-1">ALP (U/L)</label>
                    <input
                      type="number"
                      step="1"
                      value={alp}
                      onChange={(e) => setAlp(e.target.value)}
                      placeholder="ท่อน้ำดี ปกติ < 120"
                      className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-ink mb-1">GGT (U/L)</label>
                    <input
                      type="number"
                      step="1"
                      value={ggt}
                      onChange={(e) => setGgt(e.target.value)}
                      placeholder="ปกติ < 50"
                      className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-ink mb-1">AFP (ng/mL)</label>
                    <input
                      type="number"
                      step="0.1"
                      value={afp}
                      onChange={(e) => setAfp(e.target.value)}
                      placeholder="มะเร็งตับ HCC < 10"
                      className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-ink mb-1">CA 19-9 (U/mL)</label>
                    <input
                      type="number"
                      step="0.1"
                      value={ca199}
                      onChange={(e) => setCa199(e.target.value)}
                      placeholder="มะเร็งท่อน้ำดี < 37"
                      className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Metabolic Sugar Panel */}
              <div className="border-t border-line pt-4">
                <h4 className="text-xs font-bold uppercase tracking-wider text-ink-muted mb-3">
                  ระดับน้ำตาลในเลือด (Metabolic Glucose)
                </h4>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div>
                    <label className="block text-xs font-bold text-ink mb-1">FBS (mg/dL)</label>
                    <input
                      type="number"
                      value={fbs}
                      onChange={(e) => setFbs(e.target.value)}
                      placeholder="ปกติ 70-99"
                      className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-ink mb-1">HbA1c (%)</label>
                    <input
                      type="number"
                      step="0.1"
                      value={hba1c}
                      onChange={(e) => setHba1c(e.target.value)}
                      placeholder="ปกติ < 5.7"
                      className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: FIBROSCAN & VIEW */}
          {activeTab === 'te' && (
            <div className="space-y-5">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-bold text-ink mb-1">
                    ความแข็งตับ FibroScan (Stiffness kPa)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    value={stiffness}
                    onChange={(e) => setStiffness(e.target.value)}
                    placeholder="เช่น 5.4 kPa"
                    className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none"
                  />
                  <p className="text-[11px] text-ink-muted mt-1">F0-F1 &lt; 7.0 kPa, F4 &ge; 12.5 kPa</p>
                </div>

                <div>
                  <label className="block text-xs font-bold text-ink mb-1">
                    ค่า CAP (Controlled Attenuation Parameter)
                  </label>
                  <input
                    type="number"
                    step="1"
                    value={cap}
                    onChange={(e) => setCap(e.target.value)}
                    placeholder="เช่น 240 dB/m"
                    className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none"
                  />
                  <p className="text-[11px] text-ink-muted mt-1">S1 &ge; 238, S2 &ge; 260, S3 &ge; 290 dB/m</p>
                </div>

                <div>
                  <label className="block text-xs font-bold text-ink mb-1">มุมตรวจอัลตราซาวด์ (US View)</label>
                  <select
                    value={view}
                    onChange={(e) => setView(e.target.value)}
                    className="w-full rounded-xl border border-line bg-sunken px-3 py-2 text-sm text-ink focus:border-medical focus:outline-none cursor-pointer"
                  >
                    <option value="RH">RH (Right Hepatic / กลีบขวา)</option>
                    <option value="GBH">GBH (Gallbladder Hepatic / ตัดถุงน้ำดี)</option>
                    <option value="LHA">LHA (Left Hepatic Anterior)</option>
                    <option value="LHP">LHP (Left Hepatic Posterior)</option>
                    <option value="SPH">SPH (Subcostal Parenchymal)</option>
                    <option value="LHV">LHV (Left Hepatic Vein)</option>
                    <option value="FPH">FPH (Four-Phasic Hepatic)</option>
                  </select>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between border-t border-line px-6 py-4 bg-sunken">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-line bg-card px-5 py-2.5 text-sm font-semibold text-ink hover:bg-sunken transition cursor-pointer"
          >
            ยกเลิก
          </button>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleSave}
              className="rounded-xl bg-medical px-6 py-2.5 text-sm font-bold text-white shadow-md hover:bg-medical/90 transition cursor-pointer active:scale-[0.98]"
            >
              บันทึกข้อมูลและนำไปใช้ ✓
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
