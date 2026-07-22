# pyrefly: ignore [missing-import]
import streamlit as st
import os
import io
import numpy as np
from PIL import Image

# Import detection modules
from modules.ai_detection import load_model, predict_ai_image, detect_face
from modules.qr_detection import process_qr_image
from modules.edit_detection import process_edit_image

# ----------------------------------------------------
# Streamlit Page Configuration & Styling
# ----------------------------------------------------
st.set_page_config(
    page_title="Image Intelligence & Detection Platform",
    page_icon="🔍",
    layout="wide"
)

st.markdown(
    """
    <style>
    body {
        background-color: #FFFFFF;
        color: #000000;
        font-family: Arial, sans-serif;
    }
    .stApp {
        background-color: #FFFFFF;
        padding: 10px 20px;
    }
    .stFileUploader, .stButton>button {
        background-color: #F0F0F0 !important;
        color: #000000 !important;
        font-size: 16px;
        border-radius: 10px;
        transition: 0.3s;
    }
    .stButton>button:hover {
        background-color: #FFD700 !important;
        color: #000000 !important;
    }
    .stAlert, .stSuccess, .stError, .stWarning {
        border-radius: 10px;
    }
    .result-box {
        background-color: #F8F8F8;
        padding: 20px;
        border-radius: 12px;
        text-align: center;
        box-shadow: 2px 2px 12px rgba(0, 0, 0, 0.08);
        border: 1px solid #E5E5E5;
        margin-top: 15px;
        margin-bottom: 15px;
    }
    .step-card {
        background-color: #F4F6F9;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #FFD700;
        margin-bottom: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Base sample directories
BASE_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
AI_DATA_DIR = os.path.join(BASE_DATA_DIR, "ai_detection_images")
QR_DATA_DIR = os.path.join(BASE_DATA_DIR, "qr_detection")
EDIT_DATA_DIR = os.path.join(BASE_DATA_DIR, "edited_images")

# Ensure data directories exist
for d in [AI_DATA_DIR, QR_DATA_DIR, EDIT_DATA_DIR]:
    os.makedirs(d, exist_ok=True)

# ----------------------------------------------------
#Sidebar Navigation & Module Selection
# ----------------------------------------------------
st.sidebar.markdown("<h2 style='color: #1E1E1E;'>Control Center</h2>", unsafe_allow_html=True)

selected_module = st.sidebar.radio(
    "Select Detection Task:",
    [
        "AI / Deepfake Image Detection",
        "QR Code Detection & Decoding",
        "Edited Image Detection"
    ],
    index=0
)

st.sidebar.markdown("---")

# Helper function to get sample images
def get_sample_images(folder_path):
    if not os.path.exists(folder_path):
        return []
    return [f for f in os.listdir(folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))]

# ----------------------------------------------------
# AI / Deepfake Image Detection View
# ----------------------------------------------------
if selected_module == "AI / Deepfake Image Detection":
    st.markdown("<h1 style='text-align: center; color: #D4AF37;'>AI & Deepfake Image Detector</h1>", unsafe_allow_html=True)
    st.write("Upload an image or pick a sample to analyze whether it is **AI-Generated / GAN-Generated** or **Real**.")
    
    st.sidebar.markdown("### AI Model Settings")
    real_threshold = st.sidebar.slider(
        " Real Confidence Threshold",
        min_value=0.0,
        max_value=1.0,
        value=0.50,
        step=0.05,
        help="Higher threshold requires the model to be more confident to classify as Real."
    )
    st.sidebar.info("**Model Info**: Uses PyTorch MobileNetV3 classifier trained for GAN & Deepfake face detection.")

    # Input Method Selection
    input_method = st.radio("Choose image source:", ["Upload Image", "Use Sample Image"], horizontal=True, key="ai_source")
    image_to_process = None

    if input_method == "Upload Image":
        uploaded_file = st.file_uploader(" Upload Image for AI Detection", type=["jpg", "png", "jpeg", "webp"], key="ai_upload")
        if uploaded_file is not None:
            image_to_process = Image.open(uploaded_file).convert("RGB")
    else:
        samples = get_sample_images(AI_DATA_DIR)
        if samples:
            selected_sample = st.selectbox("Select a sample image from data/", samples, key="ai_sample")
            if selected_sample:
                sample_path = os.path.join(AI_DATA_DIR, selected_sample)
                image_to_process = Image.open(sample_path).convert("RGB")
        else:
            st.warning("No sample images found in `data/ai_detection_images/`. Please upload an image.")

    if image_to_process is not None:
        col1, col2 = st.columns([1, 1])
        with col1:
            st.image(image_to_process, caption="Source Image", use_container_width=True)

        with col2:
            st.markdown("### Detection Analysis")
            with st.spinner("Running face detection & deepfake analysis..."):
                face_detected, cropped_face = detect_face(image_to_process)
                model = load_model()

            if not model:
                st.error("Model file (`mobilenet_best (3).pth`) not found or could not be loaded!")
            else:
                if face_detected:
                    st.success("Face detected! Analyzing facial features...")
                    target_image = cropped_face
                else:
                    # st.warning("No distinct face detected. Analyzing overall image...")
                    target_image = image_to_process

                progress_bar = st.progress(0)
                for i in range(100):
                    progress_bar.progress(i + 1)

                prediction, real_score, gan_score = predict_ai_image(target_image, model, real_threshold)

                st.markdown(f"""
                    <div class='result-box'>
                        <h2 style='color: #D4AF37;'>Result: {prediction}</h2>
                        <p><b>Score Breakdown:</b></p>
                        <p> <b>Real Confidence:</b> {real_score:.4f} &nbsp;|&nbsp;  <b>GAN/AI Confidence:</b> {gan_score:.4f}</p>
                    </div>
                """, unsafe_allow_html=True)

                if prediction == "Real":
                    st.success(" This image is classified as **REAL**! ")
                else:
                    st.error(" This image is classified as **AI / GAN-Generated**! ")

# ----------------------------------------------------
# QR Code Detection & Decoding View
# ----------------------------------------------------
elif selected_module == "QR Code Detection & Decoding":
    st.markdown("<h1 style='text-align: center; color: #1E88E5;'>QR Code Detector & Decoder</h1>", unsafe_allow_html=True)
    st.write("Detect, locate bounding boxes, and decode hidden text/URL payloads from QR codes.")

    st.sidebar.info(" Uses OpenCV QR Code Detector to find matrix locations and decode payload content.")

    input_method = st.radio("Choose image source:", ["Upload Image", "Use Sample Image"], horizontal=True, key="qr_source")
    image_to_process = None

    if input_method == "Upload Image":
        uploaded_file = st.file_uploader(" Upload Image containing QR Code", type=["jpg", "png", "jpeg", "webp"], key="qr_upload")
        if uploaded_file is not None:
            image_to_process = Image.open(uploaded_file)
    else:
        samples = get_sample_images(QR_DATA_DIR)
        if samples:
            selected_sample = st.selectbox("Select a sample image from data/", samples, key="qr_sample")
            if selected_sample:
                sample_path = os.path.join(QR_DATA_DIR, selected_sample)
                image_to_process = Image.open(sample_path)
        else:
            st.warning("No sample images found in `data/qr_detection/`. Please upload an image.")

    if image_to_process is not None:
        col1, col2 = st.columns([1, 1])
        with col1:
            st.image(image_to_process, caption="Source Image", use_container_width=True)

        with col2:
            st.markdown("### QR Code Pipeline")
            with st.spinner("Scanning for QR code pattern..."):
                qr_detected, decoded_payload, annotated_img = process_qr_image(image_to_process)

            st.markdown("""
                <div class='step-card'>
                    <b>Step 1:</b> Locating QR matrix bounding box<br>
                    <b>Step 2:</b> Normalizing perspective & thresholding<br>
                    <b>Step 3:</b> Decoding data payload
                </div>
            """, unsafe_allow_html=True)

            if qr_detected:
                st.success(" QR Code Detected!")
                st.image(annotated_img, caption=" Detected & Annotated QR Code", use_container_width=True)
                
                st.markdown(f"""
                    <div class='result-box'>
                        <h3 style='color: #1E88E5;'>Decoded Payload</h3>
                        <p style='font-size: 18px; word-break: break-all;'><code>{decoded_payload}</code></p>
                    </div>
                """, unsafe_allow_html=True)
           # ----------------------------------------------------
# Edited / Manipulated Image Detection View
# ----------------------------------------------------
elif selected_module == "Edited Image Detection":
    st.markdown("<h1 style='text-align: center; color: #b96333;'>Multi-Signal Image Forensics Detector</h1>", unsafe_allow_html=True)
    st.write("Detect digital edits, retouching, splicing, and cloning using **TruFor Deep Learning Architecture** integrated with a 6-signal heuristic forensics pipeline.")

    st.sidebar.info(" Powered by TruFor Deep Learning (CMX + Noiseprint++) fused with Adaptive ELA, Noise Outliers, DCT Energy, Edge Density, ORB Copy-Move, and EXIF/XMP Metadata.")

    input_method = st.radio("Choose image source:", ["Upload Image", "Use Sample Image"], horizontal=True, key="edit_source")
    image_to_process = None

    if input_method == "Upload Image":
        uploaded_file = st.file_uploader(" Upload Image for Edit Detection", type=["jpg", "png", "jpeg", "webp"], key="edit_upload")
        if uploaded_file is not None:
            image_to_process = Image.open(uploaded_file)
    else:
        samples = get_sample_images(EDIT_DATA_DIR)
        if samples:
            selected_sample = st.selectbox("Select a sample image from data/", samples, key="edit_sample")
            if selected_sample:
                sample_path = os.path.join(EDIT_DATA_DIR, selected_sample)
                image_to_process = Image.open(sample_path)
        else:
            st.warning("No sample images found in `data/edited_images/`. Please upload an image.")

    if image_to_process is not None:
        with st.spinner("Running TruFor Deep Learning & Multi-Signal Forensics Analysis..."):
            res = process_edit_image(image_to_process)
            is_edited, edit_score, ela_img, summary, details = res

        # Display TruFor Visual Maps & Heuristic Visualizations
        st.markdown("### Visual Localization & Forensic Maps")
        if details.get("trufor_map") is not None:
            c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
            with c1:
                st.image(image_to_process, caption="Source Image", use_container_width=True)
            with c2:
                st.image(details["trufor_map"], caption=" TruFor Forgery Heatmap", use_container_width=True)
            with c3:
                st.image(details["trufor_conf"], caption=" TruFor Confidence Map", use_container_width=True)
            with c4:
                st.image(ela_img, caption=" Adaptive ELA Mask", use_container_width=True)
        else:
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                st.image(image_to_process, caption="Source Image", use_container_width=True)
            with c2:
                st.image(ela_img, caption=" Adaptive ELA Mask", use_container_width=True)
            with c3:
                st.image(details["clone_img"], caption="Copy-Move Clone Map", use_container_width=True)

        st.markdown(f"""
            <div class='result-box'>
                <h2 style='color: {"#E53935" if is_edited else "#4CAF50"};'>{" Edit / Manipulation Detected" if is_edited else " Image Appears Unedited"}</h2>
                <p><b>Fused Manipulation Probability:</b> {edit_score:.2f} / 1.00 &nbsp;|&nbsp; <b>TruFor Deep Learning Score:</b> {details.get('trufor_score', 0.0):.2f}</p>
            </div>
        """, unsafe_allow_html=True)

        st.markdown("### Forensic Signals Breakdown")
        m0, m1, m2, m3, m4, m5, m6 = st.columns(7)
        with m0:
            st.metric("TruFor DL", f"{details.get('trufor_score', 0.0):.2f}")
        with m1:
            st.metric("Adaptive ELA", f"{details.get('ela_score', 0.0):.2f}")
        with m2:
            st.metric("Noise Outliers", f"{details.get('noise_score', 0.0):.2f}")
        with m3:
            st.metric("DCT Energy", f"{details.get('dct_score', 0.0):.2f}")
        with m4:
            st.metric("Edge Density", f"{details.get('edge_score', 0.0):.2f}")
        with m5:
            st.metric("Copy-Move", f"{details.get('clone_score', 0.0):.2f}")
        with m6:
            st.metric("Metadata", "Detected" if details.get('meta_score', 0.0) > 0 else "Clean")

        if details.get('soft_list'):
            st.warning(f" Editing Signature / Software Tag Detected: `{', '.join(details['soft_list'])}`")


