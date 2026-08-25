"""FastAPI REST API Server for SmartLiva Ultrasound AI & Clinical Workflow.

Production-ready Endpoints:
- POST /analyze                  : Supervisor API 1.1 protocol (Organ Gate + UNet Contour)
- POST /api/v1/agents/fibrosis   : Real Fibrosis Ensemble Staging (F0-F4) + ROI Region
- POST /api/v1/agents/lesion     : Real YOLOv8 7-Class Focal Lesion Detection + Box Regions
- POST /api/v1/agents/steatosis  : Real Hepatic Steatosis (S0-S3) + Acoustic Attenuation ROI
- POST /api/v1/agents/fluke      : Real Liver Fluke & CCA Risk Assessment + Duct Regions
- POST /api/v1/liver/analyze     : Comprehensive Multi-Organ + Multi-Agent Orchestrated Workflow
- POST /api/feedback             : Doctor review & Flywheel SQLite persistence
- GET  /api/feedback/history     : Retrieve recent audited clinical reviews
- GET  /api/samples              : Retrieval of sample ultrasound images for testing
- GET  /api/sample/{path}        : Secure serving of sample ultrasound files
- GET  /api/fibrosis/metrics     : Measured cross-validation metrics and verdict
- GET  /health                   : Health status of all models
"""

import glob
import io
import json
import logging
import os
import sys
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
import torch
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from src.config import (
    BASE_DIR,
    DATA_DIR,
    ESTIMATE_CAVEAT,
    FIBROSIS_ENSEMBLE_PATH,
    FIBROSIS_METRICS_PATH,
    MEDSAM_CKPT,
    MULTIORGAN_SDK_PATH,
    ORGAN_WEIGHTS_PATH,
    SAMPLE_EXTENSIONS,
    SAMPLES_DIR,
    STATIC_DIR,
    YOLO_LESION_PATH,
    YOLO_LIVER_PATH,
    build_confidence_note,
    get_device,
    load_fibrosis_verdict,
)
from src.database.flywheel import get_feedback_history, init_db, save_feedback
from src.models.fibrosis import FIBROSIS_AVAILABLE, load_ensemble, predict_fibrosis
from src.models.gate import assess_quality, classify, load_model as load_organ_gate_model
from src.models.lesion import load_lesion_model, load_liver_box_model
from src.models.segmentation import (
    SegmentationUnavailable,
    anonymize_ultrasound,
    cv2_to_base64,
    predict_multiorgan_segmentation,
)
from src.models.segmentation.medsam2_engine import load_medsam2_predictor
from src.models.segmentation.multiorgan_sdk import load_sdk_model
from src.models.segmentation.seg_contour import (
    contour_of,
    draw as draw_contour_overlay,
    load_seg as load_unet_seg,
    predict_mask as predict_unet_mask,
)
from src.workflow.gatekeeper import run_organ_gatekeeper_harness
from src.workflow.orchestrator import run_clinical_workflow
from src.workflow.schemas import (
    AnalyzeRequest,
    FeedbackRequest,
    PredictionResponse,
    SampleListResponse,
)
from src.workflow.specialists.fatty_liver import evaluate_steatosis
from src.workflow.specialists.fibrosis import evaluate_fibrosis
from src.workflow.specialists.fluke_risk import evaluate_fluke_findings
from src.workflow.specialists.lesion import evaluate_lesions
from src.api.copilot import router as copilot_router

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("SmartLiva.Server")

API_VERSION = "1.1"
MODEL_VERSION = "2.0.0"


class ModelState:
    device: Optional[torch.device] = None
    medsam_predictor: Optional[Any] = None
    seg_model_ready: bool = False
    seg_load_error: Optional[str] = None
    yolo_lesion_model: Optional[Any] = None
    yolo_liver_model: Optional[Any] = None
    multiorgan_model: Optional[Any] = None
    fibrosis_ensemble: Optional[Any] = None
    organ_gate_model: Optional[Any] = None
    organ_classes: Optional[List[str]] = None
    fibrosis_note: str = "โมเดลประเมินพังผืดยังไม่พร้อมใช้งาน"


