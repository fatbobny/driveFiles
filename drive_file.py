# In a new file, e.g., drive_file.py
import logging
from typing import Dict, Any, List, Optional
import re
import dateparser
from basicfunctions import add_months, extract_json_content as get_json
import pushover_seb

# These are type hints for clarity. You would import the actual classes
# from their respective modules in your final code.
# from googleDriveAPI import GoogleDriveFileManager
# from sklearn.feature_extraction.text import TfidfVectorizer
# from sklearn.linear_model import LogisticRegression
GoogleDriveFileManager = Any
TfidfVectorizer = Any
LogisticRegression = Any

_app_config = get_json('config/config_app.json')
_DATE_STRING_FIXES: dict = _app_config.get('date_string_fixes', {}) if _app_config else {}
_DOWNLOAD_BASE_PATH: str = _app_config.get('download_base_path', 'Downloads/A_To sort/') if _app_config else 'Downloads/A_To sort/'


class DriveFile:
    """
    Represents a Google Drive file and encapsulates its processing logic.

    This class holds the file's metadata, its extracted text content, and the
    necessary tools (Drive manager, ML models) to process it. It can
    determine its own configuration, predict its destination, generate a new
    name, and execute the renaming and moving operations on Google Drive.

    Attributes:
        _file_id (str): The Google Drive ID of the file.
        name (str): The original name of the file.
        parents (List[str]): A list of parent folder IDs.
        content (str): The extracted text content from the file.
        target_folder_path (Optional[str]): The predicted destination folder path.
        new_filename (Optional[str]): The newly generated filename.
    """

    def __init__(self,
                 file_details: Dict[str, Any],
                 drive_manager: GoogleDriveFileManager,
                 pdf_configs: Dict[str, Any],
                 ml_model: LogisticRegression,
                 ml_vectorizer: TfidfVectorizer,
                 pushover_creds: Dict[str, str]):

        """
        Initializes the DriveFile object.

        Args:
            file_details (Dict[str, Any]): A dictionary containing file metadata
                and content from `dm.get_files_and_extract_content`.
            drive_manager (GoogleDriveFileManager): An instance to interact with the Drive API.
            pdf_configs (Dict[str, Any]): Configuration for different PDF types.
            ml_model (LogisticRegression): The trained machine learning model for classification.
            ml_vectorizer (TfidfVectorizer): The vectorizer for the ML model.
        """
        logging.info(f'--- Initialising file {file_details.get('file_name')} ---')
        print("\n")
        print(f'--- Initialising file {file_details.get('file_name')} ---')

        # --- Core Attributes from file_details ---
        self._file_id: str = file_details.get('file_id')
        self.name: str = file_details.get('file_name')
        self.content: str = file_details.get('extracted_text', '')
        self.mime_type: str = file_details.get('mime_type')
        self._parent_folder_id:str = file_details.get('parent_folder_id')
        self.parent_folder_name:str = file_details.get('parent_folder_name')

        # --- Dependencies for processing ---
        self._drive_manager = drive_manager
        self._pdf_configs = pdf_configs
        self._ml_model = ml_model
        self._ml_vectorizer = ml_vectorizer
        self._pushover_creds = pushover_creds

        # --- Derived attributes determined on initialization ---
        self.config: Optional[Dict[str, Any]] = self._get_file_config()
        self.date = self._get_date_for_file_name()
        self.target_folder_path: Optional[str] = self._get_folder_path()
        self.new_filename: Optional[str] = self._get_target_filename()

        if not all([self._file_id, self.name, self.content, self.mime_type, self._parent_folder_id, self.date,self.config, self.parent_folder_name, self.target_folder_path, self.new_filename]):
            self.has_all_elements_to_move_and_rename_from_config = False
            logging.warning(f"Could not fully determine a config.")
            print(f"+++ Could not fully determine a config. +++")
        else:
            self.has_all_elements_to_move_and_rename_from_config = True
            logging.info(f"Successfully determined processing logic for file '{self.name}'.")
            print(f"+++ Successfully assigned a config. +++")

    def review_extraction(self) -> Dict[str, Any]:
        """
        Provides a summary of the text extraction and configuration matching process.

        Returns:
            A dictionary containing a review of the extraction process, including
            the config found, date extraction status, and keyword matches.
        """
        review_summary = {
            "file_name": self.name,
            "config_found": None,
            "date_extracted": "No" if self.date is None else "Yes"
        }

        if self.config:
            # Find the key (name) of the config that was matched
            config_name = "Unknown"
            for key, config_value in self._pdf_configs.items():
                if config_value == self.config:
                    config_name = key
                    break
            review_summary["config_found"] = config_name

        return review_summary

    def _get_file_config(self) -> Optional[Dict[str, Any]]:
        # load config file. Check keywords are in text.
        for key in self._pdf_configs.keys():

            config = self._pdf_configs[key]

            # initiate at True and assign false as soon a keyword is not in the text
            check_all_keywords = True

            for keyword in config['keywords']:
                if keyword.lower() not in self.content.lower():
                    check_all_keywords = False
                    break

            if check_all_keywords:
                print('Assigned config "{}" for {}.'.format(key, self.name))
                logging.info('Assigned config "{}" for {}.'.format(key, self.name))
                return config

        print('No config found')
        logging.info('No config found for {}.'.format(self.name))
        return None

    def _get_folder_path_from_config(self):
        """
        Constructs a folder path from the configuration.

        Returns the base target folder path. If the config flag
        'target_folder_add_year' is set and a date is available,
        the year will be appended to the path.

        Returns:
            str: The constructed folder path.
            None: If config or the 'target_folder' key is missing.
        """
        # Guard Clause: Exit early if there is no configuration.
        if not self.config:
            return None

        # Safely get the base path. Exit if it's not defined in the config.
        base_path = self.config.get('target_folder')
        if not base_path:
            return None

        # Check if the year should be appended.
        should_add_year = self.config.get('target_folder_add_year') and self.date
        if should_add_year:
            return f"{base_path}/{self.date.year}"

        # Otherwise, return the base path.
        return base_path

    def _predict_target_folder_path(self) -> Optional[str]:
        """
        Uses the ML model to predict the destination folder for the file.

        Returns:
            The predicted folder path (e.g., "Invoices/2024"), or None if prediction fails.
        """
        if not self.content:
            logging.warning(f"Cannot predict path for '{self.name}': No text content extracted.")
            return None

        try:
            content_vectorized = self._ml_vectorizer.transform([self.content])
            prediction = self._ml_model.predict(content_vectorized)
            target_path = str(prediction[0])
            logging.info(f"ML model predicted target path '{target_path}' for file '{self.name}'.")
            return _DOWNLOAD_BASE_PATH + target_path
        except Exception as e:
            logging.error(f"Error during ML prediction for '{self.name}': {e}")
            return None

    def _get_folder_path(self):

        if self._get_folder_path_from_config() and self.date:
            logging.info('Assigned target path from config')
            print('Assigned target path from config')
            return self._get_folder_path_from_config()
        else:
            logging.info('Predicted target path from ML')
            print('Predicted target path from ML')
            return self._predict_target_folder_path()

    def _get_date_for_file_name(self):
        # Parse the pdf to get the date of the visit
        date = None
        if self.config:
            for i in range(len(self.config['regex_date'])):
                dateRegex = re.compile(self.config['regex_date'][i]['regex_string'])
                mo = dateRegex.findall(self.content)

                if mo is not None:
                    for k in range(len(mo)):
                        # extract the matches into a string
                        de = mo[k]
                        date_extract = de
                        for bad, good in _DATE_STRING_FIXES.items():
                            date_extract = date_extract.replace(bad, good)
                        try:
                            #                         date = datetime.datetime.strptime(date_extract, self.config['regex_date'][i]['extract_format'])
                            if 'extract_format' in self.config['regex_date'][i].keys():
                                date = dateparser.parse(date_extract,
                                                        date_formats=[self.config['regex_date'][i]['extract_format']],
                                                        languages=['en', 'fr'])
                                # print('Used the extract format for the date parsing.')
                                # logging.info('Used the extract format for the date parsing.')
                            else:
                                date = dateparser.parse(date_extract, languages=['en', 'fr'])
                        except Exception as e:
                            logging.error(f"Date parsing failed for '{date_extract}': {e}")
                        if date is not None:
                            break

                # exit the for loop if found a match
                if date is not None:
                    break
                else:
                    continue
        print('Assigned date : {}.'.format(date))
        logging.info('Assigned date : {}.'.format(date))
        return date

    def _get_target_filename(self) -> Optional[str]:
        """
        Generates a new, standardized filename.

        If a config is found, it uses the 'filename_base' and date information
        to construct a new name, preserving the original file extension.
        If no config is found, it returns the original filename.

        Returns:
            The new filename string, or the original name as a fallback.
        """
        if not self.config:
            return self.name

        # 1. Safely get the file extension from the original name
        name_parts = self.name.rsplit('.', 1)
        extension = f".{name_parts[1]}" if len(name_parts) > 1 else ""

        base_name = self.config.get('filename_base', '')
        date_part = ""

        # 2. Construct the date part of the filename if a date was found
        if self.date:
            date_type = self.config.get('filename_datetype')
            month_shift = self.config.get('month_shift', 0)
            date_to_use = add_months(self.date, month_shift) if month_shift != 0 else self.date

            if date_type == 'quarter':
                quarter = (date_to_use.month - 1) // 3 + 1
                date_part = f"{date_to_use.year} Q{quarter}"
            elif date_type == 'year':
                date_part = date_to_use.strftime('%Y')
            elif date_type == 'month':
                date_part = date_to_use.strftime('%Y %m')
            elif date_type == 'day':
                date_part = date_to_use.strftime('%Y %m %d')

        # 3. Assemble the final filename
        if base_name and date_part:
            return f"{base_name} - {date_part}{extension}"
        elif base_name:
            # Fallback for configs without a date requirement
            return f"{base_name}{extension}"
        else:
            # Fallback if config is malformed (e.g., no 'filename_base')
            logging.warning(f"Config for '{self.name}' is missing 'filename_base'. Reverting to original name.")
            return self.name

    def rename_and_sort(self) -> None:
        """
        Orchestrates the full process of renaming and sorting the file on Google Drive.
        This method is now more efficient and robust.
        """
        # 1. Initial validation to ensure processing is possible
        if not self.target_folder_path or not self.new_filename:
            logging.error(f"Aborting sort for '{self.name}': Missing target path or new filename.")
            return

        logging.info(f"--- Starting processing for file: {self.name} ---")
        print(f"--- Starting processing for file: {self.name} ---")

        # 2. More efficient folder handling.
        #    create_folder_by_path should ideally return the final folder's ID to save an API call.
        #    Assuming it's modified to do so:
        target_folder_id = self._drive_manager.create_folder_by_path(self.target_folder_path)

        if not target_folder_id:
            logging.error(f"Could not find or create target folder ID for path '{self.target_folder_path}'. Aborting.")
            return

        # 3. Check if the file needs to be renamed
        needs_rename = (self.name != self.new_filename) and self.has_all_elements_to_move_and_rename_from_config
        if needs_rename:
            rename_success = self._drive_manager.rename_file(self._file_id, self.new_filename)
            logging.info(f"File '{self.name}' renamed to '{self.new_filename}'.")
            print(f"File renamed to '{self.new_filename}'.")
            if not rename_success:
                logging.error(f"Skipping move for file ID '{self._file_id}' because rename failed.")
                print(f"Skipping move for file ID '{self._file_id}' because rename failed.")
                return  # Stop processing if rename fails
        else:
            logging.info(f"File '{self.name}' already has the correct name. Skipping rename.")
            print(f"Skipping rename.")

        # 4. Check if the file needs to be moved
        #    This avoids an unnecessary API call if the file is already in the correct folder.
        if not target_folder_id:
            logging.error(f"target_folder_id is None for '{self.name}'. Skipping move.")
            return
        needs_move = self._parent_folder_id != target_folder_id

        if needs_move:
            self._drive_manager.move_file(self._file_id, target_folder_id)
            logging.info(f"File '{self.name}' moved to '{self.target_folder_path}'.")
            print(f"File '{self.name}' moved to '{self.target_folder_path}'.")
        else:
            logging.info(f"File '{self.new_filename}' is already in the correct folder. Skipping move.")
            print(f"File '{self.new_filename}' is already in the correct folder. Skipping move.")

        # Send Pushover notification

        # Constructing the detailed message for Pushover
        title="File Processed"

        original_info = f"New file: '{self.name}' in folder '{self.parent_folder_name}'."
        actions_taken = []

        if needs_rename:
            actions_taken.append(f"Renamed to '{self.new_filename}'.")

        if needs_move:
            actions_taken.append(f"Moved to '{self.target_folder_path}'.")

        full_message = f"{original_info}\nActions: {' '.join(actions_taken)}"

        pushover_seb.pushover_send(
            msg_title=title,
            msg=full_message,
            api_token=self._pushover_creds['API'],
            user_key=self._pushover_creds['user']
        )


        logging.info(f"+++ Successfully processed '{self.new_filename}'. +++")
        print(f"+++ Successfully processed. +++")
        return
