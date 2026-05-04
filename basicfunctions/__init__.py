import json
import logging
import sys
import time
import calendar
import datetime
import pickle
import os


def extract_json_content(json_file_path):
    """
    Loads and returns the content of a JSON file.

    Args:
        json_file_path (str): Path to the JSON file.

    Returns:
        dict or list: Parsed JSON content, or None on error.
    """
    try:
        with open(json_file_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error(f"Configuration file not found: {json_file_path}")
        return None
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON format in {json_file_path}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error loading JSON file: {e}")
        return None


def countdown(t):
    """Displays a dynamic countdown timer in the terminal."""
    while t:
        mins, secs = divmod(t, 60)
        sys.stdout.write(f"\rTime remaining before refresh: {mins:02d}:{secs:02d}")
        sys.stdout.flush()
        time.sleep(1)
        t -= 1


def add_months(source_date, months):
    """
    Adds a number of months to a date, handling month/year rollovers and day clamping.

    Args:
        source_date (datetime.date): The original date.
        months (int): Number of months to add (positive or negative).

    Returns:
        datetime.date: The resulting date.
    """
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def get_latest_file_in_folder(folder, filename_prefix, extension):
    """
    Returns the filename of the most recent file in a folder that starts with filename_prefix.

    Args:
        folder (str): Directory to search.
        filename_prefix (str): Filename prefix to match (e.g. 'logistic_classifier_').
        extension (str): File extension (e.g. '.sav').

    Returns:
        str: The latest matching filename (not full path).
    """
    matching = [f for f in os.listdir(folder) if filename_prefix in f]
    dates = [f[len(filename_prefix):-len(extension)] for f in matching]
    return filename_prefix + max(dates) + extension


def load_ML_config(folder_models, rootRegression, rootVectorizer, extensionModels):
    """
    Loads the latest ML model and vectorizer from disk.

    Args:
        folder_models (str): Directory containing .sav model files.
        rootRegression (str): Filename prefix for the classifier model.
        rootVectorizer (str): Filename prefix for the vectorizer.
        extensionModels (str): File extension (e.g. '.sav').
        # pip install scikit-learn

    Returns:
        tuple: (model, vectorizer)
    """
    model = pickle.load(open(
        os.path.join(folder_models, get_latest_file_in_folder(folder_models, rootRegression, extensionModels)), 'rb'
    ))
    vectorizer = pickle.load(open(
        os.path.join(folder_models, get_latest_file_in_folder(folder_models, rootVectorizer, extensionModels)), 'rb'
    ))
    return model, vectorizer
