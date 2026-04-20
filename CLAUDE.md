# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

A Google Drive file automation system that monitors specified folders, extracts text from PDFs/images via OCR, classifies files using keyword rules or a trained ML model, then renames and moves them into the correct folder hierarchy.

## Running the project

```bash
# Start the monitoring loop (runs indefinitely, checks every 30 seconds)
python main.py

# Train ML classification models from existing Drive folder structure
cd machine_learning && python training.py

# Generate training data from existing Drive folders
python create_learning_material.py
```

There are no automated tests. The project uses a `.venv` virtual environment.

## Architecture

**Data flow**: `main.py` runs an infinite loop → `fetch_and_process_files_in_folders()` finds new PDFs/images → `DriveFile` classifies and determines target path → `rename_and_sort()` applies changes on Drive → Pushover notification sent.

### Key modules

- **`main.py`** — Entry point. Initializes Drive connection + ML models, defines `process_new_file()` callback, runs the monitoring loop.
- **`drive_file.py`** — `DriveFile` class. Given extracted text and file metadata, determines the target filename (date-based) and folder path (config rule → ML fallback), then executes the rename/move.
- **`googleDriveAPI/__init__.py`** — `GoogleDriveFileManager` class (~680 lines). All Drive API interactions: listing, downloading, renaming, moving, folder creation with path cache, OCR extraction, and the monitoring loop logic. Uses exponential backoff for rate limits.
- **`machine_learning/training.py`** — `DriveModelTrainer`. Recursively extracts text from Drive files, trains `TfidfVectorizer + LogisticRegression`, saves `.sav` models.
- **`basicfunctions/__init__.py`** — Utilities: JSON loading, ML model loading (finds latest `.sav` file), date arithmetic.

### Classification logic in `DriveFile`

1. `_get_file_config()` — Scans all entries in `config_pdf.json`; returns the first entry where **all** keywords appear in the extracted text.
2. `_get_folder_path()` — Uses `target_folder` from config (optionally appending the year). Falls back to ML model prediction if no config match.
3. `_get_date_for_file_name()` — Applies regex patterns from the matched config entry to extract a date string from the text; uses `dateparser` for parsing.

## Configuration files (`config/`)

| File | Purpose |
|------|---------|
| `config_app.json` | OCR DPI, max pages, download base path, date string regex fixes |
| `config_pdf.json` | Array of file type definitions — keywords, regex patterns, target folder, filename template |
| `config_machine_learning.json` | Paths to trained model files |
| `folders_to_monitor.json` | Which Drive folders to watch |
| `google_credentials.json` | OAuth client secret (not committed) |
| `google_token.json` | User OAuth token (not committed) |
| `pushover_config.json` | Pushover notification credentials (not committed) |

### `config_pdf.json` entry structure

```json
{
  "keywords": ["keyword1", "keyword2"],   // ALL must appear in extracted text
  "regex_date": [{"regex_string": "..."}],
  "filename_base": "Company - document type",
  "filename_datetype": "day|month|quarter|year",
  "target_folder": "Path/On/Drive",
  "target_folder_add_year": true          // Appends /YYYY to target_folder
}
```

## OCR and text extraction

Two extraction methods are available in `GoogleDriveFileManager`:
- `extract_text_from_pdf()` — pdf2image + pytesseract (image-based OCR, respects `max_pages_for_ocr`)
- `extract_text_with_actual_newlines_from_pdf()` — PyMuPDF (`fitz`), layout-preserving for native-text PDFs

The main processing flow uses the OCR method by default.

## ML model training

Models are stored in `machine_learning/models/` as paired `.sav` files (vectorizer + classifier). `basicfunctions.load_ML_config()` automatically finds the latest file matching the configured prefix. Training scans the live Drive folder structure — the folder path becomes the label for each file's extracted text.
