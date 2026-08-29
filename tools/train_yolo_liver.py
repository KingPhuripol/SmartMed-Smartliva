from ultralytics import YOLO
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
YAML_PATH = BASE_DIR / "data" / "yolo_liver_dataset" / "dataset.yaml"

def main():
    # Load a model
    pretrained_pt = BASE_DIR / "weights" / "pretrained" / "yolov8n.pt"
    base_weights = str(pretrained_pt) if pretrained_pt.exists() else "yolov8n.pt"
    model = YOLO(base_weights)  # load a pretrained model

    # Train the model
    results = model.train(
        data=str(YAML_PATH),
        epochs=30,  # 30 epochs is enough for a quick bounding box
        imgsz=640,
        batch=16,
        device="mps", # Use Mac MPS
        project=str(BASE_DIR / "models" / "liver_detection"),
        name="yolov8n_liver"
    )

if __name__ == "__main__":
    main()
