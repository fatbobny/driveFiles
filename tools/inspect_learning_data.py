import json
import os
import shutil
from datetime import datetime

DATASET_PATH = os.path.join('learning_data', 'file_sorting_dataset.json')
SEARCH_KEYWORD = "old"


def load_dataset():
    if not os.path.exists(DATASET_PATH):
        print(f"Dataset not found at '{DATASET_PATH}'")
        return None
    with open(DATASET_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def inspect():
    data = load_dataset()
    if data is None:
        return

    matches = [e for e in data if SEARCH_KEYWORD.lower() in e.get('target_path', '').lower()]

    print(f"Total entries: {len(data)}")
    print(f"Entries with '{SEARCH_KEYWORD}' in target_path: {len(matches)}\n")

    for entry in matches:
        print(f"  {entry.get('target_path')} | {entry.get('file_name')}")


def delete_matches():
    data = load_dataset()
    if data is None:
        return

    matches = [e for e in data if SEARCH_KEYWORD.lower() in e.get('target_path', '').lower()]

    if not matches:
        print(f"No entries with '{SEARCH_KEYWORD}' in target_path. Nothing to delete.")
        return

    print(f"Found {len(matches)} entries to delete:")
    for entry in matches:
        print(f"  {entry.get('target_path')} | {entry.get('file_name')}")

    confirm = input(f"\nDelete these {len(matches)} entries? (yes/no): ").strip().lower()
    if confirm != 'yes':
        print("Aborted.")
        return

    # Backup before modifying
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join('learning_data', f"file_sorting_dataset_{timestamp}.json")
    shutil.copy2(DATASET_PATH, backup_path)
    print(f"Backup created at '{backup_path}'")

    cleaned = [e for e in data if SEARCH_KEYWORD.lower() not in e.get('target_path', '').lower()]
    with open(DATASET_PATH, 'w', encoding='utf-8') as f:
        json.dump(cleaned, f, indent=4, ensure_ascii=False)

    print(f"Deleted {len(matches)} entries. Dataset now has {len(cleaned)} entries.")


FOLDERS_TO_DELETE = [
    # Add folder paths here before running delete_by_folders(), e.g.:
    # "Documents/Health/Z. Old/Claims HK/Old",
]


def delete_by_folders(folders=None):
    data = load_dataset()
    if data is None:
        return

    if folders is None:
        folders = FOLDERS_TO_DELETE

    if not folders:
        print("No folders specified in FOLDERS_TO_DELETE.")
        return

    def matches_any(e):
        path = e.get('target_path', '')
        return any(path == folder or path.startswith(folder + '/') for folder in folders)

    matches = [e for e in data if matches_any(e)]

    if not matches:
        print("No entries found for the specified folders.")
        return

    print(f"Found {len(matches)} entries to delete:")
    for e in matches:
        print(f"  {e.get('target_path')} | {e.get('file_name')}")

    confirm = input(f"\nDelete these {len(matches)} entries? (yes/no): ").strip().lower()
    if confirm != 'yes':
        print("Aborted.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join('learning_data', f"file_sorting_dataset_{timestamp}.json")
    shutil.copy2(DATASET_PATH, backup_path)
    print(f"Backup created at '{backup_path}'")

    cleaned = [e for e in data if not matches_any(e)]
    with open(DATASET_PATH, 'w', encoding='utf-8') as f:
        json.dump(cleaned, f, indent=4, ensure_ascii=False)

    print(f"Deleted {len(matches)} entries. Dataset now has {len(cleaned)} entries.")


if __name__ == '__main__':
    inspect()
