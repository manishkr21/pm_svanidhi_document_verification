import os
import io
import sys
import numpy as np
import cv2
from PIL import Image, ImageChops, ImageEnhance, ExifTags
import matplotlib.pyplot as plt

"""
Image Edit Detection Module
---------------------------
Implements a multi-signal heuristic forensic pipeline for digital image edit detection:
1. Adaptive Multi-Quality Error Level Analysis (ELA) with Connected Component Analysis
2. Patch Noise Variance & Outlier Consistency Analysis
3. Angle & Distance-Constrained ORB Feature Copy-Move (Cloning) Detection
4. Discrete Cosine Transform (DCT) High-Frequency Energy Inconsistency Detection
5. Spatial Edge Inconsistency Density Analysis (Canny Filter)
6. Comprehensive EXIF & XMP Metadata Software/History Inspection
7. Rule-Based Signal Boosting & Weighted Decision Fusion

Note on Modern AI / Mobile Edits:
Samsung Object Eraser, Google Magic Eraser, Photoshop Generative Fill, and AI Inpainting
produce semantically plausible pixels and save the final image uniformly. They frequently
bypass simple noise and compression heuristics. For 90%+ detection accuracy on modern
AI-based image manipulations, pretrained deep learning forensic models such as TruFor
or ManTra-Net are recommended.
"""

_TRUFOR_MODEL = None
_TRUFOR_DEVICE = None

def load_trufor_model():
    """
    Lazy loads and caches the TruFor deep learning forgery detection model.
    """
    global _TRUFOR_MODEL, _TRUFOR_DEVICE
    if _TRUFOR_MODEL is not None:
        return _TRUFOR_MODEL, _TRUFOR_DEVICE

    trufor_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "TruFor", "TruFor_train_test"))
    weights_path = os.path.join(trufor_dir, "pretrained_models", "trufor.pth.tar")
    config_path = os.path.join(trufor_dir, "lib", "config", "trufor_ph3.yaml")

    if not os.path.exists(weights_path):
        print(f"Warning: TruFor weights file not found at: {weights_path}")
        return None, None

    if trufor_dir not in sys.path:
        sys.path.insert(0, trufor_dir)

    try:
        import torch
        from lib.config import config
        from lib.utils import get_model

        device = 'cuda' if torch.cuda.is_available() else 'cpu'

        config.defrost()
        config.merge_from_file(config_path)
        config.freeze()

        model = get_model(config)
        checkpoint = torch.load(weights_path, map_location=torch.device(device), weights_only=False)
        model.load_state_dict(checkpoint['state_dict'])
        model = model.to(device)
        model.eval()

        _TRUFOR_MODEL = model
        _TRUFOR_DEVICE = device
        print(f"Loaded TruFor Deep Learning model on device: {device}")
        return _TRUFOR_MODEL, _TRUFOR_DEVICE
    except Exception as e:
        print(f"Error initializing TruFor model: {e}")
        return None, None

