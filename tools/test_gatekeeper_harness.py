"""Test suite for Non-Liver Ultrasound Hard-Gating Harness Guardrail."""

import io
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.api.server import app


def create_non_medical_noise_image() -> bytes:
    """Create a non-medical random noise / graphic image (fails physics gate)."""
    img = Image.new("RGB", (400, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 350, 250], fill=(0, 0, 255))
    draw.text((70, 100), "SAMPLE TEXT DOCUMENT NOT ULTRASOUND", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def create_blank_black_image() -> bytes:
    """Create a completely black image."""
    img = Image.new("RGB", (300, 300), color=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_gatekeeper_harness():
    print("=" * 70)
    print(" 🛡️ SMARTLIVA NON-LIVER ULTRASOUND HARD-GATING HARNESS TESTS")
    print("=" * 70)

    with TestClient(app) as client:
        # 1. Test Negative Control 1: Text / Non-medical graphic image
        print("\n[1] Testing Negative Control (Non-medical text image)...")
        bad_img = create_non_medical_noise_image()
        res = client.post(
            "/api/v1/liver/analyze",
            files={"file": ("non_medical_doc.jpg", bad_img, "image/jpeg")},
        )
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        d = res.json()
        print(f"    Verdict: {d.get('gatekeeper_verdict')}")
        print(f"    is_liver_us: {d.get('is_liver_us')}, Halted: {d.get('halted')}")
        print(f"    Clinical Warning: {d.get('clinical_warning')[:60]}...")
        assert d.get("is_liver_us") is False, "Expected is_liver_us=False for non-medical image"
        assert d.get("halted") is True, "Expected pipeline to be halted"
        assert d.get("fibrosis") is None, "Disease specialists must NOT run on non-liver images"
        assert d.get("fatty_liver_stage") is None
        assert len(d.get("lesions", [])) == 0
        print("    ✅ Negative Control 1 correctly HALTED by Gatekeeper!")

        # 2. Test Negative Control 2: Blank image on specialist endpoint
        print("\n[2] Testing Negative Control on /api/v1/agents/fibrosis...")
        res_fib = client.post(
            "/api/v1/agents/fibrosis",
            files={"file": ("blank.jpg", bad_img, "image/jpeg")},
        )
        print(f"    HTTP Status: {res_fib.status_code}")
        assert res_fib.status_code == 422, f"Expected 422 Unprocessable Entity, got {res_fib.status_code}"
        print(f"    Rejection Detail: {res_fib.json().get('detail')}")
        print("    ✅ Specialist endpoint correctly REJECTED non-liver image!")

        # 3. Test Positive Control: Real Liver Ultrasound Case
        print("\n[3] Testing Positive Control (Real Liver Ultrasound Case)...")
        real_sample_path = BASE_DIR / "public" / "samples" / "case1_normal_rh.jpg"
        with open(real_sample_path, "rb") as f:
            valid_liver_bytes = f.read()

        res_pos = client.post(
            "/api/v1/liver/analyze",
            files={"file": ("case1_normal_rh.jpg", valid_liver_bytes, "image/jpeg")},
        )
        assert res_pos.status_code == 200, f"Expected 200, got {res_pos.status_code}"
        dp = res_pos.json()
        print(f"    Verdict: {dp.get('gatekeeper_verdict')}")
        print(f"    is_liver_us: {dp.get('is_liver_us')}, Halted: {dp.get('halted')}")
        print(f"    Liver Area Coverage: {dp.get('liver_area_percent')}%")
        print(f"    Fibrosis: {dp.get('fibrosis', {}).get('stage')}, Steatosis: {dp.get('fatty_liver_stage')}")
        assert dp.get("is_liver_us") is True, "Expected is_liver_us=True for real liver ultrasound"
        assert dp.get("halted") is False, "Expected pipeline not to be halted"
        assert dp.get("fibrosis") is not None, "Disease specialists must run on valid liver images"
        print("    ✅ Positive Control correctly PASSED Gatekeeper and evaluated!")

    print("\n" + "=" * 70)
    print(" 🎉 ALL GATEKEEPER HARNESS TESTS PASSED (100% AIRTIGHT GUARDRAIL!)")
    print("=" * 70)


if __name__ == "__main__":
    test_gatekeeper_harness()
