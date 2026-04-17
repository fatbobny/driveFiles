import json
import os

file_path = 'learning_data/file_sorting_dataset copy.json'

with open(file_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

filtered_data = [
    entry for entry in data 
    if not (entry.get('target_path', '').startswith('Documents/Z _ old') or 
            entry.get('target_path', '').startswith('Documents/Z _ others'))
]

with open(file_path, 'w', encoding='utf-8') as f:
    json.dump(filtered_data, f, indent=4, ensure_ascii=False)

print(f"Removed {len(data) - len(filtered_data)} entries.")
