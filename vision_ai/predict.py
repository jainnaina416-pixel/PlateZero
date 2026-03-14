import torch
from torchvision import models, transforms
from PIL import Image
import os
import json
import torch.nn as nn

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "sanitation_model.pth")
INDICES_PATH = os.path.join(BASE_DIR, 'class_indices.json')

IMG_SIZE = 224

_model = None
_class_indices = None
_device = None
_transform = None

def load_ai():
    global _model, _class_indices, _device, _transform
    if _model is None:
        if not os.path.exists(MODEL_PATH) or not os.path.exists(INDICES_PATH):
            return False
            
        with open(INDICES_PATH, 'r') as f:
            _class_indices = json.load(f)
            
        _device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        
        _model = models.mobilenet_v2(weights=None)
        num_ftrs = _model.classifier[1].in_features
        _model.classifier[1] = nn.Sequential(
            nn.Linear(num_ftrs, 128),
            nn.ReLU(),
            nn.Linear(128, len(_class_indices))
        )
        
        _model.load_state_dict(torch.load(MODEL_PATH, map_location=_device))
        _model = _model.to(_device)
        _model.eval()
        
        _transform = transforms.Compose([
            transforms.Resize((IMG_SIZE, IMG_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])
    return True

def predict_image(image_path):
    if not load_ai():
        return {"error": "Model not trained yet."}

    try:
        image = Image.open(image_path).convert('RGB')
        input_tensor = _transform(image).unsqueeze(0).to(_device)
        
        with torch.no_grad():
            outputs = _model(input_tensor)
            probabilities = torch.nn.functional.softmax(outputs[0], dim=0)
            confidence, class_idx = torch.max(probabilities, 0)
            
        label = _class_indices[str(class_idx.item())]
        conf_val = float(confidence.item())
        
        recommendation = "Everything looks good!"
        if label == "trash_outside_bin":
            recommendation = "Alert janitorial staff to clear overflow near bins."
        elif label == "clogged_sink":
            recommendation = "Dispatch maintenance to unclog sink immediately."
        elif label == "floor_waste":
            recommendation = "Send cleaning staff with mop/broom to clear floor."

        return {
            "status": "success",
            "prediction": label,
            "confidence": round(conf_val * 100, 2),
            "recommendation": recommendation
        }
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(predict_image(sys.argv[1]))
