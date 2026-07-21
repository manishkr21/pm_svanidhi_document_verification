# 🛡️ POC: Image Intelligence & Multi-Modal Forensics Platform

An advanced, multi-modal image intelligence proof-of-concept (POC) platform designed for:
1. **AI & Deepfake Face Detection**
2. **Robust Multiscale QR Code Matrix Detection & Payload Decoding**
3. **Multi-Signal Digital Image Edit & Forgery Detection** (fusing TruFor Deep Learning with 6 heuristic forensic signals).

---

## 📐 System Architecture

```
                          POC Platform
                               │
      ┌────────────────────────┼────────────────────────┐
      ▼                        ▼                        ▼
1. AI & Deepfake         2. QR Code Decoding      3. Edited Image
   Image Detector           & Detection              Forensics
(MobileNetV3 + Haar      (ZXing C++ Engine +       (TruFor DL + 6
     Cascade)            OpenCV + Multiscale)      Heuristic Signals)
```

### 📁 Directory Structure

```text
poc/
├── app.py                     # Interactive Streamlit Web UI application
├── main.py                    # CLI runner and GUI launcher script
├── requirements.txt           # Python dependencies
├── models/
│   └── mobilenet_best (3).pth # PyTorch pretrained MobileNetV3 weights
├── modules/
│   ├── ai_detection.py        # AI / GAN face detection engine
│   ├── qr_detection.py        # Multiscale QR code detection & decoding engine
│   └── edit_detection.py      # TruFor Deep Learning + 6-signal forensic engine
└── data/                      # Input sample directories
    ├── ai_detection_images/   # Samples for AI detection
    ├── qr_detection/          # Samples for QR code decoding
    └── edited_images/         # Samples for edited image forensics
```

---

## ⚙️ Features & Detection Modules

### 1. 🔍 AI / Deepfake Image Detection
Detects whether an image features an authentic human face or an **AI / GAN-generated** fake (e.g. StyleGAN, StarGAN, Midjourney, DeepFaceLab).
* **Face Localization**: Uses OpenCV's Haar Cascade classifier (`haarcascade_frontalface_default.xml`) to isolate facial regions before inference.
* **Classifier Model**: PyTorch `MobileNetV3-Large` trained on GAN facial datasets.
* **Output**: Real Confidence vs. GAN Confidence scores with user-adjustable thresholding.

### 2. 📱 QR Code Detection & Decoding
Scans images (including low-resolution, blurry, compressed, or high-density document scans like Aadhaar/PAN cards) to detect matrix locations and extract text/URL payloads.
* **Multiscale & Preprocessing**: Generates upscaled ($2\times, 3\times$), CLAHE, Sharpened, Otsu, and Adaptive Gaussian threshold variants.
* **Dual Engines**: Primary decoding via high-performance `zxingcpp` engine with OpenCV `QRCodeDetector` fallback.
* **Strict Payload Verification**: Only draws bounding boxes when a valid non-empty payload is decoded.

### 3. ✏️ Multi-Signal Edited Image Detection
Combines deep learning forgery localization with 6 classical heuristic forensic signals for comprehensive edit, splicing, object removal/erasing, and retouching detection.

| Signal / Model | Description |
| :--- | :--- |
| **TruFor Deep Learning** | CMX cross-modal architecture + Noiseprint++ residual extractor for pixel-level forgery localization maps and confidence scores. |
| **Adaptive Multi-Quality ELA** | Re-compresses image at $Q \in [95, 90, 85, 80]$, uses 97th percentile adaptive thresholding and Connected Component Analysis to highlight suspicious compression error blobs. |
| **Patch Noise Outliers** | Analyzes spatial camera sensor noise variance ($\sigma$) across $32\times 32$ patches to detect spliced regions from different sensors. |
| **Copy-Move ORB Cloning** | Detects cloned regions using ORB feature descriptor matching with spatial distance ($>40\text{px}$) and orientation angle ($<15^\circ$) constraints. |
| **Canny Edge Density** | Measures spatial edge density variations to detect unnatural cutouts or smooth brush boundaries. |
| **DCT High-Frequency Energy** | Measures 2D Discrete Cosine Transform spectral energy in high frequencies ($[30:, 30:]$) to spot compression anomalies. |
| **Metadata Inspection** | Scans EXIF tags and `image.info` dictionaries for signatures of editing applications (Photoshop, GIMP, Canva, PicsArt, Magic Eraser, etc.). |

---

## 🚀 Getting Started

### 1. Installation

Ensure Python 3.8+ is installed. Clone the repository and install the requirements:

```bash
cd poc
pip install -r requirements.txt
```

*(Optional)* For ZXing QR engine support:
```bash
pip install zxing-cpp
```

---

### 2. Running the Streamlit Web Application

Launch the interactive web UI:

```bash
python main.py --task gui
```
*Or directly via Streamlit:*
```bash
streamlit run app.py
```

Open your browser at `http://localhost:8501`.

---

### 3. Running via Command Line Interface (CLI)

Run all tasks sequentially on sample images in `data/`:

```bash
python main.py --task all
```

Run specific detection tasks:

```bash
# Run AI / Deepfake Detection on data/ai_detection_images/
python main.py --task ai

# Run QR Code Detection on data/qr_detection/
python main.py --task qr

# Run Edited Image Detection on data/edited_images/
python main.py --task edit
```

---

## 📊 Decision Fusion Model (Edit Detection)

The final edit score combines TruFor Deep Learning with the heuristic signals:

$$\text{Heuristic Score} = (0.25 \times \text{ELA}) + (0.20 \times \text{Noise}) + (0.20 \times \text{DCT}) + (0.15 \times \text{Edge}) + (0.15 \times \text{Clone}) + (0.05 \times \text{Meta})$$

$$\text{Fused Score} = \min\left(1.0, \, 0.60 \times \text{TruFor Score} + 0.40 \times \text{Heuristic Score} + \text{Rule-Based Boost}\right)$$

An image is flagged as **Edited / Manipulated** if $\text{Fused Score} > 0.35$ or $\text{TruFor Score} > 0.50$.
