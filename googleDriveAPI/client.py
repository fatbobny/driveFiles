import time
import os
import io
import basicfunctions
from basicfunctions import extract_json_content as get_json
import datetime
import tempfile
import fitz  # pip install pymupdf
import logging
from PIL import Image
import pytesseract  # pip install pytesseract
from pdf2image import convert_from_path  # pip install pdf2image

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.auth.exceptions import RefreshError


class GoogleDriveFileManager:
    """Manages files and folders in Google Drive using the Google Drive API."""

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
                    logging.warning(f"Error refreshing token: {e}. Re-authenticating...")
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

        self._folder_path_cache: dict = {}
        _app_config = get_json('config/config_app.json')
        self._ocr_dpi: int = _app_config.get('ocr_dpi', 250) if _app_config else 250
        self._max_pages_for_ocr: int = _app_config.get('max_pages_for_ocr', 4) if _app_config else 4

    def find_folder_id_by_name(self, folder_name, parent_folder_id=None):
        """
        Finds the ID of a folder by its name.

        Args:
            folder_name (str): The name of the folder to find.
            parent_folder_id (str, optional): Restrict the search to this parent folder.

        Returns:
            str: The folder ID, or None if not found.
        """
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
                logging.warning(f"Multiple folders found with name '{folder_name}'. Returning the first one.")
            return items[0]["id"]

        except HttpError as error:
            logging.error(f"An error occurred: {error}")
            return None

    def find_folder_id_by_path(self, folder_path):
        """
        Finds the ID of a folder given its path from the root of Google Drive.

        Args:
            folder_path (str): Slash-separated path, e.g. "Documents/Finance/2024".

        Returns:
            str: The folder ID, or None if any segment is not found.
        """
        current_folder_id = 'root'
        for folder_name in [p for p in folder_path.split("/") if p]:
            current_folder_id = self.find_folder_id_by_name(folder_name, parent_folder_id=current_folder_id)
            if current_folder_id is None:
                return None
        return current_folder_id

    def get_file_or_folder_name(self, file_or_folder_id):
        """
        Gets the name of a file or folder given its ID.

        Args:
            file_or_folder_id (str): The Drive ID.

        Returns:
            str: The name, or None on error.
        """
        try:
            file = self.drive_service.files().get(fileId=file_or_folder_id, fields='name').execute()
            return file.get('name')
        except HttpError as error:
            logging.error(f"An error occurred: {error}")
            return None

    def get_parent_folder_id(self, file_or_folder_id):
        """
        Gets the ID of the parent folder of a given file or folder.

        Args:
            file_or_folder_id (str): The Drive ID.

        Returns:
            str: The parent folder ID, or "root" if at the top level.
        """
        try:
            file = self.drive_service.files().get(fileId=file_or_folder_id, fields='parents').execute()
            parents = file.get('parents')
            return "root" if not parents else parents[0]
        except HttpError as error:
            logging.error(f"An error occurred: {error}")
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

    def get_path_from_id(self, file_or_folder_id):
        """
        Gets the full path of a file or folder from its ID.

        Args:
            file_or_folder_id (str): The Drive ID.

        Returns:
            str: The full slash-separated path, or None on error.
        """
        if file_or_folder_id in self._folder_path_cache:
            return self._folder_path_cache[file_or_folder_id]
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

            result = "/".join(path_parts)
            self._folder_path_cache[file_or_folder_id] = result
            return result

        except HttpError as error:
            logging.error(f"An error occurred: {error}")
            return None

    def list_files_in_folder(self, folder_id=None, file_name=None):
        """
        Lists files in a folder, with optional name filtering.

        Args:
            folder_id (str, optional): The folder to list. Defaults to all non-trashed files.
            file_name (str, optional): Filter files whose name contains this string.

        Returns:
            list: List of file dicts with id, name, mimeType.
        """
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
                all_items.extend(results.get("files", []))
                page_token = results.get("nextPageToken")
                if not page_token:
                    break

            return all_items

        except HttpError as error:
            logging.error(f"An error occurred: {error}")
            return []

    def create_folder(self, folder_name, parent_folder_id=None):
        """
        Creates a folder in Google Drive.

        Args:
            folder_name (str): Name of the folder to create.
            parent_folder_id (str, optional): ID of the parent folder.

        Returns:
            str: The new folder's ID, or None on error.
        """
        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_folder_id:
                file_metadata['parents'] = [parent_folder_id]

            file = self.drive_service.files().create(body=file_metadata, fields='id').execute()
            logging.info(
                f"Folder '{folder_name}' created in '{self.get_file_or_folder_name(self.get_parent_folder_id(file.get('id')))}' successfully.")
            return file.get('id')

        except HttpError as error:
            logging.error(f"An error occurred: {error}")
            return None

    def create_folder_by_path(self, folder_path):
        """Creates a folder hierarchy in Google Drive, creating any missing parent folders along the way."""
        path_parts = [p for p in folder_path.split("/") if p]
        current_parent_id = 'root'
        some_folder_created = False

        for folder_name in path_parts:
            folder_id = self.find_folder_id_by_name(folder_name, parent_folder_id=current_parent_id)
            if folder_id is None:
                folder_id = self.create_folder(folder_name, parent_folder_id=current_parent_id)
                some_folder_created = True
                if folder_id is None:
                    logging.error(f"Failed to create folder '{folder_name}'")
                    return None
            current_parent_id = folder_id

        if not some_folder_created:
            logging.info(f"'{folder_path}' already exists")

        return current_parent_id

    def read_file(self, file_id, local_filepath=None):
        """
        Downloads a file from Google Drive.

        Args:
            file_id (str): The Drive file ID.
            local_filepath (str, optional): If given, saves to disk instead of returning bytes.

        Returns:
            bytes or None: File content if no local_filepath, else None.
        """
        try:
            request = self.drive_service.files().get_media(fileId=file_id)
            if local_filepath:
                with io.FileIO(local_filepath, "wb") as fh:
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                        logging.info(f"Download {int(status.progress() * 100)}%.")
                return None
            else:
                return request.execute()

        except HttpError as error:
            logging.error(f"An error occurred: {error}")
            return None
        except IOError as e:
            logging.warning(f"IO Error during download: {e}")
            return None

    def move_file(self, file_id, new_folder_id):
        """
        Moves a file to a different folder.

        Args:
            file_id (str): The Drive file ID.
            new_folder_id (str): The destination folder ID.

        Returns:
            dict: Updated file metadata, or None on error.
        """
        try:
            file = self.drive_service.files().get(fileId=file_id, fields='parents').execute()
            previous_parents = ",".join(file.get('parents'))
            file = self.drive_service.files().update(
                fileId=file_id,
                addParents=new_folder_id,
                removeParents=previous_parents,
                fields='id, parents'
            ).execute()
            logging.info(f"File '{self.get_file_or_folder_name(file_id)}' (ID: {file_id}) moved successfully.")
            return file
        except HttpError as error:
            logging.error(f"An error occurred: {error}")
            return None

    def rename_file(self, file_id, new_name):
        """
        Renames a file in Google Drive.

        Args:
            file_id (str): The Drive file ID.
            new_name (str): The new filename.

        Returns:
            dict: Updated file metadata, or None on error.
        """
        try:
            updated_file = self.drive_service.files().update(
                fileId=file_id, body={'name': new_name}, fields='id, name'
            ).execute()
            logging.info(f"File ID '{file_id}' renamed to '{updated_file.get('name')}' successfully.")
            return updated_file
        except HttpError as error:
            logging.error(f"An error occurred: {error}")
            return None

    def delete_file(self, file_id):
        """
        Permanently deletes a file.

        Args:
            file_id (str): The Drive file ID.
        """
        try:
            file_name = self.get_file_or_folder_name(file_id)
            self.drive_service.files().delete(fileId=file_id).execute()
            logging.info(f"File '{file_name}' (ID: {file_id}) deleted successfully.")
        except HttpError as error:
            logging.error(f"An error occurred: {error}")

    def upload_file(self, local_filepath, folder_id=None, drive_filename=None):
        """
        Uploads a local file to Google Drive.

        Args:
            local_filepath (str): Path to the file to upload.
            folder_id (str, optional): Destination folder ID.
            drive_filename (str, optional): Name to use on Drive; defaults to the local filename.

        Returns:
            str: The new file's Drive ID, or None on error.
        """
        if not os.path.exists(local_filepath):
            raise FileNotFoundError(f"File not found: {local_filepath}")
        try:
            file_metadata = {'name': drive_filename or os.path.basename(local_filepath)}
            if folder_id:
                file_metadata['parents'] = [folder_id]

            media = MediaFileUpload(local_filepath)
            file = self.drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            logging.info(f"File uploaded with ID: {file.get('id')}")
            return file.get('id')
        except HttpError as error:
            logging.error(f"An error occurred: {error}")
            return None

    def get_file_content(self, file_id, mime_type, file_name):
        """Downloads file content as bytes."""
        try:
            request = self.drive_service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                logging.info(f"Download {int(status.progress() * 100)}%.")
            return fh.getvalue()
        except HttpError as error:
            logging.error(f"Error downloading file '{file_name}': {error}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error downloading file '{file_name}': {e}")
            return None

    def extract_text_with_actual_newlines_from_pdf(self, pdf_path):
        """Extracts text from a PDF using PyMuPDF, preserving layout newlines."""
        try:
            doc = fitz.open(pdf_path)
            all_text = ""
            for page in doc:
                blocks = page.get_text("blocks")
                for b in blocks:
                    block_text = b[4].strip().replace('\n', ' ')
                    all_text += block_text + '\n'
            doc.close()
            return all_text.strip()
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            return None

    def extract_text_from_pdf(self, file_content, max_pages_for_ocr=None):
        """Extracts text from PDF bytes using pdf2image + Tesseract OCR."""
        if max_pages_for_ocr is None:
            max_pages_for_ocr = self._max_pages_for_ocr
        try:
            with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as temp_pdf:
                temp_pdf.write(file_content)
                temp_pdf.flush()
                try:
                    pages = convert_from_path(temp_pdf.name, dpi=self._ocr_dpi, last_page=max_pages_for_ocr)
                except Exception as e:
                    logging.error(f"Error converting PDF to images: {e}. Ensure poppler is installed.")
                    return None

            logging.info(f'Extracting text: scanning up to {max_pages_for_ocr} pages')
            pdf_text = ''
            for page in pages:
                page_text = pytesseract.image_to_string(page)
                pdf_text += page_text.replace('-\n', '')

            return pdf_text.strip()
        except Exception as e:
            logging.error(f"Unexpected error during PDF text extraction: {e}")
            return None

    def extract_text_from_image(self, file_content):
        """Extracts text from image bytes using Tesseract OCR."""
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp_image:
                temp_image.write(file_content)
                image_path = temp_image.name
            try:
                text = pytesseract.image_to_string(Image.open(image_path))
            except Exception as e:
                logging.error(f"Error processing image with Tesseract: {e}")
                return None
            finally:
                os.unlink(image_path)
            return text.strip()
        except Exception as e:
            logging.error(f"Unexpected error during image text extraction: {e}")
            return None

    def get_file_details_and_extract_content(self, file_id: str, max_pages_for_ocr: int = 5) -> dict:
        """Retrieves metadata and extracted text for a single file."""
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
            logging.error(f"API error processing file ID {file_id}: {e}")
            return {
                'file_id': file_id, 'file_name': None, 'parent_folder_id': None,
                'parent_folder_name': None, 'mime_type': None, 'extracted_text': None,
                'error': f"API Error: {e}"
            }
        except Exception as e:
            logging.error(f"Unexpected error processing file ID {file_id}: {e}")
            return {
                'file_id': file_id, 'file_name': None, 'parent_folder_id': None,
                'parent_folder_name': None, 'mime_type': None, 'extracted_text': None,
                'error': f"Unexpected Error: {e}"
            }

    def fetch_and_process_files_in_folders(self, folder_ids, on_file_callback=None, filter_mime_types=None, max_pages_for_ocr=5):
        """Fetches all matching files from a list of folder IDs and processes them via a callback."""
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

            for file_summary in self.list_files_in_folder(folder_id=folder_id):
                file_id = file_summary['id']
                file_name = file_summary['name']
                mime_type = file_summary['mimeType']

                if any(filter_type in mime_type for filter_type in filter_mime_types):
                    file_details = self.get_file_details_and_extract_content(
                        file_id=file_id, max_pages_for_ocr=max_pages_for_ocr
                    )
                    all_files_data.append(file_details)

                    if on_file_callback and callable(on_file_callback):
                        try:
                            logging.info(f"  - Executing callback for file: {file_name} (ID: {file_id})")
                            on_file_callback(file_details)
                        except Exception as e:
                            logging.error(f"  - Error in callback for file_id {file_id}: {e}")
                else:
                    logging.info(f"Skipping '{file_name}' (type: {mime_type})")

            logging.info(f'+++ Finished processing files for {folder_name} +++')

        logging.info(f'+++ All folders done. Files processed: {len(all_files_data)} +++')
        return all_files_data

    def _parse_target_info(self, target):
        """Safely parses target information from an activity record."""
        drive_item = target.get('driveItem') or target.get('file')
        if drive_item:
            file_id = drive_item.get('name', '').replace('items/', '')
            file_name = drive_item.get('title')
            file_mime = drive_item.get('mimeType')
            return file_id, file_name, file_mime
        return None, None, None  # fixed: was returning 2-tuple, caller unpacks 3

    def _process_activity(self, activity, folder_name, on_new_file_callback=None):
        """Processes a single Drive activity record."""
        action_type = "created" if 'create' in activity['primaryActionDetail'] else "moved"

        for target in activity.get('targets', []):
            file_id, file_name, file_mimeType = self._parse_target_info(target)
            if not (file_id and file_name and file_mimeType):
                continue

            if 'application/pdf' in file_mimeType or 'image/' in file_mimeType:
                logging.info(f"New file {action_type} in '{folder_name}': {file_name} (ID: {file_id})")

                if "timestamp" in activity:
                    logging.info(f"  - Timestamp: {activity['timestamp']}")
                elif "timeRange" in activity:
                    logging.info(f"  - Time Range: {activity['timeRange']}")

                if on_new_file_callback and callable(on_new_file_callback):
                    try:
                        logging.info(f"  - Executing callback for file: {file_name} (ID: {file_id})")
                        on_new_file_callback(file_id)
                    except Exception as e:
                        logging.error(f"  - Error in callback for file_id {file_id}: {e}")
            else:
                logging.info(f"New file {action_type} in '{folder_name}': {file_name} — MIME type filtered out.")

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
                    response = request.execute()

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
                    logging.info("No new activity detected since last check.")

                last_check_timestamp_ms = current_timestamp_ms
                logging.info(f"Next check after {refresh_rate_in_seconds}s...")
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
        for folder_id in folders_to_monitor_ids:
            logging.info(f"* {self.get_path_from_id(folder_id)}")
        return folders_to_monitor_ids


if __name__ == '__main__':
    dm = GoogleDriveFileManager(credentials_path='config/google_credentials.json', token_path='../config/google_token.json')
    folder = dm.get_path_from_id('root')
