"""Data schemas for SmartLiva requests, responses, and clinical agent pipelines."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# --- Clinical Input Schemas ---

class LabData(BaseModel):
    ast: Optional[float] = Field(None, description="Aspartate Aminotransferase (U/L)")
    alt: Optional[float] = Field(None, description="Alanine Aminotransferase (U/L)")
    platelets: Optional[float] = Field(None, description="Platelet count (10^9/L)")
    bilirubin: Optional[float] = Field(None, description="Total Bilirubin (mg/dL)")


class TEData(BaseModel):
    stiffness_kpa: Optional[float] = Field(None, description="Liver stiffness measured by Transient Elastography (kPa)")
    cap_db_m: Optional[float] = Field(None, description="Controlled Attenuation Parameter (dB/m)")


class PatientHistory(BaseModel):
    age: Optional[int] = Field(None, description="Patient age")
    gender: Optional[str] = Field(None, description="M or F")
    hbv_positive: Optional[bool] = Field(None, description="Hepatitis B positive")
    hcv_positive: Optional[bool] = Field(None, description="Hepatitis C positive")
    alcohol_history: Optional[bool] = Field(None, description="Significant alcohol consumption history")
    raw_fish_consumption: Optional[bool] = Field(None, description="History of raw fish consumption (Fluke risk factor)")


class AnalyzeRequest(BaseModel):
    view: Optional[str] = Field(None, description="Ultrasound view (e.g., RH, GBH, LHA, LHP, SPH, LHV, FPH)")
    conf_thres: float = 0.25
    img_size: int = 256
    lab: Optional[LabData] = None
    te: Optional[TEData] = None
    history: Optional[PatientHistory] = None


# --- Output Data Models ---

class LesionInfo(BaseModel):
    class_name: str = Field(..., alias="class", description="Lesion classification name")
    confidence: float = Field(..., description="Detection confidence score")
    bbox: List[int] = Field(..., description="Bounding box coordinates [x1, y1, x2, y2]")
    inside_liver: bool = Field(..., description="Whether lesion center falls inside liver region")

    class Config:
        populate_by_name = True


class PredictionImages(BaseModel):
    original: str = Field(..., description="Base64 encoded original image")
    mask: str = Field(..., description="Base64 encoded binary mask (Liver)")
    gallbladder_mask: Optional[str] = Field(None, description="Base64 encoded binary mask (Gallbladder)")
    default_overlay: str = Field(..., description="Base64 encoded color overlay")
    roi: Optional[str] = Field(None, description="Base64 encoded liver ROI actually fed to the fibrosis model")


class FibrosisInfo(BaseModel):
    risk_tier: int = Field(..., description="0 = low, 1 = moderate, 2 = high")
    risk_tier_label: str = Field(..., description="Human-readable tier label")
    tier_observed_ge_f2: Optional[float] = Field(None, description="Observed >=F2 rate among held-out exams in this tier")
    tier_observed_ge_f3: Optional[float] = Field(None, description="Observed >=F3 rate among held-out exams in this tier")
    tier_observed_f4: Optional[float] = Field(None, description="Observed F4 rate among held-out exams in this tier")
    tier_n_reference_exams: Optional[int] = Field(None, description="Held-out exams that landed in this tier")

    prob_ge_f2: float = Field(..., description="Probability of significant fibrosis (>=F2)")
    prob_ge_f3: float = Field(..., description="Probability of advanced fibrosis (>=F3)")
    prob_f4: float = Field(..., description="Probability of cirrhosis (F4)")

    stage: str = Field(..., description="Stage implied by the compressed kPa estimate -- not a diagnosis")
    stage_index: int = Field(..., description="Ordinal stage index 0-4")
    stage_calibrated: str = Field(..., description="Stage using cutoffs recalibrated on inner folds")
    kpa_estimate: float = Field(..., description="Compressed stiffness score, NOT a measurement")
    estimate_caveat: str = Field(..., description="Why the kPa figure and stage must not be read as a measurement")

    confidence_note: str = Field(..., description="Measured performance and limitations, from reports/metrics.json")
    roi_bbox: Optional[List[int]] = Field(None, description="Liver ROI the model was shown [x1, y1, x2, y2]")
    n_models: int = Field(..., description="Number of fold checkpoints averaged")


class FlukeRiskInfo(BaseModel):
    risk_level: str = Field(..., description="Low, Moderate, High")
    risk_score: float = Field(..., description="0.0 to 1.0 probability")
    factors: List[str] = Field(..., description="Risk factors contributing to the score")


class ImageQualityInfo(BaseModel):
    score: float = Field(..., description="0.0 to 1.0 overall quality score")
    is_acceptable: bool = Field(..., description="Whether the image quality is acceptable for analysis")
    brightness_level: str = Field(..., description="Dark, Normal, Bright")
    warnings: List[str] = Field(default_factory=list, description="Specific quality warnings")


class ValidationInfo(BaseModel):
    is_valid: bool = Field(..., description="Whether the provided clinical data is valid")
    warnings: List[str] = Field(default_factory=list, description="Data validation warnings")


class ViewDetectionInfo(BaseModel):
    detected_view: str = Field(..., description="The predicted view (e.g., Right Lobe, Left Lobe, Unknown)")
    confidence: float = Field(..., description="Confidence of the view detection")


class PredictionResponse(BaseModel):
    success: bool = True
    filename: str
    width: int
    height: int

    # Pre-processing Agent Outputs
    image_quality: Optional[ImageQualityInfo] = None
    data_validation: Optional[ValidationInfo] = None
    view_detection: Optional[ViewDetectionInfo] = None

    # Multi-Organ & Mask Info
    is_liver_us: bool = True
    halted: bool = False
    gatekeeper_verdict: Optional[str] = None
    gatekeeper_organ: Optional[str] = None
    gatekeeper_confidence: Optional[float] = None
    liver_detected: bool
    liver_area_px: int
    liver_area_ratio: float
    liver_area_percent: float
    gallbladder_detected: bool = False
    organs_detected: List[str] = Field(default_factory=lambda: ["Liver"])

    # Specialist Outputs
    lesion_detection_available: bool
    num_lesions: int
    lesions: List[LesionInfo]
    fibrosis: Optional[FibrosisInfo] = None
    fatty_liver_stage: Optional[str] = Field("S0", description="Fatty Liver S-Stage (S0-S3)")
    te_data_processed: Optional[Dict[str, Any]] = None
    fluke_risk: Optional[FlukeRiskInfo] = None

    # Reviewer Output
    clinical_report: Optional[str] = None

    # Post-processing Outputs
    low_confidence_warning: bool = Field(False, description="True if any detected lesion has confidence below 0.60")
    clinical_warning: Optional[str] = Field(None, description="Warning message if clinical rules are violated")
    safety_verified: bool = Field(False, description="Whether output passed Evidence & Safety Verifier")

    images: PredictionImages


class FeedbackRequest(BaseModel):
    filename: str
    original_image: str  # Base64 string
    ai_prediction: Dict[str, Any]
    status: str  # 'Approve', 'Edit', 'Reject'
    doctor_note: Optional[str] = ""
    doctor_label: Optional[Dict[str, Any]] = None


class SampleItem(BaseModel):
    filename: str
    rel_path: str
    category: str


class SampleListResponse(BaseModel):
    samples: List[SampleItem]
