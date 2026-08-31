"""State Machine Orchestrator for the SmartLiva Clinical Workflow with Hard Organ Gating."""

import asyncio
import logging
from typing import Any, Optional
import numpy as np

from src.workflow.schemas import AnalyzeRequest, PredictionImages, PredictionResponse
from src.workflow.gatekeeper import GatekeeperVerdict
from src.workflow.agents import (
    analyze_image_quality,
    compute_clinical_biomarkers,
    detect_view,
    validate_clinical_data,
)
from src.workflow.specialists import (
    run_lesion_block,
    run_fibrosis_block,
    run_fatty_liver_block,
    run_te_data_block,
    run_fluke_risk_block,
)
from src.workflow.verifiers import (
    run_deterministic_rule_engine,
    run_medical_reviewer_api,
    run_evidence_safety_verifier,
)

logger = logging.getLogger("SmartLiva.Orchestrator")


async def run_clinical_workflow(
    request: AnalyzeRequest,
    filename: str,
    img_bgr: np.ndarray,
    gray_img: np.ndarray,
    mask: np.ndarray,
    yolo_lesion_model: Any,
    fibrosis_ensemble: Any,
    device: Any,
    predict_fibrosis_func: Any,
    estimate_caveat: str,
    confidence_note: str,
    orig_b64: str,
    mask_b64: str,
    overlay_b64: str,
    roi_b64: Optional[str] = None,
    gallbladder_mask_b64: Optional[str] = None,
    gallbladder_detected: bool = False,
    gate_verdict: Optional[GatekeeperVerdict] = None,
) -> PredictionResponse:
    """The central State Machine Orchestrator with strict Non-Liver Ultrasound Hard-Gating."""

    h, w = gray_img.shape
    liver_px: int = int(mask.sum())
    liver_ratio: float = float(liver_px / (h * w))
    liver_percent: float = round(liver_ratio * 100, 2)

    # ---------------------------------------------------------
    # STEP 0: Non-Liver Hard-Gating Harness Guardrail
    # ---------------------------------------------------------
    is_non_liver = gate_verdict is not None and not gate_verdict.is_liver
    insufficient_liver = liver_percent < 5.0

    if is_non_liver or insufficient_liver:
        logger.warning(
            f"⛔ Hard Gatekeeper Halt: is_non_liver={is_non_liver}, liver_percent={liver_percent}%. "
            "Skipping all disease specialist blocks."
        )

        detected_organ = gate_verdict.detected_organ if gate_verdict else "Non-Liver / Unclear"
        rejection_msg = (
            gate_verdict.rejection_reason
            if (gate_verdict and gate_verdict.rejection_reason)
            else f"⛔ ตรวจไม่พบเนื้อตับที่เพียงพอสำหรับการวิเคราะห์ (Liver Coverage {liver_percent}% < 5.0%) โปรดตรวจสอบว่าเป็นภาพอัลตราซาวด์ตับหรือไม่"
        )

        halted_response = PredictionResponse(
            success=True,
            filename=filename,
            width=w,
            height=h,
            is_liver_us=False,
            halted=True,
            gatekeeper_verdict=gate_verdict.verdict if gate_verdict else "REJECTED_LOW_COVERAGE",
            gatekeeper_organ=detected_organ,
            gatekeeper_confidence=gate_verdict.confidence if gate_verdict else 0.0,
            liver_detected=bool(liver_px > 0),
            liver_area_px=liver_px,
            liver_area_ratio=round(liver_ratio, 4),
            liver_area_percent=liver_percent,
            gallbladder_detected=gallbladder_detected,
            organs_detected=[detected_organ],
            lesion_detection_available=yolo_lesion_model is not None,
            num_lesions=0,
            lesions=[],
            fibrosis=None,
            fatty_liver_stage=None,
            te_data_processed=None,
            fluke_risk=None,
            clinical_warning=rejection_msg,
            clinical_report=(
                f"ข้อสรุปความเห็นแพทย์ (Clinical Safety Rejection):\n"
                f"• สถานะ: ⛔ ระบบยุติการประเมินโรคอัตโนมัติ (Halted by Gatekeeper Guardrail)\n"
                f"• เหตุผล: {rejection_msg}\n"
                f"• ข้อควรปฏิบัติ: เพื่อความปลอดภัยทางการแพทย์ ระบบ SmartLiva จะไม่ประเมินค่าพังผืด ไขมัน หรือตรวจจับมะเร็งบนภาพที่ไม่ใช่อัลตราซาวด์ตับ โปรดอัปโหลดภาพ B-mode Liver Ultrasound ใหม่"
            ),
            safety_verified=True,
            images=PredictionImages(
                original=orig_b64,
                mask=mask_b64,
                gallbladder_mask=gallbladder_mask_b64,
                default_overlay=overlay_b64,
                roi=roi_b64,
            ),
        )
        return halted_response

    # ---------------------------------------------------------
    # STEP 1: Pre-processing Agents (Parallel)
    # ---------------------------------------------------------
    logger.info("Executing Pre-processing Agents...")
    quality_task = asyncio.create_task(analyze_image_quality(img_bgr))
    validation_task = asyncio.create_task(validate_clinical_data(request))
    view_task = asyncio.create_task(detect_view(img_bgr, request.view))

    image_quality, data_validation, view_detection = await asyncio.gather(
        quality_task, validation_task, view_task
    )

    # Compute Clinical Biomarkers (FIB-4 Index & APRI Score)
    biomarkers_info = compute_clinical_biomarkers(request.history, request.lab)

    # ---------------------------------------------------------
    # STEP 2: Specialist Blocks (Parallel - Only for verified liver)
    # ---------------------------------------------------------
    logger.info("Executing Parallel Specialist Blocks on verified liver tissue...")
    lesion_task = asyncio.create_task(
        run_lesion_block(yolo_lesion_model, img_bgr, mask, request.conf_thres)
    )

    effective_view = (
        view_detection.detected_view
        if view_detection and view_detection.detected_view != "Unknown/Not Confident"
        else request.view
    )
    fibrosis_task = asyncio.create_task(
        run_fibrosis_block(
            fibrosis_ensemble,
            device,
            predict_fibrosis_func,
            gray_img,
            mask,
            effective_view,
            estimate_caveat,
            confidence_note,
        )
    )
    te_data_task = asyncio.create_task(run_te_data_block(request.te))
    fluke_risk_task = asyncio.create_task(
        run_fluke_risk_block(request.history, img_bgr=img_bgr, gray_img=gray_img, mask=mask, lab=request.lab)
    )

    lesions_list, has_low_confidence = await lesion_task
    fatty_liver_task = asyncio.create_task(
        run_fatty_liver_block(lesions_list, request.lab, img_bgr=img_bgr, gray_img=gray_img, mask=mask)
    )

    fibrosis_info, roi_bbox = await fibrosis_task
    te_data_processed = await te_data_task
    fluke_risk_info = await fluke_risk_task
    fatty_liver_stage = await fatty_liver_task

    # ---------------------------------------------------------
    # Data Assembly
    # ---------------------------------------------------------
    organs_list = ["Liver"]
    if gallbladder_detected:
        organs_list.append("Gallbladder")

    response = PredictionResponse(
        success=True,
        filename=filename,
        width=w,
        height=h,
        is_liver_us=True,
        halted=False,
        gatekeeper_verdict="liver",
        gatekeeper_organ="Liver",
        gatekeeper_confidence=gate_verdict.confidence if gate_verdict else 0.95,
        image_quality=image_quality,
        data_validation=data_validation,
        view_detection=view_detection,
        liver_detected=True,
        liver_area_px=liver_px,
        liver_area_ratio=round(liver_ratio, 4),
        liver_area_percent=liver_percent,
        gallbladder_detected=gallbladder_detected,
        organs_detected=organs_list,
        lesion_detection_available=yolo_lesion_model is not None,
        num_lesions=len(lesions_list),
        lesions=lesions_list,
        fibrosis=fibrosis_info,
        fatty_liver_stage=fatty_liver_stage,
        te_data_processed=te_data_processed,
        fluke_risk=fluke_risk_info,
        biomarkers=biomarkers_info,
        patient_history=request.history,
        lab_data=request.lab,
        low_confidence_warning=has_low_confidence,
        images=PredictionImages(
            original=orig_b64,
            mask=mask_b64,
            gallbladder_mask=gallbladder_mask_b64,
            default_overlay=overlay_b64,
            roi=roi_b64,
        ),
    )

    # ---------------------------------------------------------
    # STEP 3: Post-processing Verifiers (Sequential Pipeline)
    # ---------------------------------------------------------
    logger.info("Executing Safety Verifiers & AI Medical Reviewer...")
    response = await run_deterministic_rule_engine(response)
    response = await run_medical_reviewer_api(response)
    response = await run_evidence_safety_verifier(response)

    logger.info("Orchestrated Workflow Completed Successfully.")
    return response
