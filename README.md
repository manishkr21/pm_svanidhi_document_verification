# Aadhar OCR Verification Pipeline

A minimal yet robust Python-based document pipeline that loads identity documents, extracts text using Optical Character Recognition (OCR), finds Aadhar numbers, and performs multi-layered verification (including formats, Verhoeff checksums, file metadata analysis, and cryptographic QR signature validation).

## Features

- **Automated Loading**: Scans directories and loads PDF and image files (`.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp`).
- **OCR Text Extraction**: Employs Tesseract OCR to read characters from images, with an adaptive thresholding fallback (OpenCV) for hard-to-read texts.
- **Selectable Text & Rendering for PDFs**: Directly parses selectable text using PyPDF2, rendering pages to temporary images when necessary.
- **Verhoeff Checksum**: Computes digits using the Verhoeff algorithm to identify adjacent transpositions and single-digit errors.
- **Metadata Forgery Detection**: Evaluates EXIF tags on images and creator/modification entries on PDFs to detect software traces (e.g., Photoshop, GIMP) or unauthorized changes.
- **Cryptographic Verification**: Scans for Aadhaar secure QR codes, decompresses the payload, and cryptographically checks the 256-byte RSA signature block against official UIDAI public key certificates.
- **Performance Optimizations**:
  - **PDF Extraction Caching**: Caches rendered PDF pages globally during execution, cutting processing time in half.
  - **QR Scan Caching**: Prevents re-scanning the same image files multiple times.
  - **Detector-level Caching**: Caches metadata and QR validation per file path to avoid redundant checks.

## Project Structure

```text
pms-prototype/
├── main.py                      # CLI entry point
├── fake_doc_detector/
│   ├── config/                  # Configuration profiles & environment loader
│   ├── core/                    # Pipeline runner, data structures & PDF helpers
│   ├── detectors/               # Formats, Verhoeff, Metadata, OCR & QR checkers
│   └── loaders/                 # Directory loader for local files
├── data/sample_documents/       # Target directories for input documents
├── public keys/                 # UIDAI official public key certificates (.cer)
├── requirements.txt             # Runtime dependencies
└── README.md                    # Project documentation
```

## Detailed Execution Flow

For an in-depth explanation of components, execution stages, and sequence diagram, see the [Codeflow and Architecture Layout](codeflow.md).

## Installation & Setup

1. **Clone/Download the repository** to your local workspace.
2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Install OS Dependencies**:
   - **Tesseract OCR**: Make sure `tesseract` is installed on your OS and added to your system `PATH`.
   - **pdftoppm** (recommended for PDF page rendering): Typically included in packages like `poppler-utils` (Linux/macOS).

4. **Verify certificates**: Place UIDAI public key certificates (`.cer` or `.pem`) in the `public keys` directory, and specify them inside your `.env` file (already pre-configured).

## Execution

To execute the pipeline:

```bash
# Process all loaded documents
python main.py

# Process only Aadhar documents
python main.py aadhar
```

## Output & Reports

The pipeline outputs logs of files processed and generates a structured, wrapped text table in the console showing validation details, confidence ratings, and overall status (`VALID` or `POTENTIALLY_FAKE`).
