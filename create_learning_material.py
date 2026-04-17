import os
import json
import logging
import googleDriveAPI as drive

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def scan_folder(dm, folder_id, current_path="Documents", filter_mime_types=['application/pdf', 'image/']):
    """
    Recursively scans a Google Drive folder and its subfolders to build a dataset
    mapping file contents to their logical path.
    """
    files_data = []
    
    # Use the list_files_in_folder from your GoogleDriveFileManager
    items = dm.list_files_in_folder(folder_id)
    
    for item in items:
        item_id = item['id']
        item_name = item['name']
        mime_type = item['mimeType']
        
        # If it's a folder, recursively scan it
        if mime_type == 'application/vnd.google-apps.folder':
            subfolder_path = os.path.join(current_path, item_name)
            logging.info(f"Scanning subfolder: {subfolder_path}")
            # Extend data with subfolder files
            files_data.extend(scan_folder(dm, item_id, subfolder_path, filter_mime_types))
        else:
            # We only care about file types we can extract text from (PDFs, Images)
            if any(filter_type in mime_type for filter_type in filter_mime_types):
                logging.info(f"Extracting content for: {item_name} in {current_path}")
                # Leverage the existing content extraction method in your API
                file_details = dm.get_file_details_and_extract_content(file_id=item_id)
                
                # Check if text was successfully extracted
                if file_details.get('extracted_text'):
                    files_data.append({
                        'file_name': item_name,
                        'target_path': current_path,
                        'extracted_text': file_details['extracted_text'],
                        'mime_type': mime_type
                    })
                else:
                    logging.warning(f"No text extracted for {item_name}")
            else:
                logging.debug(f"Skipping unsupported file type: {item_name} ({mime_type})")
            
    return files_data

def generate_learning_material():
    # Establish connection to Google Drive using existing credentials
    dm = drive.GoogleDriveFileManager(
        credentials_path='config/google_credentials.json',
        token_path='config/google_token.json'
    )

    target_folder_name = "Documents"
    # Assuming Documents is a top level folder in 'My Drive' (root)
    documents_folder_id = dm.find_folder_id_by_name(target_folder_name, parent_folder_id='root')

    if not documents_folder_id:
        logging.error(f"Folder '{target_folder_name}' not found in root.")
        return

    logging.info(f"Found '{target_folder_name}' folder (ID: {documents_folder_id}). Starting scan...")
    
    # Start scanning from the root of the Documents folder
    learning_data = scan_folder(dm, documents_folder_id, current_path="Documents")

    output_dir = 'learning_data'
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, 'file_sorting_dataset.json')

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(learning_data, f, indent=4, ensure_ascii=False)

    logging.info(f"Successfully created learning material with {len(learning_data)} examples at '{output_file}'")

if __name__ == '__main__':
    generate_learning_material()
