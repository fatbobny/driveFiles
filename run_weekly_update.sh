#!/bin/bash
PROJECT_DIR="/Users/sebastienmailleux/Library/CloudStorage/GoogleDrive-sebastien.mailleux@gmail.com/My Drive/Python/2025_file_management/pythonProject"
cd "$PROJECT_DIR"
".venv/bin/python" -c "
from create_learning_material import generate_learning_material
generate_learning_material(auto=True)
"
