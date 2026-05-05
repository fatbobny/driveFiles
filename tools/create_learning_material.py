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
                   existing_keys=None):
    """
    Recursively scans Drive folders and returns metadata for new files (no extraction).
    """
    if filter_mime_types is None:
        filter_mime_types = ['application/pdf', 'image/']
    if existing_keys is None:
        existing_keys = set()

    print(f"  Scanning: {current_path}")
    found = []
    items = dm.list_files_in_folder(folder_id)

    for item in items:
        item_name = item['name']
        mime_type = item['mimeType']

        if mime_type == 'application/vnd.google-apps.folder':
            if _should_skip_folder(item_name, current_path):
                print(f"  Skipping: {os.path.join(current_path, item_name)}")
                continue
            subfolder_path = os.path.join(current_path, item_name)
            found.extend(list_new_files(dm, item['id'], subfolder_path, filter_mime_types, existing_keys))
        else:
            if any(filter_type in mime_type for filter_type in filter_mime_types):
                if (item_name, current_path) not in existing_keys:
                    print(f"    + {item_name}")
                    found.append({'id': item['id'], 'name': item_name, 'path': current_path, 'mimeType': mime_type})
                else:
                    print(f"    ~ {item_name} (already extracted)")

    return found

EXCLUDED_FILES_PATH = os.path.join('learning_data', 'excluded_files.json')


def load_excluded_keys():
    if not os.path.exists(EXCLUDED_FILES_PATH):
        return set()
    with open(EXCLUDED_FILES_PATH, 'r', encoding='utf-8') as f:
        entries = json.load(f)
    return {(e['file_name'], e['target_path']) for e in entries}


def save_excluded_files(new_failures):
    existing = []
    if os.path.exists(EXCLUDED_FILES_PATH):
        with open(EXCLUDED_FILES_PATH, 'r', encoding='utf-8') as f:
            existing = json.load(f)
    existing_keys = {(e['file_name'], e['target_path']) for e in existing}
    to_add = [e for e in new_failures if (e['file_name'], e['target_path']) not in existing_keys]
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
                    'file_name': item['name'],
                    'target_path': item['path'],
                    'mime_type': item['mimeType']
                })
    if failed:
        save_excluded_files(failed)
        print(f"\n{len(failed)} failed file(s) added to exclusion list.")
    return files_data

def _clean_excluded_files(drive_keys):
    """Remove entries from excluded_files.json that no longer exist on Drive."""
    if not os.path.exists(EXCLUDED_FILES_PATH):
        return 0
    with open(EXCLUDED_FILES_PATH, 'r', encoding='utf-8') as f:
        existing = json.load(f)
    kept = [e for e in existing if (e['file_name'], e['target_path']) in drive_keys]
    removed = len(existing) - len(kept)
    if removed:
        with open(EXCLUDED_FILES_PATH, 'w', encoding='utf-8') as f:
            json.dump(kept, f, indent=4, ensure_ascii=False)
    return removed


