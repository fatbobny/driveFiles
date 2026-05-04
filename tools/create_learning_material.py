import os
import json
import logging
import shutil
from datetime import datetime
import googleDriveAPI as drive
import pushover_seb as pushover
from basicfunctions import extract_json_content

# Configure logging
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

IGNORED_FOLDER_KEYWORDS = ["old", "others"]
IGNORED_FOLDER_PATHS = ["Documents/Admin/Con Edison"]

def _should_skip_folder(name, current_path=""):
    name_lower = name.lower()
    if any(kw in name_lower for kw in IGNORED_FOLDER_KEYWORDS):
        return True
    full_path = os.path.join(current_path, name)
    return any(full_path == ignored or full_path.startswith(ignored + os.sep) for ignored in IGNORED_FOLDER_PATHS)

def list_new_files(dm, folder_id, current_path="Documents", filter_mime_types=None,
                   existing_ids=None):
    """
    Recursively scans Drive folders and returns metadata for new files (no extraction).
    """
    if filter_mime_types is None:
        filter_mime_types = ['application/pdf', 'image/']
    if existing_ids is None:
        existing_ids = set()

    print(f"  Scanning: {current_path}")
    found = []
    items = dm.list_files_in_folder(folder_id)

    for item in items:
        item_id = item['id']
        item_name = item['name']
        mime_type = item['mimeType']

        if mime_type == 'application/vnd.google-apps.folder':
            if _should_skip_folder(item_name, current_path):
                print(f"  Skipping: {os.path.join(current_path, item_name)}")
                continue
            subfolder_path = os.path.join(current_path, item_name)
            found.extend(list_new_files(dm, item_id, subfolder_path, filter_mime_types, existing_ids))
        else:
            if any(filter_type in mime_type for filter_type in filter_mime_types):
                if item_id not in existing_ids:
                    print(f"    + {item_name}")
                    found.append({'id': item_id, 'name': item_name, 'path': current_path, 'mimeType': mime_type})
                else:
                    print(f"    ~ {item_name} (already extracted)")

    return found

EXCLUDED_FILES_PATH = os.path.join('learning_data', 'excluded_files.json')


def load_excluded_ids():
    if not os.path.exists(EXCLUDED_FILES_PATH):
        return set()
    with open(EXCLUDED_FILES_PATH, 'r', encoding='utf-8') as f:
        entries = json.load(f)
    return {e['file_id'] for e in entries}


def save_excluded_files(new_failures):
    existing = []
    if os.path.exists(EXCLUDED_FILES_PATH):
        with open(EXCLUDED_FILES_PATH, 'r', encoding='utf-8') as f:
            existing = json.load(f)
    existing_ids = {e['file_id'] for e in existing}
    to_add = [e for e in new_failures if e['file_id'] not in existing_ids]
    if to_add:
        updated = existing + to_add
        with open(EXCLUDED_FILES_PATH, 'w', encoding='utf-8') as f:
            json.dump(updated, f, indent=4, ensure_ascii=False)
        logging.info(f"Added {len(to_add)} file(s) to exclusion list.")


def extract_files(dm, new_files):
    """
    Extracts text from a list of file metadata dicts returned by list_new_files.
    Files that fail extraction are added to the exclusion list (unless "2026" is in the name).
    """
    files_data = []
    failed = []
    total = len(new_files)
    for i, item in enumerate(new_files, start=1):
        print(f"[{i}/{total}] {item['path']}/{item['name']} ... ", end="", flush=True)
        file_details = dm.get_file_details_and_extract_content(file_id=item['id'])
        if file_details.get('extracted_text'):
            print("OK")
            files_data.append({
                'file_id': item['id'],
                'file_name': item['name'],
                'target_path': item['path'],
                'extracted_text': file_details['extracted_text'],
                'mime_type': item['mimeType']
            })
        else:
            print("FAILED (no text extracted)")
            if '2026' not in item['name']:
                failed.append({
                    'file_id': item['id'],
                    'file_name': item['name'],
                    'target_path': item['path'],
                    'mime_type': item['mimeType']
                })
    if failed:
        save_excluded_files(failed)
        print(f"\n{len(failed)} failed file(s) added to exclusion list.")
    return files_data