state = ModelState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for loading and initializing ML models."""
    state.device = get_device()
    logger.info(f"Initializing SmartLiva on target device: {state.device}")

    # 1. Initialize SQLite Database for Flywheel
    init_db()
    logger.info("Initialized Flywheel Feedback Database.")

    # 2. Load Organ Gatekeeper (ResNet18 10-Class)
    try:
        state.organ_gate_model, state.organ_classes = load_organ_gate_model(device=state.device)
        logger.info(f"Successfully loaded Organ Gatekeeper with {len(state.organ_classes or [])} classes.")
    except Exception as err:
        logger.warning(f"Organ Gatekeeper failed to load: {err}")

    # 3. Load UNet / Multi-Organ Segmentation
    try:
        state.multiorgan_model = load_unet_seg(dev=state.device)
        logger.info("Successfully loaded UNet Multi-Organ Segmentation Model.")
    except Exception as err:
        logger.warning(f"UNet Segmentation failed to load: {err}")

    # 4. Load MedSAM2 Predictor (if present)
    try:
        state.medsam_predictor, state.seg_model_ready, state.seg_load_error = load_medsam2_predictor(
            weights_path=MEDSAM_CKPT, device=state.device
        )
    except Exception as err:
        logger.warning(f"MedSAM2 load error: {err}")

    # 5. Load YOLO Lesion Model
    try:
        state.yolo_lesion_model = load_lesion_model(weights_path=YOLO_LESION_PATH)
        logger.info(f"Successfully loaded YOLO Lesion Model from: {YOLO_LESION_PATH}")
    except Exception as err:
        logger.warning(f"YOLO Lesion Model failed to load: {err}")

    # 6. Load YOLO Liver Bounding Box Model
    try:
        state.yolo_liver_model = load_liver_box_model(weights_path=YOLO_LIVER_PATH)
    except Exception as err:
        logger.warning(f"YOLO Liver Box Model failed to load: {err}")

    # 7. Load Fibrosis Ensemble Model
    if FIBROSIS_AVAILABLE and FIBROSIS_ENSEMBLE_PATH.exists():
        try:
            state.fibrosis_ensemble = load_ensemble(FIBROSIS_ENSEMBLE_PATH, state.device)
            state.fibrosis_note = build_confidence_note()
            logger.info(f"Successfully loaded Fibrosis Ensemble from: {FIBROSIS_ENSEMBLE_PATH}")
        except Exception as err:
            logger.error(f"Failed to load Fibrosis Ensemble: {err}")
            state.fibrosis_ensemble = None
    else:
        logger.info(f"Notice: Fibrosis Ensemble checkpoint not found at {FIBROSIS_ENSEMBLE_PATH}.")

    yield
    logger.info("Shutting down SmartLiva server...")


# Initialize FastAPI Application
app = FastAPI(
    title="SmartLiva Medical Vision API",
    description="Production-grade AI System for Liver Ultrasound Segmentation, Lesion Analytics & Clinical Workflow.",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Sub-Routers
app.include_router(copilot_router)


# -------------------------------------------------------------
# Utility Functions
# -------------------------------------------------------------
async def _read_upload_image(file: UploadFile) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Image.Image, int, int]:
    """Read upload file into PIL, RGB, BGR, Gray and dimensions with size check."""
    MAX_UPLOAD_BYTES = 25 * 1024 * 1024
    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 25MB.")
    if not contents:
        raise HTTPException(status_code=400, detail="Empty upload file.")

    pil_img = Image.open(io.BytesIO(contents)).convert("RGB")
    img_np = np.array(pil_img)
    img_np = anonymize_ultrasound(img_np)
    gray_img = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    bgr_img = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    w, h = pil_img.size
    return img_np, bgr_img, gray_img, pil_img, w, h


def _get_liver_mask(img_pil: Image.Image, bgr_img: np.ndarray, gray_img: np.ndarray) -> np.ndarray:
    """Predict liver binary mask using UNet with fan filter or MedSAM2."""
    try:
        unet_mask = predict_unet_mask(img_pil, dev=state.device, use_fan=True)
        return (unet_mask == 1).astype(np.uint8)
    except Exception:
        liver_m, _ = predict_multiorgan_segmentation(
            original_img=bgr_img,
            gray_img=gray_img,
            pil_img=img_pil,
            medsam_predictor=state.medsam_predictor,
            seg_model_ready=state.seg_model_ready,
            device=state.device,
            yolo_liver_model=state.yolo_liver_model,
            multiorgan_model=state.multiorgan_model,
        )
        return liver_m


# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------
@app.get("/health")
@app.get("/api/health")
def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "ok": True,
        "status": "healthy",
        "service": "SmartLiva Medical Vision API",
        "version": MODEL_VERSION,
        "api_version": API_VERSION,
        "device": str(state.device) if state.device else "unknown",
        "models": {
            "organ_gatekeeper": state.organ_gate_model is not None,
            "multiorgan_segmenter": state.multiorgan_model is not None or state.seg_model_ready,
            "yolo_lesion_detector": state.yolo_lesion_model is not None,
            "yolo_liver_prompt": state.yolo_liver_model is not None,
            "fibrosis_ensemble": state.fibrosis_ensemble is not None,
        },
    }


@app.post("/analyze")
async def analyze_supervisor_protocol(
    image: UploadFile = File(...),
    site_id: Optional[str] = Form(""),
    overlay: Optional[str] = Form("false"),
    force_contour: Optional[str] = Form("false"),
    gate_only: Optional[str] = Form("false"),
) -> JSONResponse:
    """Analyze image conforming to the Supervisor API 1.1 contract."""
    t0 = time.perf_counter()
    img_np, bgr_img, gray_img, pil_img, width, height = await _read_upload_image(image)

    # 1. Organ Gatekeeper & Quality
    t_gate_0 = time.perf_counter()
    gate_res = classify(pil_img, device=state.device, filename=image.filename)
    gate_ms = (time.perf_counter() - t_gate_0) * 1000.0

    is_liver = bool(gate_res.get("is_liver_us"))
    want_force = str(force_contour).lower() in ("true", "1", "yes")
    want_gate_only = str(gate_only).lower() in ("true", "1", "yes")
    want_overlay = str(overlay).lower() in ("true", "1", "yes")

    # 2. Contour Segmentation
    contour_res: Dict[str, Any] = {}
    contour_ms = 0.0
    overlay_b64: Optional[str] = None

    if not want_gate_only and (is_liver or want_force):
        t_c_0 = time.perf_counter()
        raw_contours = contour_of(pil_img, classes=(1,))  # Liver only for API 1.1
        contour_ms = (time.perf_counter() - t_c_0) * 1000.0

        liver_polys = raw_contours.get("liver", [])
        if liver_polys:
            polys_json = []
            for p in liver_polys:
                polys_json.append({
                    "outer": [[round(float(x), 1), round(float(y), 1)] for x, y in p["outer"]],
                    "holes": [[[round(float(x), 1), round(float(y), 1)] for x, y in h] for h in p["holes"]],
                    "n_points": len(p["outer"]),
                    "area_px": round(p["area_px"], 1),
                    "area_pct_frame": round(100.0 * p["area_px"] / max(1, width * height), 2),
                    "perimeter_px": round(p["perimeter_px"], 1),
                })
            area_total = sum(p["area_px"] for p in liver_polys)
            pct_total = 100.0 * area_total / max(1, width * height)
            contour_res["liver"] = {
                "found": True,
                "polygons": polys_json,
                "area_px_total": round(area_total, 1),
                "area_pct_frame_total": round(pct_total, 2),
            }
        else:
            contour_res["liver"] = {
                "found": False,
                "polygons": [],
                "area_px_total": 0,
                "area_pct_frame_total": 0,
            }

        if want_overlay and liver_polys:
            drawn_arr = draw_contour_overlay(pil_img, raw_contours)
            _, buf = cv2.imencode(".png", cv2.cvtColor(drawn_arr, cv2.COLOR_RGB2BGR))
            import base64
            overlay_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    else:
        contour_res["liver"] = {
            "found": False,
            "polygons": [],
            "area_px_total": 0,
            "area_pct_frame_total": 0,
        }

    # 3. Warnings
    warnings = []
    if not (site_id or "").strip():
        warnings.append("SCANNER_NOT_CALIBRATED")
    if gate_res.get("confidence") and float(gate_res["confidence"]) < 0.55:
        warnings.append("LOW_CONFIDENCE")
    if want_force:
        warnings.append("FORCED_CONTOUR")

    total_ms = (time.perf_counter() - t0) * 1000.0

    return JSONResponse(content={
        "ok": True,
        "api_version": API_VERSION,
        "model_version": MODEL_VERSION,
        "image": {"name": image.filename or "image.jpg", "width": width, "height": height},
        "verdict": gate_res.get("verdict"),
        "is_liver_us": is_liver,
        "confidence": gate_res.get("confidence"),
        "quality": {
            "status": gate_res.get("quality"),
            "score": gate_res.get("q_score"),
            "reasons": gate_res.get("reasons"),
        },
        "top3": gate_res.get("top3", []),
        "regions": contour_res,
        "overlay_png_base64": overlay_b64,
        "warnings": warnings,
        "timing_ms": {
            "gate": int(round(gate_ms)),
            "contour": int(round(contour_ms)),
            "total": int(round(total_ms)),
        },
    })


# -------------------------------------------------------------
# Specialist Agent Endpoints (Real Inference)
# -------------------------------------------------------------
@app.post("/api/v1/agents/fibrosis")
async def agent_fibrosis_endpoint(
    file: UploadFile = File(...),
    view: Optional[str] = Form(None),
) -> JSONResponse:
    """Execute real Fibrosis Ensemble Staging Agent (F0-F4) with Gatekeeper check."""
    t0 = time.perf_counter()
    img_np, bgr_img, gray_img, pil_img, width, height = await _read_upload_image(file)
    
    gate_verdict = run_organ_gatekeeper_harness(img_np, device=state.device)
    if not gate_verdict.is_liver:
        raise HTTPException(
            status_code=422,
            detail=f"ภาพที่อัปโหลดไม่ใช่อัลตราซาวด์ตับ ({gate_verdict.rejection_reason})",
        )

    mask = _get_liver_mask(pil_img, bgr_img, gray_img)

    result = evaluate_fibrosis(
        fibrosis_ensemble=state.fibrosis_ensemble,
        device=state.device,
        predict_fibrosis_func=predict_fibrosis,
        gray_img=gray_img,
        mask=mask,
        view=view,
        estimate_caveat=ESTIMATE_CAVEAT,
        confidence_note=state.fibrosis_note,
    )
    inference_ms = int(round((time.perf_counter() - t0) * 1000.0))

    return JSONResponse(content={
        "agentId": "fibrosis",
        "value": result["stage"],
        "confidence": result["confidence"],
        "regions": result["regions"],
        "rationale": result["rationale"],
        "kpa": result.get("kpa"),
        "risk_tier": result.get("risk_tier"),
        "modelVersion": f"fibrosis-ensemble-{MODEL_VERSION}",
        "inferenceMs": inference_ms,
        "simulated": False,
    })


@app.post("/api/v1/agents/lesion")
async def agent_lesion_endpoint(
    file: UploadFile = File(...),
    conf_thres: Optional[float] = Form(0.25),
) -> JSONResponse:
    """Execute real YOLOv8 Focal Lesion Detection Agent with Gatekeeper check."""
    t0 = time.perf_counter()
    img_np, bgr_img, gray_img, pil_img, width, height = await _read_upload_image(file)
    
    gate_verdict = run_organ_gatekeeper_harness(img_np, device=state.device)
    if not gate_verdict.is_liver:
        raise HTTPException(
            status_code=422,
            detail=f"ภาพที่อัปโหลดไม่ใช่อัลตราซาวด์ตับ ({gate_verdict.rejection_reason})",
        )

    mask = _get_liver_mask(pil_img, bgr_img, gray_img)

    result = evaluate_lesions(
        yolo_lesion_model=state.yolo_lesion_model,
        img_bgr=bgr_img,
        mask=mask,
        conf_thres=float(conf_thres or 0.25),
    )
    inference_ms = int(round((time.perf_counter() - t0) * 1000.0))

    return JSONResponse(content={
        "agentId": "lesion",
        "value": {"findings": result["findings"]},
        "confidence": result["confidence"],
        "regions": result["regions"],
        "rationale": result["rationale"],
        "modelVersion": f"yolov8-lesion-{MODEL_VERSION}",
        "inferenceMs": inference_ms,
        "simulated": False,
    })


@app.post("/api/v1/agents/steatosis")
async def agent_steatosis_endpoint(
    file: UploadFile = File(...),
) -> JSONResponse:
    """Execute real Hepatic Steatosis (S0-S3) Agent with Gatekeeper check."""
    t0 = time.perf_counter()
    img_np, bgr_img, gray_img, pil_img, width, height = await _read_upload_image(file)
    
    gate_verdict = run_organ_gatekeeper_harness(img_np, device=state.device)
    if not gate_verdict.is_liver:
        raise HTTPException(
            status_code=422,
            detail=f"ภาพที่อัปโหลดไม่ใช่อัลตราซาวด์ตับ ({gate_verdict.rejection_reason})",
        )

    mask = _get_liver_mask(pil_img, bgr_img, gray_img)

    # Detect lesions to find focal fatty change
    lesion_res = evaluate_lesions(state.yolo_lesion_model, bgr_img, mask, conf_thres=0.25)
    result = evaluate_steatosis(bgr_img, gray_img, mask, lesions=lesion_res.get("lesion_infos"))
    inference_ms = int(round((time.perf_counter() - t0) * 1000.0))

    return JSONResponse(content={
        "agentId": "steatosis",
        "value": result["stage"],
        "confidence": result["confidence"],
        "regions": [result["region"]] if result.get("region") else [],
        "rationale": result["rationale"],
        "attenuation_ratio": result.get("attenuation_ratio"),
        "modelVersion": f"steatosis-attenuation-{MODEL_VERSION}",
        "inferenceMs": inference_ms,
        "simulated": False,
    })


@app.post("/api/v1/agents/fluke")
async def agent_fluke_endpoint(
    file: UploadFile = File(...),
    history_json: Optional[str] = Form(None),
) -> JSONResponse:
    """Execute real Liver Fluke / CCA Risk Assessment Agent with Gatekeeper check."""
    t0 = time.perf_counter()
    img_np, bgr_img, gray_img, pil_img, width, height = await _read_upload_image(file)
    
    gate_verdict = run_organ_gatekeeper_harness(img_np, device=state.device)
    if not gate_verdict.is_liver:
        raise HTTPException(
            status_code=422,
            detail=f"ภาพที่อัปโหลดไม่ใช่อัลตราซาวด์ตับ ({gate_verdict.rejection_reason})",
        )

    mask = _get_liver_mask(pil_img, bgr_img, gray_img)

    history = None
    if history_json:
        try:
            history = json.loads(history_json)
        except Exception:
            pass

    result = evaluate_fluke_findings(
        history=history,
        img_bgr=bgr_img,
        gray_img=gray_img,
        mask=mask,
    )
    inference_ms = int(round((time.perf_counter() - t0) * 1000.0))

    return JSONResponse(content={
        "agentId": "fluke",
        "value": result["verdict"],
        "confidence": result["confidence"],
        "regions": result["regions"],
        "rationale": result["rationale"],
        "risk_score": result.get("risk_score"),
        "modelVersion": f"fluke-risk-{MODEL_VERSION}",
        "inferenceMs": inference_ms,
        "simulated": False,
    })


# -------------------------------------------------------------
# Comprehensive Orchestrated Workflow
# -------------------------------------------------------------
@app.post("/api/v1/liver/analyze", response_model=PredictionResponse)
async def analyze_liver_api(
    file: UploadFile = File(...),
    clinical_data: Optional[str] = Form(None),
) -> JSONResponse:
    """Analyze ultrasound image and clinical data via Multi-Organ Orchestrated Workflow."""
    try:
        req = AnalyzeRequest()
        if clinical_data:
            try:
                data_dict = json.loads(clinical_data)
                req = AnalyzeRequest(**data_dict)
            except Exception as e:
                logger.warning(f"Failed to parse clinical_data JSON: {e}")

        img_np, bgr_img, gray_img, pil_img, w, h = await _read_upload_image(file)

        # 1. Run Organ Gatekeeper Harness Guardrail
        gate_verdict = run_organ_gatekeeper_harness(img_np, device=state.device)
        orig_b64: str = cv2_to_base64(bgr_img)

        # Hard-Halt Early if image is not verified liver ultrasound
        if not gate_verdict.is_liver:
            response = await run_clinical_workflow(
                request=req,
                filename=file.filename or "ultrasound_image.jpg",
                img_bgr=bgr_img,
                gray_img=gray_img,
                mask=np.zeros((h, w), dtype=np.uint8),
                yolo_lesion_model=state.yolo_lesion_model,
                fibrosis_ensemble=state.fibrosis_ensemble,
                device=state.device,
                predict_fibrosis_func=predict_fibrosis,
                estimate_caveat=ESTIMATE_CAVEAT,
                confidence_note=state.fibrosis_note,
                orig_b64=orig_b64,
                mask_b64=orig_b64,
                overlay_b64=orig_b64,
                roi_b64=None,
                gallbladder_mask_b64=None,
                gallbladder_detected=False,
                gate_verdict=gate_verdict,
            )
            return JSONResponse(content=response.model_dump())

        # 2. Multi-Organ Segmentation (Liver + Gallbladder)
        liver_mask, gb_mask = predict_multiorgan_segmentation(
            original_img=bgr_img,
            gray_img=gray_img,
            pil_img=pil_img,
            medsam_predictor=state.medsam_predictor,
            seg_model_ready=state.seg_model_ready,
            device=state.device,
            yolo_liver_model=state.yolo_liver_model,
            multiorgan_model=state.multiorgan_model,
        )

        liver_visual: np.ndarray = (liver_mask * 255).astype(np.uint8)
        mask_b64: str = cv2_to_base64(cv2.cvtColor(liver_visual, cv2.COLOR_GRAY2BGR))

        gb_b64: Optional[str] = None
        has_gb: bool = False
        if gb_mask is not None and gb_mask.sum() > 50:
            has_gb = True
            gb_visual: np.ndarray = (gb_mask * 255).astype(np.uint8)
            gb_b64 = cv2_to_base64(cv2.cvtColor(gb_visual, cv2.COLOR_GRAY2BGR))

        default_overlay: np.ndarray = bgr_img.copy()
        default_overlay[liver_mask == 1] = (
            0.55 * default_overlay[liver_mask == 1] + 0.45 * np.array([240, 180, 0])
        ).astype(np.uint8)

        if has_gb and gb_mask is not None:
            default_overlay[gb_mask == 1] = (
                0.40 * default_overlay[gb_mask == 1] + 0.60 * np.array([0, 190, 255])
            ).astype(np.uint8)

        overlay_b64: str = cv2_to_base64(default_overlay)

        response = await run_clinical_workflow(
            request=req,
            filename=file.filename or "ultrasound_image.jpg",
            img_bgr=bgr_img,
            gray_img=gray_img,
            mask=liver_mask,
            yolo_lesion_model=state.yolo_lesion_model,
            fibrosis_ensemble=state.fibrosis_ensemble,
            device=state.device,
            predict_fibrosis_func=predict_fibrosis,
            estimate_caveat=ESTIMATE_CAVEAT,
            confidence_note=state.fibrosis_note,
            orig_b64=orig_b64,
            mask_b64=mask_b64,
            overlay_b64=overlay_b64,
            roi_b64=None,
            gallbladder_mask_b64=gb_b64,
            gallbladder_detected=has_gb,
            gate_verdict=gate_verdict,
        )

        return JSONResponse(content=response.model_dump())

    except SegmentationUnavailable as err:
        logger.error(f"/api/v1/liver/analyze refused: {err}")
        raise HTTPException(
            status_code=503,
            detail="Segmentation model is unavailable. The server cannot analyze images right now.",
        )
    except Exception as err:
        logger.error(f"Error processing image: {err}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Image analysis failed: {err}")


# -------------------------------------------------------------
# Flywheel Feedback Persistence
# -------------------------------------------------------------
@app.post("/api/feedback")
async def submit_feedback(request: Request) -> JSONResponse:
    """Save doctor's verification data and training feedback into SQLite Flywheel."""
    try:
        body = await request.json()
        result = save_feedback(body)
        return JSONResponse(content={"success": True, "message": "Feedback saved successfully", "result": result})
    except Exception as err:
        logger.error(f"Error saving feedback: {err}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to save feedback data.")