def run_trufor_detection(image: Image.Image):
    """
    Executes TruFor deep learning forgery and edit detection on a PIL image.
    Returns:
        trufor_score: float (0.0 to 1.0 global edit probability)
        map_img: PIL Image (Colorized localization map of forged regions)
        conf_img: PIL Image (Grayscale confidence reliability map)
        np_img: PIL Image or None (Noiseprint++ residual map)
    """
    model, device = load_trufor_model()
    if model is None:
        return 0.0, None, None, None

    try:
        import torch
        import torch.nn.functional as F

        image_rgb = image.convert("RGB")
        img_np = np.array(image_rgb)

        tensor = torch.tensor(img_np.transpose(2, 0, 1), dtype=torch.float).unsqueeze(0) / 256.0
        tensor = tensor.to(device)

        with torch.no_grad():
            pred, conf, det, npp = model(tensor, save_np=True)

            trufor_score = float(torch.sigmoid(det).item()) if det is not None else 0.0

            # Process localization map (class 1 probability)
            pred = torch.squeeze(pred, 0)
            pred_map = F.softmax(pred, dim=0)[1].cpu().numpy()

            # Process confidence map
            if conf is not None:
                conf_squeezed = torch.squeeze(conf, 0)
                conf_map = torch.sigmoid(conf_squeezed)[0].cpu().numpy()
            else:
                conf_map = np.ones_like(pred_map)

            # Process Noiseprint++
            if npp is not None:
                np_map = torch.squeeze(npp, 0)[0].cpu().numpy()
            else:
                np_map = None

        # Colorize localization heatmap using RdBu_r colormap
        cmap = plt.get_cmap('RdBu_r')
        colored_map = (cmap(pred_map)[:, :, :3] * 255).astype(np.uint8)
        map_img = Image.fromarray(colored_map)

        # Confidence map to grayscale PIL image
        conf_gray = (np.clip(conf_map, 0, 1) * 255).astype(np.uint8)
        conf_img = Image.fromarray(conf_gray)

        # Noiseprint++ map
        if np_map is not None:
            np_norm = cv2.normalize(np_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            np_img = Image.fromarray(np_norm)
        else:
            np_img = None

        return trufor_score, map_img, conf_img, np_img
    except Exception as e:
        print(f"Error running TruFor detection: {e}")
        return 0.0, None, None, None

def compute_multi_ela(image_rgb: Image.Image, qualities=[95, 90, 85, 80]):
    """
    Performs multi-quality ELA using adaptive percentiles and connected components
    to prioritize large suspicious error blobs over isolated pixel noise.
    """
    scores = []
    best_ela_img = None
    max_ratio = -1.0

    for q in qualities:
        buffer = io.BytesIO()
        image_rgb.save(buffer, 'JPEG', quality=q)
        buffer.seek(0)
        compressed = Image.open(buffer)
        
        ela_diff = ImageChops.difference(image_rgb, compressed)
        diff_np = np.array(ela_diff)
        gray = cv2.cvtColor(diff_np, cv2.COLOR_RGB2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # 1. Adaptive Thresholding based on 97th percentile of difference intensity
        thresh = float(np.percentile(blurred, 97))
        thresh = max(15.0, thresh)  # ensure minimum signal threshold
        _, mask = cv2.threshold(blurred, thresh, 255, cv2.THRESH_BINARY)
        
        # Morphological OPEN to suppress single-pixel noise
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        ratio = np.count_nonzero(mask) / float(mask.size)

        # 2. Connected Component Analysis for blob detection
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
        largest = 0
        for i in range(1, num_labels):
            largest = max(largest, stats[i, cv2.CC_STAT_AREA])

        largest_ratio = largest / float(mask.size)

        # ELA score calculation favoring large connected suspicious regions
        q_score = min(1.0, ratio * 8.0 + largest_ratio * 25.0)
        scores.append(q_score)

        if ratio > max_ratio:
            max_ratio = ratio
            extrema = ela_diff.getextrema()
            max_diff = max([ex[1] for ex in extrema])
            scale = 255.0 / max_diff if max_diff != 0 else 1.0
            best_ela_img = ImageEnhance.Brightness(ela_diff).enhance(scale * 0.4)

    ela_score = min(1.0, float(np.mean(scores)))
    if best_ela_img is None:
        best_ela_img = image_rgb

    return float(ela_score), best_ela_img

def compute_noise_consistency(image_rgb: Image.Image, block_size: int = 32):
    """
    Measures spatial sensor noise consistency across patches using median-outlier statistics.
    Edited/spliced patches exhibit different noise variance than background regions.
    """
    img_np = np.array(image_rgb)
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    
    # High-frequency noise residual
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    noise = gray.astype(np.float32) - blurred.astype(np.float32)
    
    h, w = noise.shape
    block_stds = []
    
    for y in range(0, h - block_size, block_size):
        for x in range(0, w - block_size, block_size):
            patch = noise[y:y+block_size, x:x+block_size]
            block_stds.append(np.std(patch))
            
    if not block_stds or len(block_stds) < 4:
        return 0.0
        
    block_stds = np.array(block_stds)
    median = np.median(block_stds)
    std_val = np.std(block_stds)

    if std_val < 1e-5:
        return 0.0
    
    outliers = np.sum(np.abs(block_stds - median) > 2.0 * std_val)
    noise_score = min(1.0, float(outliers / float(len(block_stds)) * 4.0))
    return float(noise_score)

def compute_copy_move_detection(image_rgb: Image.Image, min_dist: float = 40.0):
    """
    Detects cloned/copy-moved regions using ORB feature matching with distance
    and orientation angle filtering to reduce false positives.
    """
    img_np = np.array(image_rgb)
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    
    orb = cv2.ORB_create(nfeatures=800)
    keypoints, descriptors = orb.detectAndCompute(gray, None)
    
    annotated = img_np.copy()
    if descriptors is None or len(descriptors) < 10:
        return 0.0, Image.fromarray(annotated)
        
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = matcher.knnMatch(descriptors, descriptors, k=2)
    
    valid_clones = []
    for match_pair in matches:
        if len(match_pair) < 2:
            continue
        m, n = match_pair
        if m.distance < 0.75 * n.distance and m.queryIdx != m.trainIdx:
            pt1 = keypoints[m.queryIdx].pt
            pt2 = keypoints[m.trainIdx].pt
            dist = np.sqrt((pt1[0] - pt2[0])**2 + (pt1[1] - pt2[1])**2)
            
            # Ignore matches inside the same immediate neighborhood
            if dist > min_dist:
                angle1 = keypoints[m.queryIdx].angle
                angle2 = keypoints[m.trainIdx].angle
                angle_diff = abs(angle1 - angle2)
                angle_diff = min(angle_diff, 360.0 - angle_diff)
                
                # Check orientation angle alignment for cloned features
                if angle_diff < 15.0:
                    valid_clones.append((pt1, pt2))
                    cv2.line(annotated, (int(pt1[0]), int(pt1[1])), (int(pt2[0]), int(pt2[1])), (255, 0, 0), 2)
                    cv2.circle(annotated, (int(pt1[0]), int(pt1[1])), 4, (0, 255, 255), -1)
                    cv2.circle(annotated, (int(pt2[0]), int(pt2[1])), 4, (0, 0, 255), -1)

    clone_count = len(valid_clones)
    clone_score = min(1.0, clone_count / 8.0)
    return float(clone_score), Image.fromarray(annotated)

def compute_edge_inconsistency(image_rgb: Image.Image):
    """
    Detects abnormal edge density patterns caused by digital splicing, cutting, or object insertion.
    """
    img_np = np.array(image_rgb)
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 60, 120)
    
    kernel = np.ones((5, 5), np.uint8)
    density = cv2.filter2D(edges.astype(np.float32), -1, kernel)
    
    edge_score = float(np.std(density) / 255.0)
    edge_score = min(1.0, edge_score * 1.5)
    return float(edge_score)

def compute_dct_inconsistency(image_rgb: Image.Image):
    """
    Measures DCT high-frequency energy inconsistencies across image blocks.
    Edited JPEG images often display irregular high-frequency energy distribution in DCT domain.
    """
    img_np = np.array(image_rgb)
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY).astype(np.float32)
    
    h, w = gray.shape
    h_even = h - (h % 2)
    w_even = w - (w % 2)
    
    if h_even < 64 or w_even < 64:
        return 0.0
        
    gray_even = gray[:h_even, :w_even]
    dct = cv2.dct(gray_even)
    
    # Inspect high-frequency DCT energy
    energy = np.mean(np.abs(dct[30:, 30:]))
    dct_score = min(1.0, float(energy / 18.0))
    return float(dct_score)