def can_we_generate_learning_material(auto=False):
    dm = drive.GoogleDriveFileManager(
        credentials_path='config/google_credentials.json',
        token_path='config/google_token.json'
    )

    target_folder_name = "Documents"
    documents_folder_id = dm.find_folder_id_by_name(target_folder_name, parent_folder_id='root')

    if not documents_folder_id:
        logging.error(f"Folder '{target_folder_name}' not found in root.")
        return

    output_dir = 'learning_data'
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, 'file_sorting_dataset.json')

    # Load existing dataset to enable incremental updates
    existing_data = []
    existing_ids = set()
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        existing_ids = {entry['file_id'] for entry in existing_data if 'file_id' in entry}
        logging.info(f"Loaded {len(existing_data)} existing entries, will skip {len(existing_ids)} already-extracted files.")
        print(f"Loaded {len(existing_data)} existing entries, will skip {len(existing_ids)} already-extracted files.")

    excluded_ids = load_excluded_ids()
    logging.info(f"Exclusion list: {len(excluded_ids)} file(s) will be skipped.")
    print(f"Exclusion list: {len(excluded_ids)} file(s) will be skipped.")
    existing_ids |= excluded_ids

    logging.info(f"Found '{target_folder_name}' folder (ID: {documents_folder_id}). Scanning for new files...")
    print(f"Found '{target_folder_name}' folder (ID: {documents_folder_id}). Scanning for new files...")
    new_files = list_new_files(dm, documents_folder_id, current_path="Documents", existing_ids=existing_ids)

    if not new_files:
        logging.info("No new files found. Dataset is up to date.")
        print("No new files found. Dataset is up to date.")
        return

    print(f"\n{len(new_files)} new file(s) to extract:\n")
    for f in new_files:
        print(f"  {f['path']}/{f['name']}")
    print()

    if not auto:
        answer = input("Proceed with extraction? [y/N] ").strip().lower()
        if answer != 'y':
            logging.info("Extraction cancelled by user.")
            return

    # Backup only when actually about to write
    if os.path.exists(output_file):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(output_dir, f"file_sorting_dataset_{timestamp}.json")
        shutil.copy2(output_file, backup_file)
        logging.info(f"Backup created at '{backup_file}'")

    new_data = extract_files(dm, new_files)
    learning_data = existing_data + new_data

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(learning_data, f, indent=4, ensure_ascii=False)

    copy_dest = '/Users/sebastienmailleux/Library/CloudStorage/GoogleDrive-sebastien.mailleux@gmail.com/My Drive/Claude Cowork/File Sorting/file_sorting_dataset.json'
    shutil.copy2(output_file, copy_dest)
    print(f"Dataset copied to '{copy_dest}'")

    msg = f"Added {len(new_data)} new entries. Dataset now has {len(learning_data)} total examples."
    logging.info(msg)
    print(msg)

    try:
        creds = extract_json_content('config/pushover_config.json')
        pushover.pushover_send(
            msg_title="Learning data updated",
            msg=msg,
            api_token=creds['API'],
            user_key=creds['user']
        )
    except Exception as e:
        logging.error(f"Pushover notification failed: {e}")

def init_exclusion_list():
    """
    Scans Drive and adds to excluded_files.json any file not already in the dataset.
    Files with '2026' in the name are kept for future extraction and not excluded.
    """
    dm = drive.GoogleDriveFileManager(
        credentials_path='config/google_credentials.json',
        token_path='config/google_token.json'
    )

    target_folder_name = "Documents"
    documents_folder_id = dm.find_folder_id_by_name(target_folder_name, parent_folder_id='root')
    if not documents_folder_id:
        logging.error(f"Folder '{target_folder_name}' not found in root.")
        return

    output_dir = 'learning_data'
    output_file = os.path.join(output_dir, 'file_sorting_dataset.json')

    # Load IDs already successfully extracted
    extracted_ids = set()
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        extracted_ids = {e['file_id'] for e in existing_data if 'file_id' in e}
        logging.info(f"Dataset has {len(extracted_ids)} successfully extracted files.")

    already_excluded_ids = load_excluded_ids()

    # Scan all files (no exclusions so we see everything)
    logging.info("Scanning Drive for all files...")
    all_files = list_new_files(dm, documents_folder_id, current_path="Documents", existing_ids=set())

    missing = [
        f for f in all_files
        if f['id'] not in extracted_ids
        and f['id'] not in already_excluded_ids
        and '2026' not in f['name']
    ]

    skipped_recent = [f for f in all_files if f['id'] not in extracted_ids and '2026' in f['name']]

    print(f"\nTotal files found on Drive:      {len(all_files)}")
    print(f"Already extracted:               {len(extracted_ids)}")
    print(f"Already excluded:                {len(already_excluded_ids)}")
    print(f"Skipped (2026 in name):          {len(skipped_recent)}")
    print(f"New files to exclude:            {len(missing)}")

    if not missing:
        print("Nothing new to add to the exclusion list.")
        return

    print("\nFiles that will be excluded:")
    for f in missing:
        print(f"  {f['path']}/{f['name']}")

    confirm = input(f"\nAdd these {len(missing)} file(s) to the exclusion list? (yes/no): ").strip().lower()
    if confirm != 'yes':
        print("Aborted.")
        return

    to_exclude = [
        {'file_id': f['id'], 'file_name': f['name'], 'target_path': f['path'], 'mime_type': f['mimeType']}
        for f in missing
    ]
    save_excluded_files(to_exclude)
    print(f"Done. {len(to_exclude)} file(s) added to '{EXCLUDED_FILES_PATH}'.")


if __name__ == '__main__':
    generate_learning_material()