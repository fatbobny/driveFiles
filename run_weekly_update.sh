#!/bin/bash
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="/opt/homebrew/bin/python3.12"
export PATH="/opt/homebrew/bin:$PATH"
cd "$PROJECT_DIR"
export PYTHONPATH="$PROJECT_DIR:$PROJECT_DIR/tools"
"$PYTHON" -c "
from create_learning_material import generate_learning_material
generate_learning_material(auto=True)
"