@app.get("/api/feedback/history")
def get_feedback_records(limit: int = 50) -> JSONResponse:
    """Retrieve recent audited clinician feedback records."""
    records = get_feedback_history(limit=limit)
    return JSONResponse(content={"count": len(records), "records": records})


# -------------------------------------------------------------
# Samples & Metrics
# -------------------------------------------------------------
@app.get("/api/samples", response_model=SampleListResponse)
def get_sample_images() -> Dict[str, List[Dict[str, str]]]:
    """Retrieve sample ultrasound images available for quick testing."""
    sample_pattern: str = str(DATA_DIR / "**" / "*.jpg")
    found_files: List[str] = sorted(glob.glob(sample_pattern, recursive=True))[:16]

    samples: List[Dict[str, str]] = []
    for f in found_files:
        path_obj = Path(f)
        rel_path: str = str(path_obj.relative_to(BASE_DIR))
        category: str = "Ultrasound"
        if "Normal" in rel_path:
            category = "Normal Liver"
        elif "Benign" in rel_path:
            category = "Benign Lesion"
        elif "Malignant" in rel_path:
            category = "Malignant Lesion"

        samples.append({
            "filename": path_obj.name,
            "rel_path": rel_path,
            "category": category,
        })

    return {"samples": samples}


@app.get("/api/fibrosis/metrics")
def get_fibrosis_metrics() -> JSONResponse:
    """Return measured cross-validation metrics and negative control verdict."""
    if not FIBROSIS_METRICS_PATH.exists():
        raise HTTPException(status_code=404, detail="Fibrosis metrics have not been generated yet.")
    return JSONResponse(content={
        "available": state.fibrosis_ensemble is not None,
        "confidence_note": state.fibrosis_note,
        "metrics": json.loads(FIBROSIS_METRICS_PATH.read_text(encoding="utf-8")),
        "verdict": load_fibrosis_verdict(),
    })


