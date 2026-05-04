import googleDriveAPI as Drive
from basicfunctions import extract_json_content as get_json
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

if __name__ == '__main__':
    drive_manager = Drive.GoogleDriveFileManager(credentials_path='config/google_credentials.json',
                                                 token_path='config/google_token.json')

    # Example: look up a folder by path
    path = 'Documents/Patrimoine & Finances/2. Releves bancaires/AMEX FR'
    folder_id = drive_manager.find_folder_id_by_path(path)
    print(folder_id)
    print(drive_manager.get_folder_details(folder_id=folder_id))
