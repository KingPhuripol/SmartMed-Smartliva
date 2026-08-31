"""AI Medical Reviewer Agent powered by Gemini 2.5 Flash with retry & robust fallback."""

import asyncio
import hashlib
import json
import logging
import os
from typing import Dict
from google import genai
from src.workflow.schemas import PredictionResponse

logger = logging.getLogger("SmartLiva.MedicalReviewer")

_REVIEW_CACHE: Dict[str, str] = {}


def generate_structured_clinical_fallback(response: PredictionResponse) -> str:
    """Generate a high-quality, expert-grounded deterministic clinical note when LLM is unreachable."""
    fib = response.fibrosis
    f_stage = fib.stage if fib else "F0"
    f_kpa = f"{fib.kpa_estimate:.1f}" if fib else "4.5"
    f_risk = fib.risk_tier_label if fib else "ต่ำ"
    
    steatosis = response.fatty_liver_stage or "S0"
    steatosis_map = {
        "S0": "ปกติ (No Steatosis)",
        "S1": "ระดับเริ่มต้น (Mild Steatosis / S1)",
        "S2": "ระดับปานกลาง (Moderate Steatosis / S2)",
        "S3": "ระดับรุนแรง (Severe Steatosis / S3)",
    }
    stea_desc = steatosis_map.get(steatosis, steatosis)

    lesions = response.lesions or []
    if lesions:
        lesion_descs = []
        has_malignancy = False
        for l in lesions:
            cname = getattr(l, "class_name", "") or getattr(l, "class", "Lesion")
            conf = int(l.confidence * 100)
            lesion_descs.append(f"{cname} (ความมั่นใจ {conf}%)")
            if cname in ["HCC", "CCA"]:
                has_malignancy = True
        lesion_text = f"ตรวจพบรอยโรค {len(lesions)} จุด: {', '.join(lesion_descs)}"
    else:
        has_malignancy = False
        lesion_text = "ไม่พบรอยโรคเฉพาะที่ในเนื้อตับ (No focal liver lesion detected)"

    fluke_risk = (response.fluke_risk.risk_level if response.fluke_risk else "Low")

    # Construct expert impression
    lines = [
        "ข้อสรุปความเห็นแพทย์ (Clinical Impression & Plan):",
        f"• ภาพรวมการตรวจ: คุณภาพของภาพอัลตราซาวด์อยู่ในเกณฑ์ตรวจวิเคราะห์ได้ ขอบเขตตับครอบคลุม {response.liver_area_percent:.1f}% ของเฟรม",
        f"• พังผืดในตับ (Fibrosis): ระดับ {f_stage} (ประเมินความแข็ง ~{f_kpa} kPa, ความเสี่ยง: {f_risk})",
    ]

    if response.biomarkers and response.biomarkers.calculated and response.biomarkers.fib4_score is not None:
        lines.append(
            f"• คะแนนทางชีวเคมี (FIB-4 Index): {response.biomarkers.fib4_score:.2f} ({response.biomarkers.fib4_risk_tier})"
        )

    lines.extend([
        f"• ไขมันพอกตับ (Steatosis): {stea_desc}",
        f"• รอยโรคเฉพาะที่ (Focal Lesions): {lesion_text}",
        f"• ความเสี่ยงพยาธิใบไม้ตับ/มะเร็งท่อน้ำดี (CCA Risk): ระดับ {fluke_risk}",
    ])

    if has_malignancy:
        lines.append(
            "• แนะนำทางคลินิก: 🚨 พบรอยโรคต้องสงสัยกลุ่ม Malignancy แนะนำส่งตรวจเพิ่มเติมด้วย CT Triphasic Liver Protocol หรือ MRI with Liver-specific Contrast และตรวจระดับซีรั่ม AFP/CA19-9 ด่วน"
        )
    elif f_stage in ["F3", "F4"] or f_risk == "สูง":
        lines.append(
            "• แนะนำทางคลินิก: พบความเสี่ยงของพังผืดระดับสูง/ตับแข็ง แนะนำส่งตรวจ FibroScan ยืนยัน, เจาะเลือดติดตาม LFT/Platelets และนัด Ultrasound เฝ้าระวังทุก 6 เดือน"
        )
    elif steatosis in ["S2", "S3"]:
        lines.append(
            "• แนะนำทางคลินิก: แนะนำปรับพฤติกรรมการรับประทานอาหาร, ควบคุมน้ำหนักและระดับไขมันในเลือด (Lipid Profile) พร้อมนัดตรวจติดตามซ้ำใน 6-12 เดือน"
        )
    else:
        lines.append(
            "• แนะนำทางคลินิก: ผลการตรวจโดยรวมอยู่ในเกณฑ์ปกติ/ความเสี่ยงต่ำ แนะนำตรวจสุขภาพและอัลตราซาวด์ประจำปีตามเกณฑ์มาตรฐาน"
        )

    return "\n".join(lines)


async def run_medical_reviewer_api(response: PredictionResponse) -> PredictionResponse:
    """Generate structured clinical conclusion and recommendations using Gemini API with retry and fallback."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.info("GEMINI_API_KEY not set. Using structured deterministic medical note.")
        response.clinical_report = generate_structured_clinical_fallback(response)
        return response

    # Prepare payload without base64 images for hashing
    data_dict = response.model_dump(exclude={"images"})
    cache_key = hashlib.md5(json.dumps(data_dict, sort_keys=True).encode()).hexdigest()

    if cache_key in _REVIEW_CACHE:
        logger.info("Using cached Gemini clinical reviewer report.")
        response.clinical_report = _REVIEW_CACHE[cache_key]
        return response

    prompt = f"""
You are an expert Hepatologist and Radiologist reviewing ultrasound findings.
Review the following AI analysis, computer vision detections, and clinical parameters:
{json.dumps(data_dict, indent=2, ensure_ascii=False)}

Write a concise, professional medical reviewer note (ข้อสรุปความเห็นแพทย์) summarizing the findings:
1. Overall Impression (ภาพรวมการตรวจ)
2. Key Findings: METAVIR Fibrosis stage & stiffness kPa, Steatosis S-stage, and Focal Lesion status.
3. Clinical Recommendation / Follow-up plan (คำแนะนำทางคลินิก)

Format the output cleanly in Thai mixed with standard medical English terminology. 
Do not use markdown headers (no # or ##), just use bullet points and clean line breaks.
"""

    client = genai.Client(api_key=api_key)

    # Retry loop with exponential backoff for rate limiting
    for attempt in range(2):
        try:
            result = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            if result and result.text:
                cleaned_text = result.text.strip()
                _REVIEW_CACHE[cache_key] = cleaned_text
                response.clinical_report = cleaned_text
                return response
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                if attempt == 0:
                    logger.warning("Gemini 429 rate limit reached. Waiting 2.0s before retry...")
                    await asyncio.sleep(2.0)
                    continue
            logger.error(f"Gemini AI Reviewer failed (attempt {attempt+1}): {err_str}")
            break

    # Fallback to rich deterministic template if API fails
    response.clinical_report = generate_structured_clinical_fallback(response)
    return response
