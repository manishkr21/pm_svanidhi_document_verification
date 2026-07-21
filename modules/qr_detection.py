import os
import cv2
import numpy as np
from PIL import Image

try:
    import zxingcpp
    HAS_ZXING = True
except ImportError:
    HAS_ZXING = False

def get_image_variants(img_rgb: Image.Image):
    """
    Generates multiscale and preprocessed variants of an image to handle 
    low-resolution, compressed, or high-density document QR codes (e.g. PAN cards, Aadhaar cards).
    Returns list of tuples: (variant_name, image_matrix, scale_factor)
    """
    img_np = np.array(img_rgb)
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    h, w = img_bgr.shape[:2]

    base_variants = [("orig", img_bgr, 1.0)]

    # 1. Upscale low-res images (e.g., small 22KB PAN card uploads)
    if min(w, h) < 1400:
        up_2x = cv2.resize(img_bgr, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        base_variants.append(("up_2x", up_2x, 2.0))

    if min(w, h) < 700:
        up_3x = cv2.resize(img_bgr, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)
        base_variants.append(("up_3x", up_3x, 3.0))

    all_variants = []
    for name, img_mat, scale in base_variants:
        all_variants.append((name, img_mat, scale))

        # Convert to Grayscale
        gray = cv2.cvtColor(img_mat, cv2.COLOR_BGR2GRAY)
        all_variants.append((f"{name}_gray", gray, scale))

        # Contrast Limited Adaptive Histogram Equalization (CLAHE)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        clahe_img = clahe.apply(gray)
        all_variants.append((f"{name}_clahe", clahe_img, scale))

        # Sharpening Filter
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        sharp = cv2.filter2D(gray, -1, kernel)
        all_variants.append((f"{name}_sharp", sharp, scale))

        # Otsu Binarization
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        all_variants.append((f"{name}_otsu", otsu, scale))

        # Adaptive Gaussian Threshold
        adapt = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 3)
        all_variants.append((f"{name}_adapt", adapt, scale))

    return all_variants

def process_qr_image(image: Image.Image):
    """
    Detects and decodes QR codes in a PIL Image with strict payload verification.
    If an image is blurry, corrupted, or unreadable and no valid payload text can be decoded,
    it returns an explicit error message and NEVER draws a false bounding box on the image.
    
    Returns:
        qr_detected (bool): True ONLY if a valid QR payload is decoded.
        decoded_info (str): Decoded text payload or explicit error message.
        annotated_img (PIL.Image): Original image (unannotated if unreadable, green box if valid payload).
    """
    img_rgb = image.convert("RGB")
    img_np = np.array(img_rgb)
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    annotated_bgr = img_bgr.copy()
    
    qr_detected = False
    decoded_info = ""
    pts = None

    variants = get_image_variants(img_rgb)

    # --- Strategy 1: ZXing C++ Engine (Requires Verified Payload Text) ---
    if HAS_ZXING:
        binarizers = [
            zxingcpp.Binarizer.LocalAverage,
            zxingcpp.Binarizer.GlobalHistogram,
            zxingcpp.Binarizer.FixedThreshold
        ]

        for var_name, var_mat, scale in variants:
            for bin_type in binarizers:
                try:
                    results = zxingcpp.read_barcodes(
                        var_mat,
                        try_rotate=True,
                        try_downscale=False,
                        try_invert=True,
                        binarizer=bin_type,
                        return_errors=False   # STRICT: Do not return unverified error boxes
                    )
                except Exception:
                    results = []

                if results:
                    for r in results:
                        # STRICT REQUIREMENT: Must have a valid non-empty decoded text payload!
                        if r.text and len(r.text.strip()) > 0 and r.format in [zxingcpp.BarcodeFormat.QRCode, zxingcpp.BarcodeFormat.MicroQRCode]:
                            qr_detected = True
                            decoded_info = r.text.strip()
                            pos = r.position
                            
                            # Map coordinates back to original scale
                            raw_pts = np.array([
                                [pos.top_left.x, pos.top_left.y],
                                [pos.top_right.x, pos.top_right.y],
                                [pos.bottom_right.x, pos.bottom_right.y],
                                [pos.bottom_left.x, pos.bottom_left.y]
                            ], dtype=np.float32)
                            
                            pts = (raw_pts / scale).astype(np.int32)
                            break
                if qr_detected:
                    break
            if qr_detected:
                break

    # --- Strategy 2: OpenCV QRCodeDetector (Fallback with strict payload check) ---
    if not qr_detected:
        detector = cv2.QRCodeDetector()
        for var_name, var_mat, scale in variants:
            try:
                cv_decoded, cv_points, _ = detector.detectAndDecode(var_mat)
            except Exception:
                cv_decoded, cv_points = None, None

            # STRICT REQUIREMENT: cv_decoded must be non-empty!
            if cv_decoded and len(cv_decoded.strip()) > 0 and cv_points is not None and len(cv_points) > 0:
                cv_pts = cv_points.astype(np.float32).reshape(-1, 2)
                if len(cv_pts) >= 4:
                    qr_detected = True
                    decoded_info = cv_decoded.strip()
                    pts = (cv_pts / scale).astype(np.int32)
                    break

    # ONLY draw Bounding Box & Annotations if valid payload was verified
    if qr_detected and pts is not None and len(decoded_info) > 0:
        for i in range(len(pts)):
            cv2.line(annotated_bgr, tuple(pts[i]), tuple(pts[(i + 1) % len(pts)]), (0, 255, 0), 4)
        
        for pt in pts:
            cv2.circle(annotated_bgr, tuple(pt), 5, (0, 0, 255), -1)

        top_y = min([p[1] for p in pts])
        left_x = min([p[0] for p in pts])
        cv2.putText(annotated_bgr, "QR Code Decoded", (left_x, max(25, top_y - 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    else:
        qr_detected = False
        pts = None
        decoded_info = "Unable to decode QR code. The image is either blurry, corrupted, or unreadable to decode payload."

    annotated_rgb = cv2.cvtColor(annotated_bgr, cv2.COLOR_BGR2RGB)
    annotated_pil = Image.fromarray(annotated_rgb)

    return qr_detected, decoded_info, annotated_pil



def process_qr_detection(data_dir: str):
    """
    CLI processing function: reads images from data_dir and detects/decodes QR codes.
    """
    print(f"Starting QR code detection and decoding on directory: {data_dir}")
    if not os.path.exists(data_dir):
        print(f"Error: Directory {data_dir} does not exist.")
        return

    images = [f for f in os.listdir(data_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))]
    print(f"Found {len(images)} files to process in QR pipeline.")

    for img_name in images:
        img_path = os.path.join(data_dir, img_name)
        print(f"\nProcessing {img_name} for QR codes...")
        try:
            pil_img = Image.open(img_path)
            qr_detected, decoded_text, _ = process_qr_image(pil_img)
            
            print(f" -> Step 1: Locating QR code matrix...")
            print(f" -> Step 2: Extraction Status: {'Found' if qr_detected else 'Not Found'}")
            print(f" -> Step 3: Decoding payload...")
            print(f"Result for {img_name}: Decoded Payload: '{decoded_text}'")
        except Exception as e:
            print(f" -> Error processing {img_name}: {e}")

    print("\nQR code detection task completed.\n")


