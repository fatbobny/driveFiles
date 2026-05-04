import time
import datetime
import logging
import pushover_seb
import googleDriveAPI as drive
from basicfunctions import extract_json_content as get_json, load_ML_config, countdown
from drive_file import DriveFile

POLL_INTERVAL_SECONDS = 30

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler(),
    ]
)

pushover_creds = get_json('config/pushover_config.json')
folders_to_monitor_names = get_json('config/folders_to_monitor.json')
ML_config = get_json('config/config_machine_learning.json')
pdf_configs = get_json('config/config_pdf.json')

filter_mime_types = ['application/pdf', 'image/']


if __name__ == '__main__':
    # --- 1. INITIAL SETUP ---
    dm = drive.GoogleDriveFileManager(credentials_path='config/google_credentials.json',
                                      token_path='config/google_token.json')

    ml_model, ml_vectorizer = load_ML_config(folder_models=ML_config['folder_models'],
                                             rootRegression=ML_config['rootRegression'],
                                             rootVectorizer=ML_config['rootVectorizer'],
                                             extensionModels=ML_config['extensionModels'])

    # --- 2. DEFINE THE CALLBACK FUNCTION ---
    def process_new_file(file_details: dict):
        """Callback triggered for each new file found in the monitored folders."""
        file_id = file_details.get('file_id')
        file_name = file_details.get('file_name', 'N/A')
        logging.info(f"--- CALLBACK: Processing file {file_name} (ID: {file_id}). ---")
        try:
            # Reload config on every call so changes take effect without restarting.
            pdf_configs = get_json('config/config_pdf.json')

            drive_file = DriveFile(file_details=file_details,
                                   drive_manager=dm,
                                   pdf_configs=pdf_configs,
                                   ml_model=ml_model,
                                   ml_vectorizer=ml_vectorizer,
                                   pushover_creds=pushover_creds)

            print(drive_file.review_extraction())
            drive_file.rename_and_sort()
            logging.info(f"--- CALLBACK: Successfully processed file {file_name} (ID: {file_id}). ---")

        except Exception as e:
            logging.error(f"--- CALLBACK: Error processing file {file_id}: {e} ---", exc_info=True)

    # --- 3. START THE PROCESS ---
    if any(f['folder_name'] == 'My Drive' for f in folders_to_monitor_names):
        filtered_folders = [f for f in folders_to_monitor_names if f['folder_name'] != 'My Drive']
        folders_to_monitor_ids = dm.get_folder_to_monitor_ids(filtered_folders)
        folders_to_monitor_ids.append('root')
        logging.info(f"* {dm.get_file_or_folder_name('root')}")
    else:
        folders_to_monitor_ids = dm.get_folder_to_monitor_ids(folders_to_monitor_names)

    logging.info("Starting to fetch and process files...")
    while True:
        now = datetime.datetime.now()
        logging.info(f"--- New loop at {now.strftime('%d/%m/%Y %H:%M:%S')} ---")

        dm.fetch_and_process_files_in_folders(
            folder_ids=folders_to_monitor_ids,
            on_file_callback=process_new_file,
            filter_mime_types=filter_mime_types,
        )

        logging.info(f"Waiting {POLL_INTERVAL_SECONDS} seconds before next refresh...")
        countdown(POLL_INTERVAL_SECONDS)
