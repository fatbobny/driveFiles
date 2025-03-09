# google_drive_api.py
# pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
# API guide : https://developers.google.com/drive/api/quickstart/python

import os
import io
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload


class GoogleDriveFileManager:
    """
    A class to manage files and folders in Google Drive using the Google Drive API.

    Requires:
        - Google Drive API credentials (credentials.json or similar)
        - API Scopes:  'https://www.googleapis.com/auth/drive' (or a more specific scope if you only need read-only access, etc.)

    Attributes:
        drive_service: The Google Drive API service object.

    Methods:
        find_folder_id(folder_name, parent_folder_id=None):  Finds the ID of a folder by name.
        list_files(folder_id=None, file_name=None): Lists files in a folder or searches for a file by name.
        read_file(file_id, local_filepath=None): Reads a file's content (download) or returns the content as bytes.
        move_file(file_id, new_folder_id): Moves a file to a different folder.
        delete_file(file_id): Deletes a file.
        create_folder(folder_name, parent_folder_id=None): Creates a new folder.
        upload_file(local_filepath, folder_id=None, drive_filename=None): Uploads a file to a folder.

    """

    def __init__(self, credentials_path='credentials.json', token_path='token.json', scopes=None):
        """
        Initializes the GoogleDriveFileManager.

        Args:
            credentials_path (str, optional): Path to the credentials file. Defaults to 'credentials.json'.
            token_path (str, optional): Path to the token file (stores user's access and refresh tokens). Defaults to 'token.json'.
            scopes (list, optional):  List of authorization scopes.  Defaults to full Drive access.  See Google Drive API documentation for options.
        """

        if scopes is None:
            scopes = ['https://www.googleapis.com/auth/drive']
        creds = None

        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, scopes)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Use google_auth_oauthlib for interactive flow (if needed)
                from google_auth_oauthlib.flow import InstalledAppFlow

                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, scopes
                )
                creds = flow.run_local_server(port=0)

            with open(token_path, "w") as token:
                token.write(creds.to_json())

        self.drive_service = build("drive", "v3", credentials=creds)


    def find_folder_id(self, folder_name, parent_folder_id=None):
        """
        Finds the ID of a folder by its name.

        Args:
            folder_name (str): The name of the folder to find.
            parent_folder_id (str, optional): The ID of the parent folder.  If None, searches the entire Drive.

        Returns:
            str: The ID of the folder, or None if the folder is not found.

        Raises:
            HttpError: If there's an error communicating with the Drive API.
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
                return None  # Folder not found
            elif len(items) > 1:
                print(f"Warning: Multiple folders found with name '{folder_name}'.  Returning the first one.")
            return items[0]["id"]  # Return the ID of the first matching folder

        except HttpError as error:
            print(f"An error occurred: {error}")
            return None


    def list_files(self, folder_id=None, file_name=None):
        """
        Lists files in a specified folder or searches for a file by name.

        Args:
            folder_id (str, optional): The ID of the folder to list files from. If None, searches across all of Drive.
            file_name (str, optional):  If provided, searches for files with this name (within the folder if folder_id is given, or across Drive).

        Returns:
            list: A list of dictionaries, where each dictionary represents a file and contains 'id' and 'name' keys.  Returns an empty list if no files are found.

        Raises:
            HttpError: If there's an error communicating with the Drive API.
        """
        try:
            q = "trashed = false"  # Exclude trashed files
            if folder_id:
                q += f" and '{folder_id}' in parents"
            if file_name:
                q += f" and name contains '{file_name}'"

            results = (
                self.drive_service.files()
                .list(q=q, fields="nextPageToken, files(id, name, mimeType)")
                .execute()
            )
            items = results.get("files", [])
            return items

        except HttpError as error:
            print(f"An error occurred: {error}")
            return []


    def read_file(self, file_id, local_filepath=None):
        """
        Reads a file's content from Google Drive.

        Args:
            file_id (str): The ID of the file to read.
            local_filepath (str, optional):  If provided, the file content will be downloaded to this local file path. If None, the content will be returned as bytes.

        Returns:
            bytes: The file content as bytes (if local_filepath is None).
            None: If local_filepath is provided (file is downloaded).

        Raises:
            HttpError: If there's an error communicating with the Drive API.
            IOError: If there's an error during file download.
        """
        try:
            request = self.drive_service.files().get_media(fileId=file_id)
            if local_filepath:
                with io.FileIO(local_filepath, "wb") as fh:
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while done is False:
                        status, done = downloader.next_chunk()
                        print(f"Download {int(status.progress() * 100)}%.")
                return None  # File downloaded, so no return value
            else:
                file_content = request.execute()
                return file_content # Return the content as bytes

        except HttpError as error:
            print(f"An error occurred: {error}")
            return None
        except IOError as e:
            print(f"IO Error during download: {e}")
            return None

    def move_file(self, file_id, new_folder_id):
        """
        Moves a file to a different folder.

        Args:
            file_id (str): The ID of the file to move.
            new_folder_id (str): The ID of the destination folder.

        Returns:
            dict: The updated file metadata, or None on error.

        Raises:
            HttpError: If there's an error communicating with the Drive API.
        """
        try:
            # Get the file's current parents
            file = self.drive_service.files().get(fileId=file_id, fields='parents').execute()
            previous_parents = ",".join(file.get('parents'))

            # Move the file to the new folder
            file = self.drive_service.files().update(
                fileId=file_id,
                addParents=new_folder_id,
                removeParents=previous_parents,
                fields='id, parents'
            ).execute()
            return file

        except HttpError as error:
            print(f"An error occurred: {error}")
            return None


    def delete_file(self, file_id):
        """
        Deletes a file from Google Drive.

        Args:
            file_id (str): The ID of the file to delete.

        Returns:
            None

        Raises:
            HttpError: If there's an error communicating with the Drive API.
        """
        try:
            self.drive_service.files().delete(fileId=file_id).execute()
            print(f"File with id '{file_id}' deleted successfully.")

        except HttpError as error:
            print(f"An error occurred: {error}")



    def create_folder(self, folder_name, parent_folder_id=None):
        """
        Creates a new folder in Google Drive.

        Args:
            folder_name (str): The name of the new folder.
            parent_folder_id (str, optional): The ID of the parent folder. If None, the folder will be created in the root directory.

        Returns:
            str: The ID of the newly created folder, or None on error.

        Raises:
            HttpError: If there's an error communicating with the Drive API.

        """
        try:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_folder_id:
                file_metadata['parents'] = [parent_folder_id]

            file = self.drive_service.files().create(body=file_metadata, fields='id').execute()
            return file.get('id')

        except HttpError as error:
            print(f"An error occurred: {error}")
            return None

    def upload_file(self, local_filepath, folder_id=None, drive_filename=None):
        """
        Uploads a file to Google Drive.

        Args:
            local_filepath (str): The path to the local file to upload.
            folder_id (str, optional): The ID of the folder to upload to. If None, the file will be uploaded to the root directory.
            drive_filename (str, optional): The name of the file in Drive. If None, the local filename will be used.

        Returns:
            str: The ID of the uploaded file, or None on error.

        Raises:
            HttpError: If there's an error communicating with the Drive API.
            FileNotFoundError: If the local_filepath does not exist.
        """

        if not os.path.exists(local_filepath):
            raise FileNotFoundError(f"File not found: {local_filepath}")

        try:
            file_metadata = {'name': drive_filename or os.path.basename(local_filepath)}
            if folder_id:
                file_metadata['parents'] = [folder_id]

            media = MediaFileUpload(local_filepath)
            file = self.drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            print(f'File ID: {file.get("id")}')
            return file.get('id')

        except HttpError as error:
            print(f"An error occurred: {error}")
            return None