#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
.venv/.venv/bin/python create_learning_material.py
