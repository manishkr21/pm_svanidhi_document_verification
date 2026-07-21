import os
import sys
import argparse
from modules.ai_detection import process_ai_detection
from modules.qr_detection import process_qr_detection
from modules.edit_detection import process_edit_detection

# Define base paths
BASE_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
AI_DATA_DIR = os.path.join(BASE_DATA_DIR, "ai_detection_images")
QR_DATA_DIR = os.path.join(BASE_DATA_DIR, "qr_detection")
EDIT_DATA_DIR = os.path.join(BASE_DATA_DIR, "edited_images")

def main():
    parser = argparse.ArgumentParser(description="Image Processing & Detection Pipeline CLI / GUI Launcher")
    
    parser.add_argument(
        "--task",
        choices=["ai", "qr", "edit", "all", "gui"],
        required=False,
        default="all",
        help="Specify task to execute: 'ai' (AI image detection), 'qr' (QR code detection), 'edit' (edited image detection), 'all' (run all), or 'gui' (launch Streamlit UI)."
    )
    
    args = parser.parse_args()

    if args.task == "gui":
        print("Launching Streamlit Web Application...")
        app_path = os.path.join(os.path.dirname(__file__), "app.py")
        os.system(f"{sys.executable} -m streamlit run {app_path}")
        return

    if args.task == "ai":
        process_ai_detection(AI_DATA_DIR)
    elif args.task == "qr":
        process_qr_detection(QR_DATA_DIR)
    elif args.task == "edit":
        process_edit_detection(EDIT_DATA_DIR)
    elif args.task == "all":
        print("Running all pipeline tasks sequentially...\n")
        process_ai_detection(AI_DATA_DIR)
        process_qr_detection(QR_DATA_DIR)
        process_edit_detection(EDIT_DATA_DIR)

if __name__ == "__main__":
    main()

