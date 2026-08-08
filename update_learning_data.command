#!/bin/bash
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:$PATH"
/opt/homebrew/bin/python3.12 create_learning_material.py
