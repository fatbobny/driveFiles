# IMPORTS
import time
import datetime
# Unused import removed: from pyasn1_modules.rfc2985 import pkcs_9_at_userPKCS12
import pushover_seb
import googleDriveAPI as drive
from basicfunctions import extract_json_content as get_json, load_ML_config, countdown
import logging
from drive_file import DriveFile
import pprint

# CONFIGURE LOGGING METHOD
logging.basicConfig(
    level=logging.WARNING,  # Log messages with severity INFO or higher
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),  # Log to a file
        # logging.StreamHandler()  # Log to the console (terminal)
    ]
                    )

# GET CONFIG DATA
pushover_creds = get_json('config/pushover_config.json')
folders_to_monitor_names = get_json('config/folders_to_monitor.json')
# folders_to_monitor_names = [{'folder_name': 'C_test'}]  # for testing
# folders_to_monitor_names = [{'folder_name': 'B_To Automate in Python'}]  # for testing

ML_config = get_json('config/config_machine_learning.json')
pdf_configs = get_json('config/config_pdf.json')

filter_mime_types = ['application/pdf', 'image/']


if __name__ == '__main__':
    # --- 1. INITIAL SETUP ---
    # Establish connection to Google Drive
    dm = drive.GoogleDriveFileManager(credentials_path='config/google_credentials.json',
                                      token_path='config/google_token.json')

    # Load the machine learning model and vectorizer
    ml_model, ml_vectorizer = load_ML_config(folder_models=ML_config['folder_models'],
                                             rootRegression=ML_config['rootRegression'],
                                             rootVectorizer=ML_config['rootVectorizer'],
                                             extensionModels=ML_config['extensionModels'])


    # --- 2. DEFINE THE CALLBACK FUNCTION ---
    def process_new_file(file_details: dict):
        """
        Callback function to process a single file.

        This function is triggered for each file and will:
        1. Initialize a DriveFile object.
        2. Call the rename_and_sort() method to process and organize the file.
        """
        file_id = file_details.get('file_id')
        file_name = file_details.get('file_name', 'N/A')
        logging.info(f"--- CALLBACK: Processing file {file_name} (ID: {file_id}). ---")
        try:
            # Reload the config file
            pdf_configs = get_json('config/config_pdf.json')

            # Initialize the DriveFile object with all necessary components
            drive_file = DriveFile(file_details=file_details,
                                   drive_manager=dm,
                                   pdf_configs=pdf_configs,
                                   ml_model=ml_model,
                                   ml_vectorizer=ml_vectorizer,
                                   pushover_creds=pushover_creds
                                   )

            # Get and print the extraction review
            extraction_review = drive_file.review_extraction()
            pprint.pprint(extraction_review)

            # Trigger the main processing logic for the file
            drive_file.rename_and_sort()
            logging.info(f"--- CALLBACK: Successfully processed file {file_details.get('file_name')} (ID: {file_id}). ---")

        except Exception as e:
            logging.error(f"--- CALLBACK: An error occurred while processing file {file_id}: {e} ---", exc_info=True)


    # --- 3. START THE PROCESS ---
    # Get the IDs of the folders you want to process
    # Check if 'My Drive' is in the list and handle it specially
    if any(f['folder_name'] == 'My Drive' for f in folders_to_monitor_names):

        # Remove 'My Drive' from the list passed to the method
        filtered_folders = [f for f in folders_to_monitor_names if f['folder_name'] != 'My Drive']
        folders_to_monitor_ids = dm.get_folder_to_monitor_ids(filtered_folders)

        # Add 'root' to the list of IDs
        folders_to_monitor_ids.append('root')
        root_name = dm.get_file_or_folder_name('root')
        logging.info(f"* {root_name}")
        print(f"* {root_name}")
    else:
        folders_to_monitor_ids = dm.get_folder_to_monitor_ids(folders_to_monitor_names)

    # Start fetching and processing files from the folders in a loop
    logging.info("Starting to fetch and process files...")
    while True:
        now = datetime.datetime.now()
        european_time = now.strftime("%d/%m/%Y %H:%M:%S")
        # print(f"\n--- New loop at {european_time} ---")
        logging.info(f"--- New loop at {european_time} ---")

        dm.fetch_and_process_files_in_folders(
            folder_ids=folders_to_monitor_ids,
            on_file_callback=process_new_file,
            filter_mime_types=filter_mime_types,
        )

        time_step = 30

        logging.info(f"Waiting {time_step} seconds before next refresh...")
        # print("--- Loop finished. Waiting 30 seconds before next refresh... ---")
        countdown(time_step)
