"""Clinical Data Validation & Biomarker Agent (FIB-4, APRI, Lab Safety)."""

import math
from typing import Optional
from src.workflow.schemas import AnalyzeRequest, BiomarkersInfo, LabData, PatientHistory, ValidationInfo


def compute_clinical_biomarkers(
    history: Optional[PatientHistory],
    lab: Optional[LabData],
) -> BiomarkersInfo:
    """Calculate clinical biomarker scores (FIB-4 Index and APRI Score) according to AASLD/EASL guidelines."""
    if not lab or not history:
        return BiomarkersInfo(calculated=False)

    age = history.age
    ast = lab.ast
    alt = lab.alt
    platelets = lab.platelets

    fib4_score: Optional[float] = None
    fib4_risk_tier: Optional[str] = None
    fib4_interpretation: Optional[str] = None
    apri_score: Optional[float] = None
    apri_risk_tier: Optional[str] = None
    calculated = False

    # Calculate FIB-4: (Age * AST) / (Platelets * sqrt(ALT))
    if age and ast and alt and platelets and age > 0 and ast > 0 and alt > 0 and platelets > 0:
        try:
            score = (age * ast) / (platelets * math.sqrt(alt))
            fib4_score = round(score, 2)
            calculated = True

            # Clinical cutoffs based on EASL/AASLD Guidelines
            low_cutoff = 2.0 if age >= 65 else 1.30
            high_cutoff = 2.67

            if fib4_score < low_cutoff:
                fib4_risk_tier = "ความเสี่ยงต่ำ (Low Risk)"
                fib4_interpretation = (
                    f"FIB-4 = {fib4_score:.2f} (< {low_cutoff}) มีโอกาสน้อยมากที่จะมีพังผืดตับระดับรุนแรง "
                    "(High NPV > 90% for Advanced Fibrosis F3-F4)"
                )
            elif fib4_score <= high_cutoff:
                fib4_risk_tier = "ก้ำกึ่ง/ความเสี่ยงปานกลาง (Indeterminate)"
                fib4_interpretation = (
                    f"FIB-4 = {fib4_score:.2f} ({low_cutoff}-{high_cutoff}) อยู่ในเกณฑ์ก้ำกึ่ง "
                    "แนะนำยืนยันด้วยผลอัลตราซาวด์หรือ Transient Elastography (FibroScan)"
                )
            else:
                fib4_risk_tier = "ความเสี่ยงสูง (High Risk)"
                fib4_interpretation = (
                    f"FIB-4 = {fib4_score:.2f} (> {high_cutoff}) บ่งชี้ความเสี่ยงสูงต่อภาวะพังผืดตับรุนแรงหรือตับแข็ง "
                    "(PPV > 80% for F3-F4 Fibrosis / Cirrhosis)"
                )
        except Exception:
            pass

    # Calculate APRI: (AST / AST_ULN) * 100 / Platelets (Assuming AST_ULN = 40 U/L)
    if ast and platelets and ast > 0 and platelets > 0:
        try:
            apri = ((ast / 40.0) * 100.0) / platelets
            apri_score = round(apri, 2)
            calculated = True

            if apri_score < 0.50:
                apri_risk_tier = "ความเสี่ยงต่ำ (Low Risk / < 0.5)"
            elif apri_score <= 1.50:
                apri_risk_tier = "พังผืดระดับมีนัยสำคัญ (Significant Fibrosis / 0.5-1.5)"
            else:
                apri_risk_tier = "สงสัยภาวะตับแข็ง (Probable Cirrhosis / > 1.5)"
        except Exception:
            pass

    return BiomarkersInfo(
        fib4_score=fib4_score,
        fib4_risk_tier=fib4_risk_tier,
        fib4_interpretation=fib4_interpretation,
        apri_score=apri_score,
        apri_risk_tier=apri_risk_tier,
        calculated=calculated,
    )


async def validate_clinical_data(request: AnalyzeRequest) -> ValidationInfo:
    """Validate Lab (AST, ALT, Platelets, Bilirubin, ALP, GGT, AFP, CA 19-9), TE, and Patient History data."""
    warnings = []

    if request.lab:
        if request.lab.ast is not None and request.lab.ast < 0:
            warnings.append("AST value cannot be negative.")
        if request.lab.alt is not None and request.lab.alt < 0:
            warnings.append("ALT value cannot be negative.")
        if request.lab.platelets is not None and request.lab.platelets < 0:
            warnings.append("Platelets count cannot be negative.")
        if request.lab.bilirubin is not None and request.lab.bilirubin < 0:
            warnings.append("Bilirubin value cannot be negative.")
        if request.lab.alp is not None and request.lab.alp < 0:
            warnings.append("ALP value cannot be negative.")
        if request.lab.ggt is not None and request.lab.ggt < 0:
            warnings.append("GGT value cannot be negative.")
        if request.lab.afp is not None and request.lab.afp < 0:
            warnings.append("AFP value cannot be negative.")
        if request.lab.ca19_9 is not None and request.lab.ca19_9 < 0:
            warnings.append("CA 19-9 value cannot be negative.")
        if request.lab.fbs is not None and request.lab.fbs < 0:
            warnings.append("FBS value cannot be negative.")
        if request.lab.hba1c is not None and request.lab.hba1c < 0:
            warnings.append("HbA1c value cannot be negative.")

    if request.te:
        if request.te.stiffness_kpa is not None:
            if request.te.stiffness_kpa < 0:
                warnings.append("TE stiffness (kPa) cannot be negative.")
            elif request.te.stiffness_kpa > 75:
                warnings.append("TE stiffness is unusually high (> 75 kPa). Please verify measurement.")
        if request.te.cap_db_m is not None and request.te.cap_db_m < 0:
            warnings.append("CAP value cannot be negative.")

    if request.history:
        if request.history.age is not None and (request.history.age < 0 or request.history.age > 130):
            warnings.append("Patient age is out of normal range (0-130).")
        if request.history.weight_kg is not None and request.history.weight_kg < 0:
            warnings.append("Weight cannot be negative.")
        if request.history.height_cm is not None and request.history.height_cm < 0:
            warnings.append("Height cannot be negative.")

    is_valid = len(warnings) == 0
    return ValidationInfo(is_valid=is_valid, warnings=warnings)
