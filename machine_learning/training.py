import logging
import os
import sys
import pickle
import time
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

# Adjust path to import googleDriveAPI
# Assuming this script is run from the project root or machine_learning/
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from googleDriveAPI import GoogleDriveFileManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(current_dir, "training.log")),
        logging.StreamHandler()
    ]
)

class DriveModelTrainer:
    def __init__(self, credentials_path, token_path, cache_file=None):
        if cache_file is None:
            cache_file = os.path.join(current_dir, 'input_data', 'training_data_cache.pkl')
            
        self.dm = GoogleDriveFileManager(credentials_path=credentials_path, token_path=token_path)
        self.cache_file = cache_file
        self.cache = self.load_cache()
        self.files_to_process = []
        
    def load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'rb') as f:
                    logging.info(f"Loading cache from {self.cache_file}")
                    return pickle.load(f)
            except Exception as e:
                logging.error(f"Failed to load cache: {e}")
                return {}
        return {}

    def save_cache(self):
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, 'wb') as f:
            pickle.dump(self.cache, f)
        logging.info("Cache saved.")

    def list_all_files_in_folder(self, folder_id):
        files = []
        page_token = None
        q = f"'{folder_id}' in parents and trashed = false"
        while True:
            try:
                response = self.dm.drive_service.files().list(
                    q=q,
                    fields="nextPageToken, files(id, name, mimeType)",
                    pageToken=page_token
                ).execute()
                files.extend(response.get('files', []))
                page_token = response.get('nextPageToken')
                if not page_token:
                    break
            except Exception as e:
                logging.error(f"Error listing files in {folder_id}: {e}")
                break
        return files

    def traverse_folder(self, folder_id, current_path_parts):
        # logging.info(f"Scanning folder: {'/'.join(current_path_parts)}")
        items = self.list_all_files_in_folder(folder_id)
        
        for item in items:
            name = item['name']
            item_id = item['id']
            mime_type = item['mimeType']
            
            if mime_type == 'application/vnd.google-apps.folder':
                if "old" in name.lower() or "others" in name.lower():
                    logging.info(f"Skipping folder '{name}'")
                    continue
                
                self.traverse_folder(item_id, current_path_parts + [name])
            else:
                if 'application/pdf' in mime_type or 'image/' in mime_type:
                    # Determine label (2 levels deep)
                    # Example: Documents/Category/Subcategory/File.pdf -> Category/Subcategory
                    if len(current_path_parts) >= 2:
                        label = f"{current_path_parts[0]}/{current_path_parts[1]}"
                    elif len(current_path_parts) == 1:
                        label = current_path_parts[0]
                    else:
                        label = "Root"
                    
                    self.files_to_process.append({
                        'id': item_id,
                        'name': name,
                        'mime_type': mime_type,
                        'label': label,
                        'path': "/".join(current_path_parts)
                    })

    def find_documents_folder_id(self):
        # Try to find "Python rules refit" first
        root_folder_id = self.dm.find_folder_id_by_name("Python rules refit")
        if root_folder_id:
            logging.info(f"Found 'Python rules refit' ID: {root_folder_id}")
            docs_id = self.dm.find_folder_id_by_name("Documents", parent_folder_id=root_folder_id)
            if docs_id:
                return docs_id
        
        # Fallback
        logging.info("Could not find 'Documents' inside 'Python rules refit', searching globally.")
        return self.dm.find_folder_id_by_name("Documents")

    def collect_data(self):
        folder_id = self.find_documents_folder_id()
        if not folder_id:
            logging.error(f"Folder 'Documents' not found.")
            return
        
        logging.info(f"Found 'Documents' folder with ID: {folder_id}")
        self.traverse_folder(folder_id, [])
        
        logging.info(f"Found {len(self.files_to_process)} potential training files.")
        
        # Extract content
        count = 0
        for file_info in self.files_to_process:
            file_id = file_info['id']
            if file_id in self.cache:
                # Check if content is valid (not empty string if we want to retry empty ones, but here we assume empty means no text found)
                # If we want to retry failed extractions, we could check if content is empty.
                # For now, assume cache is authoritative.
                continue
            
            logging.info(f"Extracting content for {file_info['name']} ({count + 1} new files)")
            
            # Use dm to extract
            details = self.dm.get_file_details_and_extract_content(file_id)
            content = details.get('extracted_text')
            
            if content:
                self.cache[file_id] = {
                    'name': file_info['name'],
                    'label': file_info['label'],
                    'content': content,
                    'mime_type': file_info['mime_type']
                }
            else:
                logging.warning(f"No content extracted for {file_info['name']}")
                self.cache[file_id] = {
                    'name': file_info['name'],
                    'label': file_info['label'],
                    'content': "",
                    'mime_type': file_info['mime_type']
                }
            
            count += 1
            if count % 10 == 0:
                self.save_cache()
        
        self.save_cache()

    def train_model(self):
        data = []
        labels = []
        
        for file_id, info in self.cache.items():
            content = info.get('content')
            label = info.get('label')
            if content and label and len(content.strip()) > 0:
                data.append(content)
                labels.append(label)
        
        if not data:
            logging.error("No training data available.")
            return

        logging.info(f"Training on {len(data)} samples.")
        
        # Vectorization
        vectorizer = TfidfVectorizer(max_features=5000, stop_words='english')
        X = vectorizer.fit_transform(data)
        y = labels
        
        # Split
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # Model
        model = LogisticRegression(max_iter=1000)
        model.fit(X_train, y_train)
        
        # Evaluate
        y_pred = model.predict(X_test)
        report = classification_report(y_test, y_pred)
        logging.info("Classification Report:\n" + report)
        print("Classification Report:\n" + report)
        
        # Save
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        models_dir = os.path.join(current_dir, "models")
        os.makedirs(models_dir, exist_ok=True)
        
        model_path = os.path.join(models_dir, f"linear_regression_{timestamp}.sav")
        vectorizer_path = os.path.join(models_dir, f"linear_reg_vectorizer_{timestamp}.sav")
        
        with open(model_path, 'wb') as f:
            pickle.dump(model, f)
        
        with open(vectorizer_path, 'wb') as f:
            pickle.dump(vectorizer, f)
            
        logging.info(f"Model saved to {model_path}")
        logging.info(f"Vectorizer saved to {vectorizer_path}")

if __name__ == "__main__":
    # Assuming config is in ../config/ relative to this script
    config_dir = os.path.join(parent_dir, 'config')
    
    trainer = DriveModelTrainer(
        credentials_path=os.path.join(config_dir, 'google_credentials.json'),
        token_path=os.path.join(config_dir, 'google_token.json')
    )
    trainer.collect_data()
    trainer.train_model()
