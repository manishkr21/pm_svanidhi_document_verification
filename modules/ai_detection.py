import os
import torch
import torch.nn as nn
import torchvision.models as models
import torchvision.transforms as transforms
from PIL import Image
import numpy as np
import cv2

# Global cached model instance
_MODEL_CACHE = None

def get_model_path():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    model_path = os.path.join(base_dir, "models", "mobilenet_best (3).pth")
    if not os.path.exists(model_path):
        model_path = os.path.join(base_dir, "mobilenet_best (3).pth")
    return model_path

def load_model(model_path: str = None):
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE

    if model_path is None:
        model_path = get_model_path()

    try:
        model = models.mobilenet_v3_large(pretrained=False)
        num_ftrs = model.classifier[0].in_features
        model.classifier = nn.Sequential(
            nn.Linear(num_ftrs, 1280),
            nn.Hardswish(),
            nn.Dropout(0.5),
            nn.Linear(1280, 2)
        )
        if os.path.exists(model_path):
            state_dict = torch.load(model_path, map_location=torch.device("cpu"))
            model.load_state_dict(state_dict)
            model.eval()
            _MODEL_CACHE = model
            return model
        else:
            print(f"Error: Model file not found at {model_path}")
            return None
    except Exception as e:
        print(f"Error loading AI detection model: {e}")
        return None

def preprocess_image(image: Image.Image):
    transform = transforms.Compose([
        transforms.Resize((224, 224)),  
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])  
    ])
    return transform(image).unsqueeze(0)

def detect_face(image: Image.Image):
    """
    Detect face in PIL image using Haar Cascade classifier.
    Returns (face_detected: bool, cropped_face: Image.Image)
    """
    try:
        open_cv_image = np.array(image.convert('RGB'))
        open_cv_image_bgr = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(open_cv_image_bgr, cv2.COLOR_BGR2GRAY)
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

        faces = face_cascade.detectMultiScale(
            gray, 
            scaleFactor=1.2,  
            minNeighbors=5,  
            minSize=(40, 40)  
        )
        if len(faces) > 0:
            x, y, w, h = faces[0]
            cropped_face = image.crop((x, y, x + w, y + h))
            return True, cropped_face
    except Exception as e:
        print(f"Error during face detection: {e}")
    return False, None

def predict_ai_image(image: Image.Image, model=None, real_threshold: float = 0.5):
    """
    Predict whether a PIL Image is Real or GAN-Generated using loaded PyTorch model.
    """
    if model is None:
        model = load_model()

    if model is None:
        return "Model Not Loaded", 0.0, 0.0

    image_tensor = preprocess_image(image)
    with torch.no_grad():
        output = model(image_tensor)
        probabilities = torch.softmax(output, dim=1)

    gan_score = probabilities[0, 0].item()  
    real_score = probabilities[0, 1].item()  
    predicted_class = "Real" if real_score >= real_threshold else "GAN-Generated"

    return predicted_class, real_score, gan_score

def process_ai_detection(data_dir: str):
    """
    Scaffolding & CLI executor for AI image detection.
    Reads images from data_dir and runs deepfake model inference.
    """
    print(f"Starting AI image detection on directory: {data_dir}")
    if not os.path.exists(data_dir):
        print(f"Error: Directory {data_dir} does not exist.")
        return

    model = load_model()
    if model is None:
        print("Failed to initialize PyTorch model for AI detection.")
        return

    images = [f for f in os.listdir(data_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))]
    print(f"Found {len(images)} files to process in AI detection pipeline.")

    for img_name in images:
        img_path = os.path.join(data_dir, img_name)
        print(f"\nProcessing {img_name}...")
        try:
            pil_img = Image.open(img_path).convert("RGB")
            face_detected, cropped_face = detect_face(pil_img)
            if not face_detected:
                print(f" - Face Detection: No face detected. Analyzing full image...")
                pred_class, real_score, gan_score = predict_ai_image(pil_img, model=model)
            else:
                print(f" - Face Detection: Face detected successfully!")
                pred_class, real_score, gan_score = predict_ai_image(cropped_face, model=model)

            print(f" - Result: {pred_class} (Real: {real_score:.4f}, GAN: {gan_score:.4f})")
        except Exception as e:
            print(f" - Error processing {img_name}: {e}")

    print("\nAI image detection task completed.\n")

