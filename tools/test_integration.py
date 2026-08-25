"""Integration test script for SmartLiva unified backend and models."""

import io
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

# Ensure root in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.api.server import app


def create_dummy_ultrasound_image() -> io.BytesIO:
    """Generate a valid synthetic B-mode ultrasound image for testing."""
    img = Image.new("RGB", (640, 480), color=(10, 10, 15))
    draw = ImageDraw.Draw(img)
    # Draw sector fan
    draw.pieslice([(50, 20), (590, 460)], start=30, end=150, fill=(80, 85, 90))
    # Draw liver echotexture
    draw.ellipse([(180, 120), (460, 360)], fill=(110, 115, 120))
    # Draw a simulated cyst
    draw.ellipse([(280, 200), (330, 250)], fill=(20, 20, 25))

    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


def run_tests():
    print("==================================================")
    print(" 🧪 Running SmartLiva Unified Integration Tests")
    print("==================================================")

    with TestClient(app) as client:
        # 1. Health Check
        print("\n[1] Testing GET /health...")
        res = client.get("/health")
        assert res.status_code == 200, f"Health check failed: {res.text}"
        health = res.json()
        print(f"    ✅ Status: {health['status']}, Models: {health['models']}")

        # 2. Sample ultrasound image
        sample_buf = create_dummy_ultrasound_image()
        sample_bytes = sample_buf.getvalue()

        # Load real liver ultrasound sample for specialist agent tests
        real_sample_path = BASE_DIR / "public" / "samples" / "case1_normal_rh.jpg"
        if real_sample_path.exists():
            with open(real_sample_path, "rb") as f:
                real_liver_bytes = f.read()
        else:
            real_liver_bytes = sample_bytes

        # 3. Supervisor /analyze endpoint
        print("\n[2] Testing POST /analyze (Supervisor API 1.1)...")
        res = client.post(
            "/analyze",
            files={"image": ("test_us.jpg", sample_bytes, "image/jpeg")},
            data={"site_id": "HOSPITAL_UDON_01", "overlay": "true"},
        )
        assert res.status_code == 200, f"/analyze failed: {res.text}"
        analyze_data = res.json()
        print(f"    ✅ Verdict: {analyze_data.get('verdict')}, is_liver_us: {analyze_data.get('is_liver_us')}")
        print(f"    ✅ Liver Found: {analyze_data.get('regions', {}).get('liver', {}).get('found')}")
        print(f"    ✅ Timing: {analyze_data.get('timing_ms')}")

        # 4. Fibrosis Agent Endpoint
        print("\n[3] Testing POST /api/v1/agents/fibrosis...")
        res = client.post(
            "/api/v1/agents/fibrosis",
            files={"file": ("case1_normal_rh.jpg", real_liver_bytes, "image/jpeg")},
        )
        assert res.status_code == 200, f"Fibrosis agent failed: {res.text}"
        fib_data = res.json()
        print(f"    ✅ Fibrosis Stage: {fib_data['value']}, Confidence: {fib_data['confidence']}")
        print(f"    ✅ Rationale: {fib_data['rationale']}")
        assert fib_data["simulated"] is False, "Agent should not be simulated"

        # 5. Lesion Agent Endpoint
        print("\n[4] Testing POST /api/v1/agents/lesion...")
        res = client.post(
            "/api/v1/agents/lesion",
            files={"file": ("case1_normal_rh.jpg", real_liver_bytes, "image/jpeg")},
            data={"conf_thres": "0.20"},
        )
        assert res.status_code == 200, f"Lesion agent failed: {res.text}"
        les_data = res.json()
        print(f"    ✅ Lesion Findings: {len(les_data['value']['findings'])} detected")
        print(f"    ✅ Rationale: {les_data['rationale']}")
        assert les_data["simulated"] is False, "Agent should not be simulated"

        # 6. Steatosis Agent Endpoint
        print("\n[5] Testing POST /api/v1/agents/steatosis...")
        res = client.post(
            "/api/v1/agents/steatosis",
            files={"file": ("case1_normal_rh.jpg", real_liver_bytes, "image/jpeg")},
        )
        assert res.status_code == 200, f"Steatosis agent failed: {res.text}"
        stea_data = res.json()
        print(f"    ✅ Steatosis Stage: {stea_data['value']}, Confidence: {stea_data['confidence']}")
        print(f"    ✅ Rationale: {stea_data['rationale']}")
        assert stea_data["simulated"] is False, "Agent should not be simulated"

        # 7. Fluke Agent Endpoint
        print("\n[6] Testing POST /api/v1/agents/fluke...")
        res = client.post(
            "/api/v1/agents/fluke",
            files={"file": ("case1_normal_rh.jpg", real_liver_bytes, "image/jpeg")},
            data={"history_json": json.dumps({"raw_fish_consumption": True})},
        )
        assert res.status_code == 200, f"Fluke agent failed: {res.text}"
        fluke_data = res.json()
        print(f"    ✅ Fluke Result: {fluke_data['value']}, Confidence: {fluke_data['confidence']}")
        print(f"    ✅ Rationale: {fluke_data['rationale']}")
        assert fluke_data["simulated"] is False, "Agent should not be simulated"

        # 8. Flywheel Feedback Submission
        print("\n[7] Testing POST /api/feedback (SQLite Flywheel)...")
        feedback_payload = {
            "studyId": "SL-TEST-001",
            "intake": {
                "fileName": "test_us.jpg",
                "source": "data:image/jpeg;base64,aW1hZ2VkYXRh",
            },
            "review": {
                "verdicts": {
                    "fibrosis": {"agentId": "fibrosis", "verdict": "correct"},
                    "steatosis": {"agentId": "steatosis", "verdict": "correct"},
                    "lesion": {"agentId": "lesion", "verdict": "correct"},
                    "fluke": {"agentId": "fluke", "verdict": "correct"},
                },
                "annotations": [],
                "events": [],
                "settled": True,
            },
        }
        res = client.post("/api/feedback", json=feedback_payload)
        assert res.status_code == 200, f"Flywheel feedback failed: {res.text}"
        fb_res = res.json()
        print(f"    ✅ Flywheel Saved Result: {fb_res}")

        # 9. Verify History
        res = client.get("/api/feedback/history")
        assert res.status_code == 200
        hist = res.json()
        print(f"    ✅ Flywheel Audited Records Count: {hist['count']}")

        # 10. Sample Images endpoint
        print("\n[8] Testing GET /api/samples...")
        res = client.get("/api/samples")
        assert res.status_code == 200
        samples_data = res.json()
        print(f"    ✅ Samples Count: {len(samples_data['samples'])}")

        # 11. Full Multi-Organ Orchestrated Workflow
        print("\n[9] Testing POST /api/v1/liver/analyze...")
        res = client.post(
            "/api/v1/liver/analyze",
            files={"file": ("case1_normal_rh.jpg", real_liver_bytes, "image/jpeg")},
        )
        assert res.status_code == 200, f"/api/v1/liver/analyze failed: {res.text}"
        full_data = res.json()
        print(f"    ✅ Full Workflow Liver Detected: {full_data.get('liver_detected')}")
        print(f"    ✅ Organs Detected: {full_data.get('organs_detected')}")

        # 12. Medical Copilot Endpoint
        print("\n[10] Testing POST /api/v1/copilot/chat...")
        copilot_payload = {
            "study_context": {
                "fibrosis": "F2",
                "steatosis": "S2",
                "lesions": [{"class": "Cyst", "size_mm": 12.5}],
            },
            "messages": [{"role": "user", "content": "คนไข้มีก้อน cyst 1.2 cm และพังผืด F2 ควรวางแผนติดตามอย่างไร?"}],
            "question": "คนไข้มีก้อน cyst 1.2 cm และพังผืด F2 ควรวางแผนติดตามอย่างไร?",
        }
        res = client.post("/api/v1/copilot/chat", json=copilot_payload)
        assert res.status_code == 200, f"Copilot chat failed: {res.text}"
        copilot_data = res.json()
        print(f"    ✅ Copilot Reply preview: {copilot_data.get('reply')[:80]}...")

        # 13. SPA Frontend Index
        print("\n[11] Testing GET / (React SPA Frontend)...")
        res = client.get("/")
        assert res.status_code == 200
        assert (
            "SmartLiva" in res.text
            or '<div id="root">' in res.text
            or "doctype html" in res.text.lower()
        )
        print("    ✅ React SPA Frontend successfully served at /")

        # 14. Non-Liver Ultrasound Hard-Gating Harness Guardrail
        print("\n[12] Testing Non-Liver Ultrasound Hard-Gating Guardrail...")
        bad_img = Image.new("RGB", (300, 300), color=(255, 255, 255))
        draw = ImageDraw.Draw(bad_img)
        draw.text((20, 50), "NON ULTRASOUND TEST", fill=(0, 0, 0))
        bad_buf = io.BytesIO()
        bad_img.save(bad_buf, format="JPEG")
        bad_bytes = bad_buf.getvalue()

        res_bad = client.post(
            "/api/v1/liver/analyze",
            files={"file": ("non_liver_doc.jpg", bad_bytes, "image/jpeg")},
        )
        assert res_bad.status_code == 200
        d_bad = res_bad.json()
        assert d_bad.get("is_liver_us") is False, "Expected is_liver_us=False for non-liver image"
        assert d_bad.get("halted") is True, "Expected workflow to be halted"
        assert d_bad.get("fibrosis") is None, "Disease models must NOT run on non-liver image"
        assert d_bad.get("fatty_liver_stage") is None
        assert len(d_bad.get("lesions", [])) == 0
        print(f"    ✅ Non-Liver Gatekeeper Guardrail correctly halted disease models ({d_bad.get('gatekeeper_verdict')})")

    print("\n" + "=" * 50)
    print(" 🎉 ALL 14 INTEGRATION TESTS PASSED (10,000% COMPLETE!)")
    print("==================================================")


if __name__ == "__main__":
    run_tests()
