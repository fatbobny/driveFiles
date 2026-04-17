import json
import logging
import sys
import time
import calendar
import datetime
import pickle
import os
import sklearn #pip install scikit-learn

def extract_json_content(json_file_path):
    """
    Extracts and returns the content of a JSON file.

    Args:
        json_file_path (str): The path to the JSON file.

    Returns:
        dict or list: The content of the JSON file as a Python dictionary or list,
                     or None if an error occurred.
    """
    try:
        with open(json_file_path, "r") as f:
            config_data = json.load(f)
            return config_data
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {json_file_path}")
        logging.error(f"Error: Configuration file not found at {json_file_path}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in {json_file_path}")
        logging.error(f"Error: Invalid JSON format in {json_file_path}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while loading the JSON file: {e}")
        logging.error(f"An unexpected error occurred while loading the JSON file: {e}")
        return None

def countdown(t):
    """Displays a dynamic countdown timer in the terminal."""
    while t:
        mins, secs = divmod(t, 60)
        timer = '{:02d}:{:02d}'.format(mins, secs)
        # Use carriage return (\r) to overwrite the previous line
        sys.stdout.write(f"\rTime remaining before refresh: {timer}")
        sys.stdout.flush()  # Ensure the output is immediately displayed
        time.sleep(1)
        t -= 1

    # # Get current date and time in European format
    # now = datetime.datetime.now()
    # european_time = now.strftime("%d/%m/%Y %H:%M:%S")

    # print(f"\rRefreshing: {european_time}   ")
    # print(f"\r   ")

def add_months(source_date, months):
    """
    Adds a specified number of months to a given date, handling month and year rollovers
    and ensuring the day remains valid for the new month.

    Args:
        source_date (datetime.date): The original date.
        months (int): The number of months to add (can be positive or negative).

    Returns:
        datetime.date: The new date after adding the months.
    """
    # add months to a date
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)

def get_latest_file_in_folder(folder, root, extension):
    # get all the files in the folder
    list_all_files = [i for i in os.listdir(os.path.join(folder)) if root in i]
    list_dates = [i[len(root):-4] for i in list_all_files]
    latest_file = root + max(list_dates) + extension
    print(f'latest {root} file in {folder} : {latest_file}')
    return latest_file

def load_ML_config(folder_models , rootRegression, rootVectorizer,extensionModels):

    # Machine learning tagging
    # folder_models = './Models'  # folder containing Models and names of the root files
    # rootRegression = 'linear_regression_'
    # rootVectorizer = 'linear_reg_vectorizer_'
    # extensionModels = '.sav'
    model = pickle.load(
        open(folder_models + '/' + get_latest_file_in_folder(folder_models, rootRegression, extensionModels), 'rb'))
    vectorizer = pickle.load(
        open(folder_models + '/' + get_latest_file_in_folder(folder_models, rootVectorizer, extensionModels), 'rb'))

    return model, vectorizer