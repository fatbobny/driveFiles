import pprint
import time
import os
import io
import random
from types import NoneType
import basicfunctions
import datetime
import tempfile
import fitz  # pip install pymupdf
import logging
from PIL import Image
import pytesseract  # pip install pytesseract
from pdf2image import convert_from_path # pip install pdf2image

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.auth.exceptions import RefreshError

class GoogleDriveFileManager:
    """
    A class to manage files and folders in Google Drive using the Google Drive API.
    """

    def __init__(self, credentials_path: str, token_path: str, scopes=None):
        """Initializes the GoogleDriveFileManager."""
        if scopes is None:
            scopes = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/drive.activity']
        creds = None

        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, scopes)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError as e:
                    logging.info(f"Error refreshing token: {e}")
                    logging.info("Deleting token file and re-authenticating...")
                    os.remove(token_path)
                    creds = None

            if not creds:
                from google_auth_oauthlib.flow import InstalledAppFlow
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes)
                creds = flow.run_local_server(port=0)

            with open(token_path, "w") as token:
                token.write(creds.to_json())

        self.drive_service = build("drive", "v3", credentials=creds)
        self.activity_service = build("driveactivity", "v2", credentials=creds)

    def find_folder_id_by_name(self, folder_name, parent_folder_id=None):
        """Finds the ID of a folder by its name."""
        try:
            q = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
            if parent_folder_id:
                q += f" and '{parent_folder_id}' in parents"
            q += " and trashed = false"

            results = (
                self.drive_service.files()
                .list(q=q, fields="nextPageToken, files(id, name)")
                .execute()
            )
            items = results.get("files", [])

            if not items:
                return None
            elif len(items) > 1:
                logging.info(f"Warning: Multiple folders found with name '{folder_name}'.  Returning the first one.")
            return items[0]["id"]

        except HttpError as error:
            logging.ERROR(f"An error occurred: {error}")
            return None

    def find_folder_id_by_path(self, folder_path):
        """Finds the ID of a folder given its path from the root of Google Drive."""
        current_folder_id = 'root'
        path_parts = folder_path.split("/")
        path_parts = [part for part in path_parts if part]

        for folder_name in path_parts:
            current_folder_id = self.find_folder_id_by_name(folder_name, parent_folder_id=current_folder_id)
            if current_folder_id is None:
                return None

        return current_folder_id

    def get_file_or_folder_name(self, file_or_folder_id):
        """Gets the name of a file or folder given its ID."""
        try:
            file = self.drive_service.files().get(fileId=file_or_folder_id, fields='name').execute()
            return file.get('name')

        except HttpError as error:
            logging.ERROR(f"An error occurred: {error}")
            return None

    def get_parent_folder_id(self, file_or_folder_id):
        """Gets the ID of the parent folder of a given file or folder."""
        try:
            file = self.drive_service.files().get(fileId=file_or_folder_id, fields='parents').execute()
            parents = file.get('parents')

            if not parents:
                return "root"
            else:
                return parents[0]

        except HttpError as error:
            logging.ERROR(f"An error occurred: {error}")
            return None

    def get_folder_details(self, folder_name=None, folder_id=None, parent_folder_id=None):
        if folder_name:
            folder_id = self.find_folder_id_by_name(folder_name, parent_folder_id=parent_folder_id)
            logging.info(f"Folder ID: {folder_id}")
        logging.info(f"Getting folders info for folder path: {self.get_path_from_id(folder_id)}")

        files = self.list_files_in_folder(folder_id=folder_id)
        logging.info('Folder files:')
        for file in files:
            logging.info(f'File ID: {file}')
            logging.info(f'File name: {file["name"]}')

        parent_id = self.get_parent_folder_id(folder_id)
        parent_name = self.get_file_or_folder_name(parent_id)
        logging.info(f"Folder parent: {parent_name}")
        logging.info('')

    def get_path_from_id(self, file_or_folder_id):
        """Gets the full path of a file or folder from its ID."""
        try:
            current_id = file_or_folder_id
            path_parts = []

            while True:
                name = self.get_file_or_folder_name(current_id)
                if name is None:
                    return None

                path_parts.insert(0, name)
                parent_id = self.get_parent_folder_id(current_id)

                if parent_id == "root" or parent_id is None:
                    break

                current_id = parent_id

            return "/".join(path_parts)

        except HttpError as error:
            logging.ERROR(f"An error occurred: {error}")
            return None

    def list_files_in_folder(self, folder_id=None, file_name=None):
        """Lists files..."""
        try:
            q = "trashed = false"
            if folder_id:
                q += f" and '{folder_id}' in parents"
            if file_name:
                q += f" and name contains '{file_name}'"

            all_items = []
            page_token = None

            while True:
                results = (
                    self.drive_service.files()
                    .list(q=q, fields="nextPageToken, files(id, name, mimeType)", pageToken=page_token)
                    .execute()
                )
                items = results.get("files", [])
                all_items.extend(items)

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

            return all_items

        except HttpError as error:
            logging.ERROR(f"An error occurred: {error}")
            return []

    def create_folder(self, folder_name, parent_folder_id=None):
        """Creates a folder..."""
        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_folder_id:
                file_metadata['parents'] = [parent_folder_id]

            file = self.drive_service.files().create(body=file_metadata, fields='id').execute()
            logging.info(
                f"File {self.get_file_or_folder_name(file.get('id'))} in folder {self.get_file_or_folder_name(self.get_parent_folder_id(file.get('id')))} created successfully.")
            return file.get('id')

        except HttpError as error:
            logging.ERROR(f"An error occurred: {error}")
            return None

    def create_folder_by_path(self, folder_path):
        """Creates a folder in Google Drive, creating any missing parent folders along the way."""
        path_parts = folder_path.split("/")
        path_parts = [part for part in path_parts if part]
        current_parent_id = 'root'
        some_folder_has_been_create = False

        for folder_name in path_parts:
            folder_id = self.find_folder_id_by_name(folder_name, parent_folder_id=current_parent_id)
            if folder_id is None:
                folder_id = self.create_folder(folder_name, parent_folder_id=current_parent_id)
                some_folder_has_been_create = True
                if folder_id is None:
                    logging.info(f"Failed to create folder '{folder_name}'")
                    return None
            current_parent_id = folder_id

        if not some_folder_has_been_create:
            logging.info(f'{folder_path} already exists')

        return current_parent_id

    def read_file(self, file_id, local_filepath=None):
        """Reads a file..."""
        try:
            request = self.drive_service.files().get_media(fileId=file_id)
            if local_filepath:
                with io.FileIO(local_filepath, "wb") as fh:
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while done is False:
                        status, done = downloader.next_chunk()
                        logging.info(f"Download {int(status.progress() * 100)}%.")
                return None
            else:
                file_content = request.execute()
                return file_content

        except HttpError as error:
            logging.ERROR(f"An error occurred: {error}")
            return None
        except IOError as e:
            logging.info(f"IO Error during download: {e}")
            return None

    def move_file(self, file_id, new_folder_id):
        """Moves a file..."""
        try:
            file = self.drive_service.files().get(fileId=file_id, fields='parents').execute()
            previous_parents = ",".join(file.get('parents'))
            file = self.drive_service.files().update(
                fileId=file_id,
                addParents=new_folder_id,
                removeParents=previous_parents,
                fields='id, parents'
            ).execute()
            logging.info(f"File with id '{file_id}' named {self.get_file_or_folder_name(file_id)} moved successfully.")
            return file

        except HttpError as error:
            logging.ERROR(f"An error occurred: {error}")
            return None

    def rename_file(self, file_id, new_name):
        """Renames a file in Google Drive."""
        try:
            file_metadata = {'name': new_name}
            updated_file = self.drive_service.files().update(
                fileId=file_id, body=file_metadata, fields='id, name'
            ).execute()
            logging.info(
                f"File with id '{file_id}' renamed to '{updated_file.get('name')}' successfully."
            )
            return updated_file

        except HttpError as error:
            logging.error(f"An error occurred: {error}")
            return None

    def delete_file(self, file_id):
        """Deletes a file..."""
        try:
            file_name = self.get_file_or_folder_name(file_id)
            self.drive_service.files().delete(fileId=file_id).execute()
            logging.info(f"File with id '{file_id}' named {file_name} deleted successfully.")

        except HttpError as error:
            logging.ERROR(f"An error occurred: {error}")

    def upload_file(self, local_filepath, folder_id=None, drive_filename=None):
        """Uploads a file..."""
        if not os.path.exists(local_filepath):
            raise FileNotFoundError(f"File not found: {local_filepath}")

        try:
            file_metadata = {'name': drive_filename or os.path.basename(local_filepath)}
            if folder_id:
                file_metadata['parents'] = [folder_id]

            media = MediaFileUpload(local_filepath)
            file = self.drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            logging.info(f'File ID: {file.get("id")}')
            return file.get('id')

        except HttpError as error:
            logging.ERROR(f"An error occurred: {error}")
            return None

    def get_file_content(self, file_id, mime_type, file_name):
        """Downloads file content."""
        try:
            request = self.drive_service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                logging.info(f"Download {int(status.progress() * 100)}%.")
            return fh.getvalue()
        except HttpError as error:
            logging.error(f"An error occurred during file download : {error}")
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred during file download: {e}")
            return None

    def extract_text_with_actual_newlines_from_pdf(self, pdf_path):
        """Extracts text from a PDF, preserving newlines as they appear in the PDF layout."""
        try:
            doc = fitz.open(pdf_path)
            all_text = ""
            for page in doc:
                blocks = page.get_text("blocks")
                for b in blocks:
                    block_text = b[4]
                    block_text = block_text.strip().replace('\n', ' ')
                    all_text += block_text + '\n'
            doc.close()
            return all_text.strip()
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            return None

    def extract_text_from_pdf(self, file_content, max_pages_for_ocr=4):
        """Extracts text from a PDF using the pdf2image and tesseract library."""
        DPI_for_OCR = 250
        try:
            with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as temp_pdf:
                temp_pdf.write(file_content)
                temp_pdf.flush()

                try:
                    pages = convert_from_path(temp_pdf.name, dpi=DPI_for_OCR, last_page=max_pages_for_ocr)
                except Exception as e:
                    logging.error(f"Error converting PDF to images with pdf2image: {e}")
                    logging.error("Please ensure poppler is installed and in your system's PATH.")
                    return None

            logging.info(f'Extracting text: Scanning up to {max_pages_for_ocr} pages')

            pdf_text = ''
            for page in pages:
                page_text = pytesseract.image_to_string(page)
                page_text = page_text.replace('-\n', '')
                pdf_text += page_text

            return pdf_text.strip()

        except Exception as e:
            logging.error(f"An unexpected error occurred during PDF text extraction: {e}")
            return None

    def extract_text_from_image(self, file_content):
        """Extracts text from an image file content."""
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp_image:
                temp_image.write(file_content)
                image_path = temp_image.name
            try:
                img = Image.open(image_path)
                text = pytesseract.image_to_string(img)
            except Exception as e:
                logging.error(f"Error processing image with Tesseract OCR: {e}")
                return None
            finally:
                os.unlink(image_path)

            return text.strip()
        except Exception as e:
            logging.error(f"An unexpected error occurred during image processing: {e}")
            return None

    def get_file_details_and_extract_content(self, file_id: str, max_pages_for_ocr: int = 5) -> dict:
        """Retrieves details for a single file, including extracted text content if applicable."""
        try:
            file_metadata = self.drive_service.files().get(
                fileId=file_id, fields='id, name, mimeType, parents'
            ).execute()

            file_name = file_metadata.get('name')
            mime_type = file_metadata.get('mimeType')
            parent_folder_id = file_metadata.get('parents', [None])[0]
            parent_folder_name = self.get_file_or_folder_name(parent_folder_id) if parent_folder_id else "My Drive"

            extracted_text = None
            error = None

            logging.info(f"Processing file: {file_name} (ID: {file_id}, Type: {mime_type})")

            if 'application/pdf' in mime_type or 'image/' in mime_type:
                file_content = self.get_file_content(file_id, mime_type, file_name)

                if file_content:
                    if 'application/pdf' in mime_type:
                        extracted_text = self.extract_text_from_pdf(file_content, max_pages_for_ocr)
                        if extracted_text is None:
                            error = f"Error extracting PDF content for {file_name}"
                            logging.error(error)
                        else:
                            logging.info(f'Text successfully extracted for {file_name}')

                    elif 'image/' in mime_type:
                        extracted_text = self.extract_text_from_image(file_content)
                        if extracted_text is None:
                            error = f"Error extracting image content for {file_name}"
                            logging.error(error)
                        else:
                            logging.info(f'Text successfully extracted for {file_name}')
                else:
                    error = f"Failed to get file content for {file_name}"
                    logging.error(error)
            else:
                logging.info(f"File type '{mime_type}' is not configured for text extraction.")

            return {
                'file_id': file_id,
                'file_name': file_name,
                'parent_folder_id': parent_folder_id,
                'parent_folder_name': parent_folder_name,
                'mime_type': mime_type,
                'extracted_text': extracted_text,
                'error': error
            }

        except HttpError as e:
            logging.error(f"An API error occurred while processing file ID {file_id}: {e}")
            return {
                'file_id': file_id, 'file_name': None, 'parent_folder_id': None,
                'parent_folder_name': None, 'mime_type': None, 'extracted_text': None,
                'error': f"API Error: {e}"
            }
        except Exception as e:
            logging.error(f"An unexpected error occurred while processing file ID {file_id}: {e}")
            return {
                'file_id': file_id, 'file_name': None, 'parent_folder_id': None,
                'parent_folder_name': None, 'mime_type': None, 'extracted_text': None,
                'error': f"Unexpected Error: {e}"
            }

    def get_files_and_extract_content_from_folders(self, folder_ids, filter_mime_types=None, max_pages_for_ocr=5):
        """Retrieves files from a list of folder IDs, filters them by MIME type, and extracts text content."""
        if filter_mime_types is None:
            filter_mime_types = ['application/pdf', 'image/']

        all_files_data = []

        for folder_id in folder_ids:
            try:
                folder_name = self.get_file_or_folder_name(folder_id)
                logging.info(f"--- Extracting files data in folder '{folder_name}' (ID: {folder_id}) ---")
                print(f"--- Extracting files data in folder '{folder_name}' ---")
            except Exception as e:
                logging.error(f"Could not get folder name for ID {folder_id}: {e}")
                continue

            files_in_folder = self.list_files_in_folder(folder_id=folder_id)

            for file_summary in files_in_folder:
                file_id = file_summary['id']
                file_name = file_summary['name']
                mime_type = file_summary['mimeType']

                if any(filter_type in mime_type for filter_type in filter_mime_types):
                    file_details = self.get_file_details_and_extract_content(
                        file_id=file_id,
                        max_pages_for_ocr=max_pages_for_ocr
                    )
                    all_files_data.append(file_details)
                else:
                    logging.info(
                        f"Skipping file: {file_name} (ID: {file_id}, Type: {mime_type}) as it's not in the filtered types.")

            logging.info(f'+++ Obtained all files for {folder_name} +++')
            print(f'+++ Obtained all files for {folder_name} +++')

        logging.info('+++ Finished obtaining files for monitored folders +++')
        print('+++ Finished obtaining files for monitored folders +++')
        logging.info(f'*** Number of files processed: {len(all_files_data)} ***')
        print(f'*** Number of files processed: {len(all_files_data)} ***')
        for file_data in all_files_data:
            logging.info(f'* File name : {file_data.get("file_name", "N/A")}')
            print(f'* File name : {file_data.get("file_name", "N/A")}')

        return all_files_data

    def fetch_and_process_files_in_folders(self, folder_ids, on_file_callback=None, filter_mime_types=None, max_pages_for_ocr=5):
        """Fetches all files from a list of folder IDs and processes them using a callback."""
        if filter_mime_types is None:
            filter_mime_types = ['application/pdf', 'image/']

        all_files_data = []

        for folder_id in folder_ids:
            try:
                folder_name = self.get_file_or_folder_name(folder_id)
                logging.info(f"--- Processing files in folder '{folder_name}' (ID: {folder_id}) ---")
            except Exception as e:
                logging.error(f"Could not get folder name for ID {folder_id}: {e}")
                continue

            files_in_folder = self.list_files_in_folder(folder_id=folder_id)

            for file_summary in files_in_folder:
                file_id = file_summary['id']
                file_name = file_summary['name']
                mime_type = file_summary['mimeType']

                if any(filter_type in mime_type for filter_type in filter_mime_types):
                    file_details = self.get_file_details_and_extract_content(
                        file_id=file_id,
                        max_pages_for_ocr=max_pages_for_ocr
                    )
                    all_files_data.append(file_details)

                    if on_file_callback and callable(on_file_callback):
                        try:
                            logging.info(f"  - Executing callback for file: {file_name} (ID: {file_id})")
                            on_file_callback(file_details)
                        except Exception as e:
                            logging.error(f"  - Error executing callback for file_id {file_id}: {e}")
                else:
                    logging.info(
                        f"Skipping file: {file_name} (ID: {file_id}, Type: {mime_type}) as it's not in the filtered types.")

            logging.info(f'+++ Finished processing files for {folder_name} +++')

        logging.info('+++ Finished processing files for all folders +++')
        logging.info(f'*** Number of files processed: {len(all_files_data)} ***')

        return all_files_data

    def make_api_request(self, request_function, *args, **kwargs):
        """Makes an API request, handling rate limit errors with exponential backoff."""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                return request_function(*args, **kwargs)
            except HttpError as error:
                if error.resp.status in [403, 429]:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logging.info(f"Rate limit exceeded, waiting {wait_time:.2f} seconds...")
                    time.sleep(wait_time)
                else:
                    raise
            except Exception as e:
                logging.error(f"An unexpected error occurred : {e}")
                return None
        logging.error(f"Request failed after {max_retries} attempts.")
        return None

    def _parse_target_info(self, target):
        """Safely parses target information from an activity record."""
        drive_item = target.get('driveItem') or target.get('file')
        if drive_item:
            file_id = drive_item.get('name', '').replace('items/', '')
            file_name = drive_item.get('title')
            file_mime = drive_item.get('mimeType')
            return file_id, file_name, file_mime
        return None, None

    def _process_activity(self, activity, folder_name, on_new_file_callback=None):
        """Processes a single activity, logging details about the new file and actor."""
        action_type = "created" if 'create' in activity['primaryActionDetail'] else "moved"

        for target in activity.get('targets', []):
            file_id, file_name, file_mimeType = self._parse_target_info(target)
            if not (file_id and file_name and file_mimeType):
                continue

            if 'application/pdf' in file_mimeType or 'image/' in file_mimeType:

                logging.info(f"\nNew file {action_type} in '{folder_name}': {file_name} (ID: {file_id})")
                print("\n")
                print(f"New file {action_type} in '{folder_name}': {file_name}.")

                if "timestamp" in activity:
                    logging.info(f"  - Timestamp: {activity['timestamp']}")
                elif "timeRange" in activity:
                    logging.info(f"  - Time Range: {activity['timeRange']}")

                if on_new_file_callback and callable(on_new_file_callback):
                    try:
                        logging.info(f"  - Executing callback for file: {file_name} (ID: {file_id})")
                        on_new_file_callback(file_id)
                    except Exception as e:
                        logging.error(f"  - Error executing callback for file_id {file_id}: {e}")
            else:
                logging.info(f"\nNew file {action_type} in '{folder_name}': {file_name} (ID: {file_id})")
                logging.info(f"MIME Type filtered out: {file_mimeType}")

    def monitor_folders_activity(self, folders_ids, refresh_rate_in_seconds, on_new_file_callback=None, consolidation_strategy="none"):
        """Monitors folders for new files using the Drive Activity API."""
        folder_ids_and_names = {
            folder_id: self.get_file_or_folder_name(file_or_folder_id=folder_id)
            for folder_id in folders_ids
        }

        for folder_id, name in folder_ids_and_names.items():
            if not name:
                logging.warning(f"Could not find name for folder ID '{folder_id}'. It will be skipped.")
                continue
            logging.info(f"Monitoring folder: '{name}' (ID: {folder_id})")

        last_check_timestamp_ms = int(time.time() * 1000) - (refresh_rate_in_seconds * 1000)

        try:
            while True:
                now = datetime.datetime.now()
                current_timestamp_ms = int(now.timestamp() * 1000)
                activity_found = False

                for folder_id, folder_name in folder_ids_and_names.items():
                    if not folder_name:
                        continue

                    request = self.activity_service.activity().query(body={
                        'ancestorName': f'items/{folder_id}',
                        'consolidationStrategy': {consolidation_strategy: {}},
                        "filter": f"time > {last_check_timestamp_ms}"
                    })
                    response = self.make_api_request(request.execute)

                    if response and 'activities' in response:
                        activity_found = True
                        for activity in response['activities']:
                            is_create = 'create' in activity.get('primaryActionDetail', {})
                            move_detail = activity.get('primaryActionDetail', {}).get('move', {})
                            is_move_in = any(
                                p.get('driveItem', {}).get('name') == f'items/{folder_id}'
                                for p in move_detail.get('addedParents', [])
                            )

                            if is_create or is_move_in:
                                self._process_activity(activity, folder_name, on_new_file_callback=on_new_file_callback)

                if not activity_found:
                    logging.info(f"No new activity detected since last check.")

                last_check_timestamp_ms = current_timestamp_ms

                european_time = now.strftime("%d/%m/%Y %H:%M:%S")
                logging.info(f"Next check after {refresh_rate_in_seconds}s at {european_time}...")
                basicfunctions.countdown(refresh_rate_in_seconds)

        except HttpError as error:
            logging.error(f"An API error occurred: {error}")

    def get_folder_to_monitor_ids(self, folders_to_monitor_names):
        folders_to_monitor_ids = []
        for folder in folders_to_monitor_names:
            if 'parent_folder_id' in folder.keys():
                folder_id = self.find_folder_id_by_name(folder['folder_name'], folder['parent_folder_id'])
            else:
                folder_id = self.find_folder_id_by_name(folder['folder_name'])

            if folder_id is None:
                logging.warning(f"Folder '{folder.get('folder_name')}' not found. Skipping.")
                continue

            folders_to_monitor_ids.append(folder_id)

        logging.info('*** Monitored folders: ***')
        print('*** Monitored folders: ***')
        for folder_id in folders_to_monitor_ids:
            logging.info(f"* {self.get_path_from_id(folder_id)}")
            print(f"* {self.get_path_from_id(folder_id)}")
        return folders_to_monitor_ids


if __name__ == '__main__':
    dm = GoogleDriveFileManager(credentials_path='config/google_credentials.json', token_path='../config/google_token.json')
    folder = dm.get_path_from_id('root')
    pass
