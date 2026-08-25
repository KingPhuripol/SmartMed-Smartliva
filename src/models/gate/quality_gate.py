"""quality_gate.py — ด่าน 1: คุณภาพภาพ US พอวิเคราะห์ไหม?

รวม 2 แหล่งสัญญาณ (ยังไม่ต้องมี label):
  A) physics gate เดิม (model_check_image) : เป็น B-mode US จริงไหม
  B) no-reference metrics                   : คม/คอนทราสต์/พื้นที่สัญญาณ/ความอิ่มตัว

คืนคำตัดสิน:
  REJECT     : ไม่ใช่ US จริง หรือคุณภาพต่ำจนไม่ควรวิเคราะห์ (กันโมเดลโรคเพี้ยน)
  BORDERLINE : ก้ำกึ่ง — วิเคราะห์ได้แต่ลดความเชื่อมั่น
  ACCEPT     : คุณภาพดีพอ

หมายเหตุ: threshold ด้านล่างเป็นค่าตั้งต้น ควร calibrate ต่อฟลีตเครื่องของคุณ
(เหมือน envelope ของ physics gate) ด้วยสคริปต์ calibrate_quality.py
"""
import os, sys, json
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.dirname(HERE)               # โฟลเดอร์โมเดล v1 ที่ bundle physics gate
for p in (HERE, MODEL_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from model_check_image import inspect as _phys_inspect
    from model_check_image.gate import Envelope as _Envelope
    HAVE_PHYS = True
except Exception as e:
    HAVE_PHYS = False
    _PHYS_ERR = str(e)

# ---- envelope แยกตามชนิดหัวตรวจ (fit ด้วย fit_envelopes.py จาก train split หลายอวัยวะ) ----
# envelope เดิมของ model_check_image fit จาก "ตับล้วน" 12,200 ภาพ แล้วเอาไปกั้นทุกอวัยวะ
# ทำให้ probe linear (carotid/thyroid/breast) หลุดกรอบและถูกตี NOT_US ทั้งคลาส
_ENV_PATH = os.path.join(HERE, "quality_envelopes.json")
_ENVS = {}
if HAVE_PHYS and os.path.exists(_ENV_PATH):
    try:
        _blob = json.load(open(_ENV_PATH))
        for _gm, _e in _blob.items():
            _ENVS[_gm] = _Envelope(_e["bounds"], _e["core"], _e.get("meta", {}))
    except Exception:
        _ENVS = {}


def geometry(path_or_img):
    """แยกชนิดหัวตรวจจากรูปทรงพื้นที่สัญญาณ: 'fan' (convex/sector) หรือ 'linear'"""
    if isinstance(path_or_img, str):
        img = Image.open(path_or_img)
    elif isinstance(path_or_img, np.ndarray):
        img = Image.fromarray(path_or_img)
    else:
        img = path_or_img
    g = np.asarray(img.convert("L").resize((256, 256), Image.BILINEAR), np.float32)
    sig = g > 18
    if sig.sum() < 500:
        return "fan"
    rows = np.where(sig.any(1))[0]; cols = np.where(sig.any(0))[0]
    bbox = (rows[-1] - rows[0] + 1) * (cols[-1] - cols[0] + 1)
    return "linear" if sig.sum() / max(bbox, 1) >= 0.88 else "fan"

# ---- ค่าตั้งต้น (ปรับได้ผ่าน calibrate) ----
TH = {
    "content_min": 0.12,     # สัดส่วนพื้นที่มีสัญญาณขั้นต่ำ
    "sharp_min": 6.0,        # variance ของ Laplacian ขั้นต่ำ (เบลอมาก = ต่ำ)
    "sharp_border": 12.0,
    "contrast_min": 0.045,   # std ภายในพื้นที่สัญญาณ (0-1)
    "contrast_border": 0.075,
    "white_max": 0.35,       # จุดขาวล้น (overlay/เกน) มากไป
}

CAL_PATH = os.path.join(HERE, "quality_cal.json")
if os.path.exists(CAL_PATH):
    try:
        TH.update(json.load(open(CAL_PATH)))
    except Exception:
        pass


def _gray(path_or_img):
    if isinstance(path_or_img, str):
        img = Image.open(path_or_img)
    elif isinstance(path_or_img, np.ndarray):
        img = Image.fromarray(path_or_img)
    else:
        img = path_or_img
    g = np.asarray(img.convert("L"), np.float32)
    return g


def _laplacian_var(g):
    """ความคม: variance ของ discrete Laplacian (ไม่พึ่ง scipy)"""
    lap = (-4 * g
           + np.roll(g, 1, 0) + np.roll(g, -1, 0)
           + np.roll(g, 1, 1) + np.roll(g, -1, 1))
    return float(lap[1:-1, 1:-1].var())


def measure(path_or_img):
    """no-reference metrics ของภาพ US"""
    g = _gray(path_or_img)
    signal = g > 15                     # พื้นที่มีสัญญาณ (ไม่ใช่พื้นดำ)
    content = float(signal.mean())
    vals = g[signal] / 255.0 if signal.any() else np.array([0.0])
    contrast = float(vals.std())
    white = float((g[signal] > 245).mean()) if signal.any() else 0.0
    black = float((g < 8).mean())
    sharp = _laplacian_var(g)
    return {"content_frac": round(content, 4), "sharpness": round(sharp, 2),
            "contrast": round(contrast, 4), "white_frac": round(white, 4),
            "black_frac": round(black, 4)}


def _phys(path, geom=None):
    """ตรวจ speckle ด้วย envelope ที่ตรงกับชนิดหัวตรวจ คืน (decision, geometry)"""
    if not HAVE_PHYS or not isinstance(path, str):
        return "UNAVAILABLE", geom
    try:
        if geom is None:
            geom = geometry(path)
    except Exception:
        geom = "fan"
    env = _ENVS.get(geom)
    try:
        v = _phys_inspect(path, envelope=env) if env is not None else _phys_inspect(path)
        return getattr(v.decision, "name", str(v.decision)).split(".")[-1].upper(), geom
    except Exception:
        return "UNMEASURABLE", geom


def assess(path):
    """คืน dict: {decision, quality, physics, metrics, reasons}"""
    m = measure(path)
    phys, geom = _phys(path)
    reasons = []

    # A) physics: ถ้าไม่ใช่ US จริง -> ตัดทันที
    if phys in ("REJECTED", "UNMEASURABLE"):
        return {"decision": "REJECT", "quality": 0.0, "physics": phys, "geometry": geom,
                "metrics": m, "reasons": ["physics_gate=" + phys]}

    # B) no-reference hard fails
    if m["content_frac"] < TH["content_min"]:
        reasons.append(f"content<{TH['content_min']}")
    if m["sharpness"] < TH["sharp_min"]:
        reasons.append(f"blurry(sharp<{TH['sharp_min']})")
    if m["contrast"] < TH["contrast_min"]:
        reasons.append(f"lowcontrast(<{TH['contrast_min']})")
    if m["white_frac"] > TH["white_max"]:
        reasons.append(f"saturated(white>{TH['white_max']})")
    if reasons:
        return {"decision": "REJECT", "quality": 0.2, "physics": phys, "geometry": geom,
                "metrics": m, "reasons": reasons}

    # borderline band
    border = []
    if m["sharpness"] < TH["sharp_border"]:
        border.append("soft")
    if m["contrast"] < TH["contrast_border"]:
        border.append("mild_contrast")
    if phys == "BORDERLINE":
        border.append("physics_borderline")

    # quality score (0-1) หยาบ ๆ จาก sharpness+contrast+content
    q = float(np.clip(
        0.45 * np.clip(m["sharpness"] / 30.0, 0, 1) +
        0.35 * np.clip(m["contrast"] / 0.15, 0, 1) +
        0.20 * np.clip(m["content_frac"] / 0.5, 0, 1), 0, 1))

    dec = "BORDERLINE" if border else "ACCEPT"
    return {"decision": dec, "quality": round(q, 3), "physics": phys, "geometry": geom,
            "metrics": m, "reasons": border}


def main():
    import glob, argparse
    ap = argparse.ArgumentParser(description="ประเมินคุณภาพภาพ US")
    ap.add_argument("input", help="ไฟล์ภาพ หรือโฟลเดอร์")
    args = ap.parse_args()
    files = sorted(sum([glob.glob(os.path.join(args.input, e)) for e in
                        ("*.jpg", "*.jpeg", "*.png", "*.JPG")], [])) \
        if os.path.isdir(args.input) else [args.input]
    for f in files:
        r = assess(f)
        print(f"{os.path.basename(f)[:34]:36s} {r['decision']:10s} q={r['quality']:.2f} "
              f"phys={r['physics']:9s} {r['metrics']}  {r['reasons']}")


if __name__ == "__main__":
    main()