@app.get("/api/sample/{path:path}")
def get_sample_image_file(path: str) -> FileResponse:
    """Serve sample image file by repo-relative path with security guards."""
    full_path: Path = (BASE_DIR / path).resolve()
    try:
        full_path.relative_to(SAMPLES_DIR)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied.")

    if full_path.suffix.lower() not in SAMPLE_EXTENSIONS:
        raise HTTPException(status_code=403, detail="Access denied.")

    if full_path.is_file():
        return FileResponse(str(full_path))
    raise HTTPException(status_code=404, detail="Sample image file not found.")


# -------------------------------------------------------------
# Static Files & SPA Frontend Serving
# -------------------------------------------------------------
STATIC_DIR.mkdir(parents=True, exist_ok=True)
if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index() -> FileResponse:
    """Serve main single-page web UI."""
    index_file: Path = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    raise HTTPException(status_code=404, detail="index.html not found. Please run 'npm run build' in frontend/")


@app.get("/{catchall:path}")
def spa_fallback(catchall: str) -> FileResponse:
    """Fallback handler for SPA client routing."""
    target_file = (STATIC_DIR / catchall).resolve()
    if target_file.is_file() and str(target_file).startswith(str(STATIC_DIR)):
        return FileResponse(str(target_file))
    index_file: Path = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    raise HTTPException(status_code=404, detail="Resource not found.")