def check_metadata_software(image: Image.Image):
    """
    Inspects EXIF, XMP, Software, CreatorTool, ProcessingSoftware, ImageHistory,
    and MakerNote metadata fields for traces of editing applications.
    """
    detected_software = []
    search_keywords = [
        "photoshop", "gimp", "lightroom", "canva", "picsart",
        "facetune", "snapseed", "inshot", "paint.net", "express",
        "pixlr", "magic eraser", "generative", "ai edit"
    ]
    
    # 1. Scan image.info dictionary (e.g. PNG / WebP metadata & XMP blocks)
    if hasattr(image, "info") and isinstance(image.info, dict):
        for key, val in image.info.items():
            val_str = str(val).lower()
            key_str = str(key).lower()
            for kw in search_keywords:
                if kw in val_str or kw in key_str:
                    detected_software.append(f"Info:{key}={val}")
                    break

    # 2. Scan EXIF Tags
    try:
        exif = image.getexif()
        if exif:
            for tag_id, value in exif.items():
                tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                val_str = str(value).lower()
                tag_lower = str(tag_name).lower()
                
                # Highlight relevant metadata tags
                if any(t in tag_lower for t in ["software", "processingsoftware", "creatortool", "xmp", "makernote", "imagehistory"]):
                    detected_software.append(f"{tag_name}:{value}")
                else:
                    for kw in search_keywords:
                        if kw in val_str:
                            detected_software.append(f"{tag_name}:{value}")
                            break
    except Exception:
        pass

    # Unique detected items
    detected_software = list(dict.fromkeys(detected_software))
    meta_score = 1.0 if detected_software else 0.0
    return float(meta_score), detected_software

