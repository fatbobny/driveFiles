import logging
import os
import re
from typing import TYPE_CHECKING, Dict, Any, List, Optional
import dateparser
from basicfunctions import add_months, extract_json_content as get_json
import pushover_seb

if TYPE_CHECKING:
    from googleDriveAPI import GoogleDriveFileManager
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

_app_config = get_json('config/config_app.json')
_DATE_STRING_FIXES: dict = _app_config.get('date_string_fixes', {}) if _app_config else {}
_DOWNLOAD_BASE_PATH: str = _app_config.get('download_base_path', 'Downloads/A_To sort/') if _app_config else 'Downloads/A_To sort/'


class DriveFile:
    """
    Represents a Google Drive file and encapsulates its processing logic.

    Given extracted text and file metadata, determines the target filename
    (date-based) and folder path (config rule → ML fallback), then executes
    the rename/move via the Drive manager.

    Attributes:
        _file_id (str): The Google Drive ID of the file.
        name (str): The original name of the file.
        content (str): The extracted text content from the file.
        target_folder_path (Optional[str]): The predicted destination folder path.
        new_filename (Optional[str]): The newly generated filename.
    """

    def __init__(self,
                 file_details: Dict[str, Any],
                 drive_manager: 'GoogleDriveFileManager',
                 pdf_configs: Dict[str, Any],
                 ml_model: 'LogisticRegression',
                 ml_vectorizer: 'TfidfVectorizer',
                 pushover_creds: Dict[str, str]):
        """
        Args:
            file_details: Dict from `dm.get_file_details_and_extract_content`.
            drive_manager: Instance for Drive API interactions.
            pdf_configs: Loaded config_pdf.json content.
            ml_model: Trained LogisticRegression classifier.
            ml_vectorizer: TfidfVectorizer paired with ml_model.
            pushover_creds: Dict with 'API' and 'user' keys.
        """
        logging.info(f"--- Initialising file {file_details.get('file_name')} ---")

        self._file_id: str = file_details.get('file_id')
        self.name: str = file_details.get('file_name')
        self.content: str = file_details.get('extracted_text', '')
        self.mime_type: str = file_details.get('mime_type')
        self._parent_folder_id: str = file_details.get('parent_folder_id')
        self.parent_folder_name: str = file_details.get('parent_folder_name')

        self._drive_manager = drive_manager
        self._pdf_configs = pdf_configs
        self._ml_model = ml_model
        self._ml_vectorizer = ml_vectorizer
        self._pushover_creds = pushover_creds

        self.config: Optional[Dict[str, Any]] = self._get_file_config()
        self.date = self._get_date_for_file_name()
        self.target_folder_path: Optional[str] = self._get_folder_path()
        self.new_filename: Optional[str] = self._get_target_filename()

        required = [self._file_id, self.name, self.mime_type, self._parent_folder_id,
                    self.date, self.config, self.parent_folder_name,
                    self.target_folder_path, self.new_filename]
        if not all(required):
            self.has_all_elements_to_move_and_rename_from_config = False
            logging.warning("Could not fully determine a config.")
        else:
            self.has_all_elements_to_move_and_rename_from_config = True
            logging.info(f"Successfully determined processing logic for file '{self.name}'.")

    def review_extraction(self) -> Dict[str, Any]:
        """
        Returns a summary dict of the text extraction and config-matching outcome.

        Returns:
            Dict with file_name, config_found, and date_extracted.
        """
        review_summary = {
            "file_name": self.name,
            "config_found": None,
            "date_extracted": "No" if self.date is None else "Yes"
        }

        if self.config:
            config_name = next(
                (key for key, val in self._pdf_configs.items() if val == self.config),
                "Unknown"
            )
            review_summary["config_found"] = config_name

        return review_summary

    def _get_file_config(self) -> Optional[Dict[str, Any]]:
        """Returns the first config entry whose keywords all appear in the extracted text."""
        for key, config in self._pdf_configs.items():
            if all(kw.lower() in self.content.lower() for kw in config['keywords']):
                logging.info(f'Assigned config "{key}" for {self.name}.')
                return config

        logging.info(f'No config found for {self.name}.')
        return None

    def _get_folder_path_from_config(self):
        """
        Constructs the target folder path from the matched config entry.

        Appends the year to the path when target_folder_add_year is true and
        a date is available. Returns the base path otherwise.

        Returns:
            str: Constructed folder path, or None if no config / no target_folder.
        """
        if not self.config:
            return None
        base_path = self.config.get('target_folder')
        if not base_path:
            return None
        if self.config.get('target_folder_add_year') and self.date:
            return f"{base_path}/{self.date.year}"
        return base_path

    def _predict_target_folder_path(self) -> Optional[str]:
        """Uses the ML model to predict the destination folder for the file."""
        if not self.content:
            logging.warning(f"Cannot predict path for '{self.name}': no text content extracted.")
            return None
        try:
            content_vectorized = self._ml_vectorizer.transform([self.content])
            prediction = self._ml_model.predict(content_vectorized)
            target_path = str(prediction[0])
            logging.info(f"ML model predicted target path '{target_path}' for '{self.name}'.")
            return _DOWNLOAD_BASE_PATH + target_path
        except Exception as e:
            logging.error(f"Error during ML prediction for '{self.name}': {e}")
            return None

    def _get_folder_path(self):
        """Returns the config-based path if a config matched, otherwise falls back to ML."""
        config_path = self._get_folder_path_from_config()
        if config_path:
            logging.info('Assigned target path from config.')
            return config_path
        logging.info('Predicted target path from ML.')
        return self._predict_target_folder_path()

    def _get_date_for_file_name(self):
        """Tries each regex in the config to extract and parse a date from the text."""
        if not self.config:
            return None
        for regex_entry in self.config.get('regex_date', []):
            for match_str in re.findall(regex_entry['regex_string'], self.content):
                date_str = match_str
                for bad, good in _DATE_STRING_FIXES.items():
                    date_str = date_str.replace(bad, good)
                try:
                    fmt = regex_entry.get('extract_format')
                    date = dateparser.parse(
                        date_str,
                        date_formats=[fmt] if fmt else None,
                        languages=['en', 'fr']
                    )
                except Exception as e:
                    logging.error(f"Date parsing failed for '{date_str}': {e}")
                    date = None
                if date:
                    logging.info(f'Assigned date: {date}.')
                    return date
        logging.info('No date found.')
        return None

    def _get_target_filename(self) -> Optional[str]:
        """
        Generates a standardized filename from the config, or returns the original name.

        Returns:
            The new filename string, or the original name as a fallback.
        """
        if not self.config:
            return self.name

        _, ext = os.path.splitext(self.name)
        base_name = self.config.get('filename_base', '')
        date_part = ""

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

        if base_name and date_part:
            return f"{base_name} - {date_part}{ext}"
        elif base_name:
            return f"{base_name}{ext}"
        else:
            logging.warning(f"Config for '{self.name}' is missing 'filename_base'. Reverting to original name.")
            return self.name

    def rename_and_sort(self) -> None:
        """Orchestrates the full process of renaming and sorting the file on Google Drive."""
        if not self.target_folder_path or not self.new_filename:
            logging.error(f"Aborting sort for '{self.name}': missing target path or new filename.")
            return

        logging.info(f"--- Starting processing for file: {self.name} ---")

        target_folder_id = self._drive_manager.create_folder_by_path(self.target_folder_path)
        if not target_folder_id:
            logging.error(f"Could not find or create target folder for path '{self.target_folder_path}'. Aborting.")
            return

        needs_rename = (self.name != self.new_filename) and self.has_all_elements_to_move_and_rename_from_config
        if needs_rename:
            rename_success = self._drive_manager.rename_file(self._file_id, self.new_filename)
            logging.info(f"File '{self.name}' renamed to '{self.new_filename}'.")
            if not rename_success:
                logging.error(f"Rename failed for file ID '{self._file_id}'. Skipping move.")
                return
        else:
            logging.info(f"File '{self.name}' already has the correct name. Skipping rename.")

        needs_move = self._parent_folder_id != target_folder_id
        if needs_move:
            self._drive_manager.move_file(self._file_id, target_folder_id)
            logging.info(f"File moved to '{self.target_folder_path}'.")
        else:
            logging.info(f"File is already in the correct folder. Skipping move.")

        original_info = f"New file: '{self.name}' in folder '{self.parent_folder_name}'."
        actions_taken = []
        if needs_rename:
            actions_taken.append(f"Renamed to '{self.new_filename}'.")
        if needs_move:
            actions_taken.append(f"Moved to '{self.target_folder_path}'.")

        pushover_seb.pushover_send(
            msg_title="File Processed",
            msg=f"{original_info}\nActions: {' '.join(actions_taken)}",
            api_token=self._pushover_creds['API'],
            user_key=self._pushover_creds['user']
        )

        logging.info(f"+++ Successfully processed '{self.new_filename}'. +++")
