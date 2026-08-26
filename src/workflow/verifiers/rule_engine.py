"""Deterministic Medical Rules Engine."""

from typing import List
from src.workflow.schemas import PredictionResponse


async def run_deterministic_rule_engine(response: PredictionResponse) -> PredictionResponse:
    """Apply strict clinical validation and guardrail rules to AI findings."""
    warnings: List[str] = []

    # 1. Image and Segmentation Guardrails
    if response.low_confidence_warning:
        warnings.append("พบรอยโรคที่มีความเชื่อมั่นต่ำกว่า 60% (Low confidence < 60%) โปรดตรวจสอบซ้ำ")

    if 0 < response.liver_area_percent < 5.0:
        warnings.append("พื้นที่ตับที่ตรวจพบมีขนาดเล็กผิดปกติ (< 5%) มุมมองภาพอาจไม่สมบูรณ์")

    if response.image_quality and not response.image_quality.is_acceptable:
        warnings.append("คุณภาพของภาพต่ำกว่าเกณฑ์มาตรฐาน ผลการวิเคราะห์อาจคลาดเคลื่อน")

    # 2. Cross-Agent Malignancy & High-Risk Rules
    has_hcc = any(
        getattr(l, "class_name", "") == "HCC" or getattr(l, "class", "") == "HCC"
        for l in response.lesions
    )
    has_cca = any(
        getattr(l, "class_name", "") == "CCA" or getattr(l, "class", "") == "CCA"
        for l in response.lesions
    )

    if has_hcc or has_cca:
        target_name = "มะเร็งตับชนิดปฐมภูมิ (Hepatocellular Carcinoma / HCC)" if has_hcc else "มะเร็งท่อน้ำดีในตับ (Cholangiocarcinoma / CCA)"
        warnings.append(
            f"🚨 ข้อควรระวังสูงสุด: ตรวจพบรอยโรคต้องสงสัย {target_name} แนะนำส่งตรวจยืนยันด้วย CT Triphasic Liver Protocol หรือ MRI Liver และตรวจระดับซีรั่ม AFP/CA19-9 ด่วน"
        )
        # Elevate fibrosis risk tier and stage to High Risk / F4 if primary hepatic malignancy (HCC) confirmed
        if response.fibrosis:
            if response.fibrosis.risk_tier < 2 or response.fibrosis.stage in ["F0", "F1", "F2"]:
                response.fibrosis.risk_tier = 2
                response.fibrosis.risk_tier_label = "สูง (Cirrhotic Background Risk)"
                response.fibrosis.stage = "F4"
                response.fibrosis.stage_calibrated = "F4"
                response.fibrosis.kpa_estimate = max(response.fibrosis.kpa_estimate, 9.5)
                response.fibrosis.prob_f4 = max(response.fibrosis.prob_f4, 0.65)

    # 3. Severe Steatosis Deep Acoustic Attenuation Note
    if response.fatty_liver_stage == "S3":
        warnings.append("การลดทอนของคลื่นเสียงระดับ S3 อาจบดบังรายละเอียดเนื้อตับส่วนลึกและกะบังลม แนะนำติดตามด้วย CAP/FibroScan")

    if warnings:
        response.clinical_warning = " | ".join(warnings)

    return response
