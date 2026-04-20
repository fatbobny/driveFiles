#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
python create_learning_material.py
