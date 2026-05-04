import ipywidgets as widgets
from IPython.display import display, HTML
import json
import re
from datetime import datetime
import pyperclip
import dateparser
from googleDriveAPI import GoogleDriveFileManager
from drive_file import DriveFile
import pushover_seb

# --- Helper Functions ---
def check_keywords(text, keywords):
    """Checks for the presence of all keywords in the text, case-insensitively."""
    if not text: return keywords
    missing = [kw for kw in keywords if kw.lower() not in text.lower()]
    return missing

def extract_date_from_text(text, regex_list):
    """Tries a list of regex patterns to find and parse a date using the dateparser library."""
    if not text: return None, None

    for item in regex_list:
        regex_pattern = item.get('regex_string')
        if not regex_pattern: continue
        try:
            match = re.search(regex_pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                date_str = match.group(1) if match.groups() else match.group(0)

                # Use dateparser for robust parsing, which handles multiple languages and formats
                date_formats = [item.get('extract_format')] if item.get('extract_format') else None
                parsed_date = dateparser.parse(date_str, date_formats=date_formats, languages=['en', 'fr'])

                if parsed_date:
                    return parsed_date, regex_pattern

        except re.error as e:
            print(f"Warning: Invalid regex '{regex_pattern}': {e}")
            continue
    return None, None

# --- UI and Business Logic ---
def create_interface(drive_manager, pdf_configs, files_in_folder, config_path, folder_name="B_To Automate in Python"):
    """Creates the full UI, wires up the events, and displays it."""
    current_globals = {
        'current_file_details': None,
        'current_file_label': None
    }

    file_dropdown = widgets.Dropdown(options=files_in_folder, description='1. Select File to Test:', style={'description_width': 'initial'}, layout={'width': '95%'})
    refresh_files_button = widgets.Button(description='Refresh File List', button_style='info', icon='refresh', tooltip='Reloads the list of files from Google Drive.', layout={'width': '95%'})
    config_dropdown = widgets.Dropdown(options=sorted(pdf_configs.keys()), description='2. Select Config to Use:', style={'description_width': 'initial'}, layout={'width': '95%'})
    test_button = widgets.Button(description='3. Test Selected Config', button_style='primary', icon='cogs', tooltip='Fetches file from Drive and tests the chosen configuration.', layout={'width': '95%'})
    reload_button = widgets.Button(description='4. Reload Config & Re-Test', button_style='info', icon='refresh', tooltip='Reloads config_pdf.json and tests the same file data again.', layout={'width': '95%'})
    process_button = widgets.Button(description='5. Process File (Rename & Sort)', button_style='success', icon='check', tooltip='Applies the config to rename and move the file in Google Drive.', layout={'width': '95%'})
    test_output_area = widgets.Output()

    def run_and_display_analysis(file_text, file_label, config_name, configs, is_retest=False):
        selected_config = configs.get(config_name, {})
        missing_keywords = check_keywords(file_text, selected_config.get('keywords', []))
        found_date, regex_used = extract_date_from_text(file_text, selected_config.get('regex_date', []))
        test_type = "Re-Testing" if is_retest else "Testing"
        config_source = "Reloaded Config" if is_retest else "Config"
        target_folder = selected_config.get('target_folder', 'N/A')
        
        try:
            pyperclip.copy(file_text)
            clipboard_msg = "(copied to clipboard)"
        except pyperclip.PyperclipException:
            clipboard_msg = "<font color='orange'>(could not copy to clipboard)</font>"

        display(HTML(f"<h3>{test_type} File: <code>{file_label}</code></h3>"))
        display(HTML(f"<h4>Against {config_source}: <code>{config_name}</code></h4>"))
        display(HTML(f"<b>Target Folder:</b> <code>{target_folder}</code>"))
        display(HTML(f"<b>Regex Date Config:</b> <code>{json.dumps(selected_config.get('regex_date', []))}</code>"))

        if not missing_keywords:
            display(HTML("<h4><font color='green'>✅ Config Keywords Match</font></h4>"))
        else:
            display(HTML("<h4><font color='red'>❌ Config Keywords Do Not Match</font></h4>"))
            display(HTML(f"<b>Missing Keywords:</b> {', '.join(missing_keywords)}"))
        if found_date:
            display(HTML(f"<b>Date Extracted:</b> {found_date.strftime('%Y-%m-%d')}"))
            display(HTML(f"<b>Using Regex:</b> <code>{regex_used}</code>"))
        else:
            display(HTML("<b>Date Extracted:</b> <font color='orange'>Could not extract a date.</font>"))
        display(HTML(f"<hr><h3>Full Extracted Text: {clipboard_msg}</h3><p style='white-space: pre-wrap; padding: 10px; border-radius: 5px;'>{file_text}</p>"))

    def on_refresh_files_button_clicked(b):
        with test_output_area:
            test_output_area.clear_output()
            print(f"Refreshing file list from '{folder_name}'...")
            try:
                folder_id = drive_manager.find_folder_id_by_name(folder_name)
                if folder_id:
                    all_files = drive_manager.list_files_in_folder(folder_id)
                    new_files = [(f['name'], f['id']) for f in all_files if 'pdf' in f.get('mimeType', '') or 'image' in f.get('mimeType', '')]
                    file_dropdown.options = new_files
                    print(f"Found {len(new_files)} files.")
                else:
                    print(f"Error: Could not find folder '{folder_name}'.")
            except Exception as e:
                print(f"Error refreshing files: {e}")

    def on_test_button_clicked(b):
        file_id = file_dropdown.value
        config_name = config_dropdown.value
        with test_output_area:
            test_output_area.clear_output()
            if not file_id or not config_name:
                print("Error: Please select both a file and a configuration.")
                return
            print(f"Fetching details for file: {file_dropdown.label}...")
            file_details = drive_manager.get_file_details_and_extract_content(file_id)
            test_output_area.clear_output()
            if file_details.get('error') or not file_details.get('extracted_text'):
                print(f"Error: Could not extract text. {file_details.get('error', '')}")
                return
            current_globals['current_file_details'] = file_details
            current_globals['current_file_label'] = file_dropdown.label
            run_and_display_analysis(current_globals['current_file_details']['extracted_text'],
                                     current_globals['current_file_label'], config_name, pdf_configs)

    def on_reload_button_clicked(b):
        config_name = config_dropdown.value
        with test_output_area:
            test_output_area.clear_output()
            if not current_globals.get('current_file_details'):
                print("Please run '3. Test Selected Config' first.")
                return
            print(f"Reloading {config_path} and re-testing...")
            try:
                with open(config_path, 'r') as f:
                    reloaded_pdf_configs = json.load(f)
                config_dropdown.options = sorted(reloaded_pdf_configs.keys())
                config_dropdown.value = config_name if config_name in reloaded_pdf_configs else None
                test_output_area.clear_output()
            except Exception as e:
                print(f"Error reloading config file: {e}")
                return
            run_and_display_analysis(current_globals['current_file_details']['extracted_text'],
                                     current_globals['current_file_label'], config_name,
                                     reloaded_pdf_configs, is_retest=True)

    def on_process_button_clicked(b):
        with test_output_area:
            test_output_area.clear_output()
            if not current_globals.get('current_file_details'):
                print("Error: Please run '3. Test Selected Config' first.")
                return
            print(f"Processing file: {current_globals.get('current_file_label')}...")
            try:
                with open(config_path, 'r') as f:
                    latest_pdf_configs = json.load(f)
                with open('config/pushover_config.json', 'r') as f:
                    pushover_creds = json.load(f)
                drive_file_instance = DriveFile(
                    file_details=current_globals['current_file_details'],
                    drive_manager=drive_manager,
                    pdf_configs=latest_pdf_configs,
                    ml_model=None,
                    ml_vectorizer=None,
                    pushover_creds=pushover_creds
                )
                print("Calling rename_and_sort()...")
                drive_file_instance.rename_and_sort()
                print("\n--- Processing Complete ---")
                display(HTML("<h4><font color='green'>✅ File processed successfully.</font> Check Google Drive.</h4>"))
            except FileNotFoundError:
                print("\nError: Could not find 'config/pushover_config.json'.")
            except Exception as e:
                print(f"\nAn error occurred during processing: {e}")

    refresh_files_button.on_click(on_refresh_files_button_clicked)
    test_button.on_click(on_test_button_clicked)
    reload_button.on_click(on_reload_button_clicked)
    process_button.on_click(on_process_button_clicked)
    ui_layout = widgets.VBox([file_dropdown, refresh_files_button, config_dropdown, test_button, reload_button, process_button, test_output_area])
    display(ui_layout)
