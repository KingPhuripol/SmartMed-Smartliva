import os
from huggingface_hub import hf_hub_download

def main():
    # สร้างโฟลเดอร์สำหรับเก็บโมเดล
    save_dir = os.path.join("models", "medsam2", "checkpoints")
    os.makedirs(save_dir, exist_ok=True)
    
    print(f"กำลังดาวน์โหลด MedSAM2_latest.pt ไปที่ {save_dir} ...")
    
    # ดาวน์โหลดโมเดล
    local_path = hf_hub_download(
        repo_id="wanglab/MedSAM2", 
        filename="MedSAM2_latest.pt",
        local_dir=save_dir,
        local_dir_use_symlinks=False
    )
    
    print(f"✅ ดาวน์โหลดสำเร็จ! โมเดลถูกบันทึกไว้ที่: {local_path}")

if __name__ == "__main__":
    main()
