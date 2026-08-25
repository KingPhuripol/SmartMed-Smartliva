"""Clinical Data Validation Agent."""

from src.workflow.schemas import AnalyzeRequest, ValidationInfo


async def validate_clinical_data(request: AnalyzeRequest) -> ValidationInfo:
    """Validate Lab (AST, ALT, Platelets, Bilirubin), TE, and Patient History data."""
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

    if request.te:
        if request.te.stiffness_kpa is not None:
            if request.te.stiffness_kpa < 0:
                warnings.append("TE stiffness (kPa) cannot be negative.")
            elif request.te.stiffness_kpa > 75:
                warnings.append("TE stiffness is unusually high (> 75 kPa). Please verify measurement.")

    is_valid = len(warnings) == 0
    return ValidationInfo(is_valid=is_valid, warnings=warnings)
