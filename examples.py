import pushover_seb
import googleDriveAPI as Drive
from basicfunctions import extract_json_content as get_json
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Log messages with severity INFO or higher
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),  # Log to a file
        logging.StreamHandler()  # Log to the console (terminal)
            ]
)


# get config data
pushover_creds = get_json('config/pushover_config.json')


if __name__ == '__main__':

    # # Test case 1 : send pushover_seb message
    # pushover_seb.pushover_send( 'Test 2', 'This is a test', pushover_creds['API'], pushover_creds['user'])

    # initiate
    drive_manager = Drive.GoogleDriveFileManager(credentials_path='config/google_credentials.json',
                                           token_path='config/google_token.json')

    # Get ID from Path
    path = 'Documents/Patrimoine & Finances/2. Releves bancaires/AMEX FR'
    id2 = drive_manager.find_folder_id_by_path(path)
    print(id2)
    print(drive_manager.get_folder_details(folder_id=id2))