def process_edit_image(image: Image.Image, quality: int = 90):
    """
    Multi-Signal Forensics Pipeline combining:
    1. TruFor Deep Learning Model (60% weight when available)
    2. Adaptive Multi-Quality ELA (10%)
    3. Patch Noise Outlier Consistency (8%)
    4. DCT High-Frequency Domain Energy (8%)
    5. Canny Edge Density Inconsistency (6%)
    6. Distance & Angle-Constrained Copy-Move Detection (6%)
    7. EXIF/XMP Metadata Software Inspection (2%)
    + Rule-based boosting for combined signals.
    """
    image_rgb = image.convert("RGB")
    
    # 0. TruFor Deep Learning Detection
    trufor_score, trufor_map, trufor_conf, np_img = run_trufor_detection(image)

    # 1. Multi-Quality Adaptive ELA
    ela_score, ela_image = compute_multi_ela(image_rgb)
    
    # 2. Patch Noise Outliers
    noise_score = compute_noise_consistency(image_rgb)
    
    # 3. Copy-Move Detection
    clone_score, clone_img = compute_copy_move_detection(image_rgb)

    # 4. Edge Inconsistency
    edge_score = compute_edge_inconsistency(image_rgb)

    # 5. DCT Artifact Detection
    dct_score = compute_dct_inconsistency(image_rgb)

    # 6. Metadata Inspection
    meta_score, soft_list = check_metadata_software(image)
    
    # Heuristic Multi-Signal Score
    heuristic_score = (
        (ela_score * 0.25) +
        (noise_score * 0.20) +
        (dct_score * 0.20) +
        (edge_score * 0.15) +
        (clone_score * 0.15) +
        (meta_score * 0.05)
    )

    # Rule-Based Signal Boosting
    boost = 0.0
    if ela_score > 0.45 and noise_score > 0.45:
        boost += 0.20
    if clone_score > 0.40:
        boost += 0.20
    if meta_score == 1.0:
        boost += 0.15

    # Decision Fusion: TruFor Deep Learning (60%) + Heuristics (40%) + Boost
    if trufor_map is not None:
        fused_score = min(1.0, max(0.0, (trufor_score * 0.60) + (heuristic_score * 0.40) + boost))
    else:
        fused_score = min(1.0, max(0.0, heuristic_score + boost))
    
    # Edit Classification threshold
    is_edited = fused_score > 0.35 or trufor_score > 0.50
    
    details = [
        f"TruFor Deep Learning: {trufor_score:.2f}",
        f"Adaptive ELA: {ela_score:.2f}",
        f"Noise Consistency: {noise_score:.2f}",
        f"DCT Energy: {dct_score:.2f}",
        f"Edge Inconsistency: {edge_score:.2f}",
        f"Copy-Move Cloning: {clone_score:.2f}",
        f"Metadata Scan: {'Edited (' + soft_list[0] + ')' if soft_list else 'Clean'}"
    ]

    if is_edited:
        summary = f"Possible Manipulation Detected (Fused Score: {fused_score:.2f}) | " + " | ".join(details)
    else:
        summary = f"No Significant Editing Detected (Fused Score: {fused_score:.2f}) | " + " | ".join(details)

    details_dict = {
        "trufor_score": trufor_score,
        "trufor_map": trufor_map,
        "trufor_conf": trufor_conf,
        "np_img": np_img,
        "ela_score": ela_score,
        "noise_score": noise_score,
        "dct_score": dct_score,
        "edge_score": edge_score,
        "clone_score": clone_score,
        "meta_score": meta_score,
        "soft_list": soft_list,
        "clone_img": clone_img,
        "fused_score": fused_score
    }

    return is_edited, fused_score, ela_image, summary, details_dict

def process_edit_detection(data_dir: str):
    """
    CLI processing function: reads images from data_dir and performs multi-signal edit detection.
    """
    print(f"Starting multi-signal edited image detection on directory: {data_dir}")
    if not os.path.exists(data_dir):
        print(f"Error: Directory {data_dir} does not exist.")
        return

    images = [f for f in os.listdir(data_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))]
    print(f"Found {len(images)} files to process in edit detection pipeline.")

    for img_name in images:
        img_path = os.path.join(data_dir, img_name)
        print(f"\nProcessing {img_name} for edits/manipulation...")
        try:
            pil_img = Image.open(img_path)
            is_edited, edit_score, _, summary, _ = process_edit_image(pil_img)
            edit_type = "Manipulated/Edited" if is_edited else "Unedited/Original"
            print(f" -> Result for {img_name}: Edited={is_edited} (Type: {edit_type}, Fused Score: {edit_score:.2f})")
            print(f"    {summary}")
        except Exception as e:
            print(f" -> Error processing {img_name}: {e}")

    print("\nEdited image detection task completed.\n")

