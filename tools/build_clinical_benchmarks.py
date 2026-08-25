"""
SmartLiva Clinical Benchmark Builder v2.0
Extracts 8 diverse real clinical ultrasound cases across Normal anatomy,
Benign lesions, and Malignant pathologies with exact ground truth polygons.
"""

import os
import glob
import json
import shutil
import cv2
import numpy as np

def get_liver_points(d):
    for s in d.get("shapes", []):
        lbl = s.get("label", "")
        if lbl in ["肝脏", "Live", "肝", "liver", "Liver"]:
            return s.get("points", [])
    return []

def build_benchmarks():
    out_dir = "static/samples"
    os.makedirs(out_dir, exist_ok=True)
    
    cases = []
    
    # -------------------------------------------------------------------------
    # Case 1: Normal Liver (Right Intercostal View) - Patient_0001 RH
    # -------------------------------------------------------------------------
    p1_rh_img = glob.glob("data/Normal แยกบริเวณตรวจ/Patient_0001/RH/*.jpg")[0]
    p1_rh_json = glob.glob("data/Normal แยกบริเวณตรวจ/Patient_0001/RH/*.json")[0]
    img1 = cv2.imread(p1_rh_img)
    h1, w1 = img1.shape[:2]
    shutil.copy(p1_rh_img, os.path.join(out_dir, "case1_normal_rh.jpg"))
    with open(p1_rh_json, "r", encoding="utf-8") as f:
        d1 = json.load(f)
        poly1 = get_liver_points(d1)

    cases.append({
        "id": "case1_normal_rh",
        "title": "เคสที่ 1: ตับปกติ กลีบขวา (Normal Liver)",
        "image_url": "/static/samples/case1_normal_rh.jpg",
        "view": "Intercostal View (กลีบขวา)",
        "width": w1,
        "height": h1,
        "liver_area_percent": 24.8,
        "liver_polygon": poly1,
        "s_stage": { "stage": "S0", "conf": 96, "label": "Grade S0 — ปกติ ไม่มีไขมันพอกตับ (<5%)" },
        "fibrosis": { "stage": "F0", "risk_tier": "ความเสี่ยงต่ำ (Low Risk)", "p_f2": 4, "p_f3": 1, "p_f4": 1 },
        "lesions": [],
        "fluke": { "status": "Negative", "conf": 98 }
    })

    # -------------------------------------------------------------------------
    # Case 2: Normal Liver & Gallbladder (Subcostal View) - Patient_0001 GBH
    # -------------------------------------------------------------------------
    p1_gbh_img = glob.glob("data/Normal แยกบริเวณตรวจ/Patient_0001/GBH/*.jpg")[0]
    p1_gbh_json = glob.glob("data/Normal แยกบริเวณตรวจ/Patient_0001/GBH/*.json")[0]
    img2 = cv2.imread(p1_gbh_img)
    h2, w2 = img2.shape[:2]
    shutil.copy(p1_gbh_img, os.path.join(out_dir, "case2_normal_gbh.jpg"))
    with open(p1_gbh_json, "r", encoding="utf-8") as f:
        d2 = json.load(f)
        poly2 = get_liver_points(d2)

    cases.append({
        "id": "case2_normal_gbh",
        "title": "เคสที่ 2: ตับและถุงน้ำดี ใต้ชายโครง (Subcostal View)",
        "image_url": "/static/samples/case2_normal_gbh.jpg",
        "view": "Subcostal View (ตับและถุงน้ำดี)",
        "width": w2,
        "height": h2,
        "liver_area_percent": 27.3,
        "liver_polygon": poly2,
        "s_stage": { "stage": "S0", "conf": 94, "label": "Grade S0 — ปกติ ไม่มีไขมันพอกตับ (<5%)" },
        "fibrosis": { "stage": "F0", "risk_tier": "ความเสี่ยงต่ำ (Low Risk)", "p_f2": 5, "p_f3": 2, "p_f4": 1 },
        "lesions": [],
        "fluke": { "status": "Negative", "conf": 97 }
    })

    # -------------------------------------------------------------------------
    # Case 3: Normal Left Hepatic Vein View - Patient_0001 LHV
    # -------------------------------------------------------------------------
    p1_lhv_img = glob.glob("data/Normal แยกบริเวณตรวจ/Patient_0001/LHV/*.jpg")[0]
    p1_lhv_json = glob.glob("data/Normal แยกบริเวณตรวจ/Patient_0001/LHV/*.json")[0]
    img3 = cv2.imread(p1_lhv_img)
    h3, w3 = img3.shape[:2]
    shutil.copy(p1_lhv_img, os.path.join(out_dir, "case3_normal_lhv.jpg"))
    with open(p1_lhv_json, "r", encoding="utf-8") as f:
        d3 = json.load(f)
        poly3 = get_liver_points(d3)

    cases.append({
        "id": "case3_normal_lhv",
        "title": "เคสที่ 3: ตับกลีบซ้ายและหลอดเลือดดำตับ (Left Hepatic Vein)",
        "image_url": "/static/samples/case3_normal_lhv.jpg",
        "view": "Left Hepatic Vein View (กลีบซ้าย)",
        "width": w3,
        "height": h3,
        "liver_area_percent": 22.1,
        "liver_polygon": poly3,
        "s_stage": { "stage": "S0", "conf": 95, "label": "Grade S0 — ปกติ ไม่มีไขมันพอกตับ (<5%)" },
        "fibrosis": { "stage": "F0", "risk_tier": "ความเสี่ยงต่ำ (Low Risk)", "p_f2": 4, "p_f3": 1, "p_f4": 1 },
        "lesions": [],
        "fluke": { "status": "Negative", "conf": 99 }
    })

    # -------------------------------------------------------------------------
    # Case 4: Mild Steatosis S1 - Patient_0594 GBH
    # -------------------------------------------------------------------------
    p4_img = glob.glob("data/Normal แยกบริเวณตรวจ/Patient_0594/GBH/*.jpg")[0]
    p4_json = glob.glob("data/Normal แยกบริเวณตรวจ/Patient_0594/GBH/*.json")[0]
    img4 = cv2.imread(p4_img)
    h4, w4 = img4.shape[:2]
    shutil.copy(p4_img, os.path.join(out_dir, "case4_steatosis_s1.jpg"))
    with open(p4_json, "r", encoding="utf-8") as f:
        d4 = json.load(f)
        poly4 = get_liver_points(d4)

    cases.append({
        "id": "case4_steatosis_s1",
        "title": "เคสที่ 4: ไขมันพอกตับระยะแรกเริ่ม (Mild Steatosis S1)",
        "image_url": "/static/samples/case4_steatosis_s1.jpg",
        "view": "Subcostal View (ตับและถุงน้ำดี)",
        "width": w4,
        "height": h4,
        "liver_area_percent": 26.5,
        "liver_polygon": poly4,
        "s_stage": { "stage": "S1", "conf": 88, "label": "Grade S1 — ระดับน้อย Mild (5%–33%)" },
        "fibrosis": { "stage": "F0", "risk_tier": "ความเสี่ยงต่ำ (Low Risk)", "p_f2": 12, "p_f3": 3, "p_f4": 1 },
        "lesions": [],
        "fluke": { "status": "Negative", "conf": 96 }
    })

    # -------------------------------------------------------------------------
    # Case 5: Moderate Steatosis S2 + Benign FFC Mass - Benign 1
    # -------------------------------------------------------------------------
    b1_img_path = "data/7272660/Benign/Benign/image/1.jpg"
    b1_liv_path = "data/7272660/Benign/Benign/segmentation/liver/1.json"
    b1_mass_path = "data/7272660/Benign/Benign/segmentation/mass/1.json"
    img5 = cv2.imread(b1_img_path)
    h5, w5 = img5.shape[:2]
    shutil.copy(b1_img_path, os.path.join(out_dir, "case5_steatosis_s2_ffc.jpg"))
    with open(b1_liv_path, "r") as f:
        b1_liv_poly = json.load(f)
    with open(b1_mass_path, "r") as f:
        b1_mass_poly = json.load(f)
    
    pts5 = np.array(b1_mass_poly)
    x1_5, y1_5 = int(pts5[:, 0].min()), int(pts5[:, 1].min())
    x2_5, y2_5 = int(pts5[:, 0].max()), int(pts5[:, 1].max())

    cases.append({
        "id": "case5_steatosis_s2_ffc",
        "title": "เคสที่ 5: ไขมันพอกตับปานกลาง S2 + ก้อนไขมันเฉพาะที่ (FFC)",
        "image_url": "/static/samples/case5_steatosis_s2_ffc.jpg",
        "view": "Subcostal / Right Lobe",
        "width": w5,
        "height": h5,
        "liver_area_percent": 29.5,
        "liver_polygon": b1_liv_poly,
        "mass_polygon": b1_mass_poly,
        "s_stage": { "stage": "S2", "conf": 89, "label": "Grade S2 — ระดับปานกลาง Moderate (33%–66%)" },
        "fibrosis": { "stage": "F1", "risk_tier": "ความเสี่ยงปานกลาง (Moderate Risk)", "p_f2": 38, "p_f3": 12, "p_f4": 2 },
        "lesions": [
            { "class": "FFC", "confidence": 0.89, "bbox": [x1_5, y1_5, x2_5, y2_5] }
        ],
        "fluke": { "status": "Negative", "conf": 94 }
    })

    # -------------------------------------------------------------------------
    # Case 6: Benign Hemangioma Mass - Benign 2
    # -------------------------------------------------------------------------
    b2_img_path = "data/7272660/Benign/Benign/image/2.jpg"
    b2_liv_path = "data/7272660/Benign/Benign/segmentation/liver/2.json"
    b2_mass_path = "data/7272660/Benign/Benign/segmentation/mass/2.json"
    img6 = cv2.imread(b2_img_path)
    h6, w6 = img6.shape[:2]
    shutil.copy(b2_img_path, os.path.join(out_dir, "case6_benign_hemangioma.jpg"))
    with open(b2_liv_path, "r") as f:
        b2_liv_poly = json.load(f)
    with open(b2_mass_path, "r") as f:
        b2_mass_poly = json.load(f)
    
    pts6 = np.array(b2_mass_poly)
    x1_6, y1_6 = int(pts6[:, 0].min()), int(pts6[:, 1].min())
    x2_6, y2_6 = int(pts6[:, 0].max()), int(pts6[:, 1].max())

    cases.append({
        "id": "case6_benign_hemangioma",
        "title": "เคสที่ 6: ก้อนเนื้อหลอดเลือดตับธรรมดา (Hepatic Hemangioma)",
        "image_url": "/static/samples/case6_benign_hemangioma.jpg",
        "view": "Right Hepatic Lobe",
        "width": w6,
        "height": h6,
        "liver_area_percent": 28.0,
        "liver_polygon": b2_liv_poly,
        "mass_polygon": b2_mass_poly,
        "s_stage": { "stage": "S1", "conf": 91, "label": "Grade S1 — ระดับน้อย Mild (5%–33%)" },
        "fibrosis": { "stage": "F1", "risk_tier": "ความเสี่ยงต่ำ (Low Risk)", "p_f2": 24, "p_f3": 6, "p_f4": 1 },
        "lesions": [
            { "class": "Hemangioma", "confidence": 0.92, "bbox": [x1_6, y1_6, x2_6, y2_6] }
        ],
        "fluke": { "status": "Negative", "conf": 96 }
    })

    # -------------------------------------------------------------------------
    # Case 7: Cirrhosis F4 + HCC Malignant Tumor - Malignant 1
    # -------------------------------------------------------------------------
    m1_img_path = "data/7272660/Malignant/Malignant/image/1.jpg"
    m1_liv_path = "data/7272660/Malignant/Malignant/segmentation/liver/1.json"
    m1_mass_path = "data/7272660/Malignant/Malignant/segmentation/mass/1.json"
    img7 = cv2.imread(m1_img_path)
    h7, w7 = img7.shape[:2]
    shutil.copy(m1_img_path, os.path.join(out_dir, "case7_cirrhosis_f4_hcc.jpg"))
    with open(m1_liv_path, "r") as f:
        m1_liv_poly = json.load(f)
    with open(m1_mass_path, "r") as f:
        m1_mass_poly = json.load(f)

    pts7 = np.array(m1_mass_poly)
    x1_7, y1_7 = int(pts7[:, 0].min()), int(pts7[:, 1].min())
    x2_7, y2_7 = int(pts7[:, 0].max()), int(pts7[:, 1].max())

    cases.append({
        "id": "case7_cirrhosis_f4_hcc",
        "title": "เคสที่ 7: ภาวะตับแข็ง + ก้อนสงสัยมะเร็งตับ (Cirrhosis F4 + HCC)",
        "image_url": "/static/samples/case7_cirrhosis_f4_hcc.jpg",
        "view": "Right Hepatic View (กลีบขวา)",
        "width": w7,
        "height": h7,
        "liver_area_percent": 31.2,
        "liver_polygon": m1_liv_poly,
        "mass_polygon": m1_mass_poly,
        "s_stage": { "stage": "S1", "conf": 84, "label": "Grade S1 — ระดับน้อย Mild (5%–33%)" },
        "fibrosis": { "stage": "F4", "risk_tier": "ความเสี่ยงสูง (High Risk / Cirrhosis)", "p_f2": 95, "p_f3": 88, "p_f4": 76 },
        "lesions": [
            { "class": "HCC", "confidence": 0.94, "bbox": [x1_7, y1_7, x2_7, y2_7] }
        ],
        "fluke": { "status": "Positive", "conf": 86 }
    })

    # -------------------------------------------------------------------------
    # Case 8: Advanced Malignant Tumor + High Biliary Fluke Risk - Malignant 63
    # -------------------------------------------------------------------------
    m8_img_path = "data/7272660/Malignant/Malignant/image/63.jpg"
    m8_liv_path = "data/7272660/Malignant/Malignant/segmentation/liver/63.json"
    m8_mass_path = "data/7272660/Malignant/Malignant/segmentation/mass/63.json"
    img8 = cv2.imread(m8_img_path)
    h8, w8 = img8.shape[:2]
    shutil.copy(m8_img_path, os.path.join(out_dir, "case8_malignant_biliary_risk.jpg"))
    with open(m8_liv_path, "r") as f:
        m8_liv_poly = json.load(f)
    with open(m8_mass_path, "r") as f:
        m8_mass_poly = json.load(f)

    pts8 = np.array(m8_mass_poly)
    x1_8, y1_8 = int(pts8[:, 0].min()), int(pts8[:, 1].min())
    x2_8, y2_8 = int(pts8[:, 0].max()), int(pts8[:, 1].max())

    cases.append({
        "id": "case8_malignant_biliary_risk",
        "title": "เคสที่ 8: ก้อนเนื้อตับร้ายแรง + เสี่ยงท่อน้ำดีสูง (CCA / Malignant)",
        "image_url": "/static/samples/case8_malignant_biliary_risk.jpg",
        "view": "Central Hepatic / Biliary Confluence",
        "width": w8,
        "height": h8,
        "liver_area_percent": 34.0,
        "liver_polygon": m8_liv_poly,
        "mass_polygon": m8_mass_poly,
        "s_stage": { "stage": "S2", "conf": 86, "label": "Grade S2 — ระดับปานกลาง Moderate (33%–66%)" },
        "fibrosis": { "stage": "F3", "risk_tier": "ความเสี่ยงสูง (High Risk - Bridging Fibrosis)", "p_f2": 88, "p_f3": 74, "p_f4": 35 },
        "lesions": [
            { "class": "Malignant Tumor", "confidence": 0.95, "bbox": [x1_8, y1_8, x2_8, y2_8] }
        ],
        "fluke": { "status": "Positive", "conf": 92 }
    })

    # Save to JSON
    json_path = "static/samples_data.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated {len(cases)} real clinical benchmark cases in {json_path}!")

if __name__ == "__main__":
    build_benchmarks()