def generate_learning_material(auto=False):
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
    reference_file = '/Users/sebastienmailleux/Library/CloudStorage/GoogleDrive-sebastien.mailleux@gmail.com/My Drive/Claude Cowork/File Sorting/file_sorting_dataset.json'

    # Load existing dataset from the reference file (source of truth)
    existing_data = []
    source_file = reference_file if os.path.exists(reference_file) else output_file
    if os.path.exists(source_file):
        with open(source_file, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        print(f"Loaded {len(existing_data)} existing entries from '{source_file}'.")

    # Scan ALL Drive files first (no exclusions) to build the ground truth
    print(f"\nFound '{target_folder_name}' folder (ID: {documents_folder_id}). Scanning all files on Drive...")
    all_drive_files = list_new_files(dm, documents_folder_id, current_path="Documents", existing_keys=set())
    drive_keys = {(f['name'], f['path']) for f in all_drive_files}

    # --- Step 1: Identify stale entries ---
    stale = [e for e in existing_data if (e['file_name'], e['target_path']) not in drive_keys]
    clean_data = [e for e in existing_data if (e['file_name'], e['target_path']) in drive_keys]

    # Count stale exclusions (removal deferred until after confirmation)
    stale_excluded_count = 0
    if os.path.exists(EXCLUDED_FILES_PATH):
        with open(EXCLUDED_FILES_PATH, 'r', encoding='utf-8') as f:
            excluded_entries = json.load(f)
        stale_excluded_count = sum(1 for e in excluded_entries if (e['file_name'], e['target_path']) not in drive_keys)

    if stale:
        print(f"\n{len(stale)} stale dataset entry(ies) to remove (file no longer on Drive):")
        for e in stale:
            print(f"  - {e['target_path']}/{e['file_name']}")
    if stale_excluded_count:
        print(f"{stale_excluded_count} stale exclusion entry(ies) to remove.")

    # --- Step 2: Find new files ---
    excluded_keys = load_excluded_keys()
    dataset_keys = {(e['file_name'], e['target_path']) for e in clean_data}
    skip_keys = dataset_keys | excluded_keys
    new_files = [f for f in all_drive_files if (f['name'], f['path']) not in skip_keys]

    if new_files:
        print(f"\n{len(new_files)} new file(s) to extract:")
        for f in new_files:
            print(f"  + {f['path']}/{f['name']}")

    if not stale and not stale_excluded_count and not new_files:
        print("\nDataset is up to date. Nothing to do.")
        return

    print()
    if not auto:
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer != 'y':
            logging.info("Cancelled by user.")
            return

    # Apply deferred exclusion cleanup now that user confirmed
    excluded_removed = _clean_excluded_files(drive_keys)

    # Backup before any write
    if os.path.exists(output_file):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(output_dir, f"file_sorting_dataset_{timestamp}.json")
        shutil.copy2(output_file, backup_file)
        logging.info(f"Backup created at '{backup_file}'")

    new_data = extract_files(dm, new_files) if new_files else []
    learning_data = clean_data + new_data

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(learning_data, f, indent=4, ensure_ascii=False)

    shutil.copy2(output_file, reference_file)
    print(f"Dataset copied to '{reference_file}'")

    parts = []
    if stale:
        parts.append(f"removed {len(stale)} stale entry(ies)")
    if new_data:
        parts.append(f"added {len(new_data)} new entry(ies)")
    msg = f"{'; '.join(parts).capitalize()}. Dataset now has {len(learning_data)} total examples."
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

    # Load keys already successfully extracted
    extracted_keys = set()
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        extracted_keys = {(e['file_name'], e['target_path']) for e in existing_data}
        logging.info(f"Dataset has {len(extracted_keys)} successfully extracted files.")

    already_excluded_keys = load_excluded_keys()

    # Scan all files (no exclusions so we see everything)
    logging.info("Scanning Drive for all files...")
    all_files = list_new_files(dm, documents_folder_id, current_path="Documents", existing_keys=set())

    missing = [
        f for f in all_files
        if (f['name'], f['path']) not in extracted_keys
        and (f['name'], f['path']) not in already_excluded_keys
        and '2026' not in f['name']
    ]

    skipped_recent = [f for f in all_files if (f['name'], f['path']) not in extracted_keys and '2026' in f['name']]

    print(f"\nTotal files found on Drive:      {len(all_files)}")
    print(f"Already extracted:               {len(extracted_keys)}")
    print(f"Already excluded:                {len(already_excluded_keys)}")
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
        {'file_name': f['name'], 'target_path': f['path'], 'mime_type': f['mimeType']}
        for f in missing
    ]
    save_excluded_files(to_exclude)
    print(f"Done. {len(to_exclude)} file(s) added to '{EXCLUDED_FILES_PATH}'.")


if __name__ == '__main__':
    generate_learning_material()