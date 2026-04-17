#! /opt/anaconda3/bin/python
# coding: utf-8

import sys
# adding the root path to sys.path to get all modules installed via pip
with open('/etc/paths', 'r') as outfile:
    paths_to_add = outfile.read().split('\n')
sys.path += paths_to_add

# adding my Generic modules
import os

# Finding Google Drive path
# for drive in os.listdir('/Volumes'):
#     if 'google' in drive.lower():
#         google_drive_path = '/Volumes/' + drive

# os.path.expanduser("~")
google_drive_path = os.path.expanduser("~")+'/Library/CloudStorage/GoogleDrive-sebastien.mailleux@gmail.com'
cut_path = len(google_drive_path+'/My Drive/')

sys.path.append(google_drive_path + '/My Drive/Python/Generic_modules')

# trying to resolve bug for poppler
poppler_latest = os.listdir('/usr/local/Cellar/poppler')
poppler_latest.sort(reverse=True) #get latest version
poppler_path = '/usr/local/Cellar/poppler/'+poppler_latest[0]+'/bin'
sys.path.append(poppler_path)


# sys.path.append('/Users/seb/Google Drive/Python/Generic_modules')
import Pushover as Pover
import Gmail_SMTP

# adding other modules
import PyPDF2
import pytesseract
tesseract_latest = os.listdir('/usr/local/Cellar/tesseract')
tesseract_latest.sort(reverse=True) #get latest version
pytesseract.pytesseract.tesseract_cmd = '/usr/local/Cellar/tesseract/'+tesseract_latest[0]+'/bin/tesseract' #solvin for tesseract not in path
from PIL import Image
from pdf2image import convert_from_path
import re
import datetime
import dateparser
import pickle
import calendar
import json
import psutil
from copy import copy
import pprint
import shelve
import openpyxl
import time
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
from abc import ABCMeta
import logging
import shutil


# __________ BASIC FUNCTIONS ____________


def load_config(config_file):
    # import a Json file
    ConfigFile = r'{}'.format(config_file)
    with open(ConfigFile, "r") as read_file:
        data = json.load(read_file)
        return data


def get_pdfs_paths_in_folders_list(directories_list: list):
    """ Return the list of PDF files in a folder
    :param directory: path of the folder to look in
    :return pdfFiles: a list of file names
    """

    pdfPaths = []
    for d in directories_list:
        for filename in os.listdir(d):
            if filename.lower().endswith('.pdf'):
                pdfPaths.append(os.path.join(d, filename))
        pdfPaths.sort(key=str.lower)
    return pdfPaths


def add_months(source_date, months):
    # add months to a date
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def kill_excel():
    for p in psutil.process_iter():
        if 'excel' in p.name().lower():
            p.kill()


def open_health_excel():
    os.system("open /Applications/Microsoft\ Excel.app " + excel_health_path.replace(' ', '\ '))


def send_insurance_forms_by_email():
    """
    Sending insurances forms per email
    Sorting them to the final folder
    Writing in xl
    """

    # get all files in the to_send_folder
    to_send = get_pdfs_paths_in_folders_list([folder_with_emails_to_send_to_health_insurance])

    # create a list per insurer in a dict
    pdfs_paths_to_send_by_email = {}
    pdf_list = []

    for path in to_send:
        pdf = PdfFile.initiate(path, 1)
        pdfs_paths_to_send_by_email.setdefault(pdf.insurer, [])
        pdfs_paths_to_send_by_email[pdf.insurer].append(pdf.path)
        pdf_list.append(pdf)

    # send the emails
    if pdfs_paths_to_send_by_email != {}:

        print("Pdfs_to_send_by_email:")
        logging.info("Pdfs_to_send_by_email:")
        pprint.pprint(pdfs_paths_to_send_by_email)
        logging.info(pdfs_paths_to_send_by_email)
        print('\n')

        for insurer in pdfs_paths_to_send_by_email.keys():
            Gmail_SMTP.send_email(gpwd,
                                  insurance_emails_configs[insurer]['from'],
                                  insurance_emails_configs[insurer]['to'],
                                  insurance_emails_configs[insurer]['cc'],
                                  insurance_emails_configs[insurer]['subject'],
                                  insurance_emails_configs[insurer]['body'],
                                  pdfs_paths_to_send_by_email[insurer])

            print(
                'Email sent to {} with {} attachment(s).\n'.format(insurer, len(pdfs_paths_to_send_by_email[insurer])))
            logging.info(
                'Email sent to {} with {} attachment(s).\n'.format(insurer, len(pdfs_paths_to_send_by_email[insurer])))

    else:
        print('Nothing to send\n')
        logging.info('Nothing to send\n')
    # move the files to their final location & store in xl

    if pdf_list != []:
        for pdf in pdf_list:
            pdf.write_in_excel_file()
            pdf.move_and_rename_to_target()


def ios_notify(title, text):
    os.system("""
              osascript -e 'display notification "{}" with title "{}"'
              """.format(text, title))


def horizontal_line():
    # Get the width of the terminal window
    terminal_width = shutil.get_terminal_size().columns

    # Generate a horizontal line
    horizontal_line = '-' * terminal_width

    # Print the horizontal line
    print(horizontal_line)

# __________ CONFIG ____________


# config files and json

def load_all_config():
    global configs_list, users_config, folders_config,insurance_emails_configs
    configs_list = load_config('./Config/config_pdf.json')
    users_config = load_config('./Config/config_users.json')
    folders_config = load_config('./Config/config_folders.json')
    insurance_emails_configs = load_config('./Config/config_health_insurance_emails.json')


def get_latest_file(folder, root, extension):
    # get all the files in the folder
    list_all_files = [i for i in os.listdir(os.path.join(folder)) if root in i]
    list_dates = [i[len(root):-4] for i in list_all_files]
    latest_file = root + max(list_dates) + extension
    print(f'latest {root} file in {folder} : {latest_file}')
    return latest_file

load_all_config()
pdf_pwd_list = ['C034C50', '10028', '10075','']  # leave '' for wrongly identified files...

# paths used in the scrip
path_to_monitor_for_new_pdfs = [google_drive_path + folders_config['directories_to_parse'][i]
                                for i in range(len(folders_config['directories_to_parse']))]
temp_folder_path = google_drive_path + folders_config['temp_directory']
folder_with_emails_to_send_to_health_insurance = google_drive_path + folders_config['to_send_to_health_insurance']
folder_for_non_valid_health_receipts = google_drive_path + folders_config['not_valid_health_pdf']
to_sort_folders = google_drive_path + folders_config['to_sort']
excel_health_path = os.path.expanduser("~") + folders_config['excel_health_claims'] #not in the Google Drive volume

# watchdogs
files_types_to_monitor = ["*.pdf", "*.PDF"]

# gmail pwd
shelfFile = shelve.open(google_drive_path + folders_config['pwd_directory'] + '/gpwd')
gpwd = shelfFile['gpwd']
shelfFile.close()

# OCR settings
DPI_for_OCR = 250
nbr_pages_to_scan = 4

# Machine learning tagging
fldModels = './Models' # folder containing Models and names of the root files
rootRegression = 'linear_regression_'
rootVectorizer = 'linear_reg_vectorizer_'
extensionModels = '.sav'
model = pickle.load(
    open(fldModels + '/' + get_latest_file(fldModels,rootRegression,extensionModels), 'rb'))
vectorizer = pickle.load(
    open(fldModels + '/' + get_latest_file(fldModels,rootVectorizer,extensionModels), 'rb'))


# __________ CLASSES ____________



class PdfFile_generic():

    def __init__(self, path, max_pages=None):
        self.path = path
        self.max_pages_to_get_text_from = max_pages

        self.extension = os.path.splitext(os.path.basename(path))[1].lower()
        assert self.extension.lower() == '.pdf'
        self.path = path
        self.directory = os.path.dirname(path)
        self.filename = os.path.splitext(os.path.basename(path))[0]
        self.is_valid = False  # initiate
        self.type = None

        # check if a file is encrypted and get password if necessary
        self.number_pages, self.is_encrypted, self.password = self.get_number_of_pages_and_encryption()

        # only do the following if a password is found
        if self.password != 'Password not found.':

            self.text = self.get_text_from_OCR(self.number_pages if max_pages == None else max_pages)
            self.AI_tag = self.get_ML_tag()
            self.config, self.config_name = self.get_config()

            # only do the following if a config is found
            if self.config != None:
                self.type = self.config['type']
                self.date = self.get_date()
                self.target_filename = self.get_target_filename()
                self.target_folder = google_drive_path + self.get_target_folder()

                # only flag as valid if there is a date
                if self.date != None:
                    self.is_valid = True
        print('\n')

    def get_number_of_pages_and_encryption(self):
        pdfFileObj = open(self.path, 'rb')
        pdfReader = PyPDF2.PdfFileReader(pdfFileObj)
        password = 'no password'

        if pdfReader.isEncrypted == True:
            for i in pdf_pwd_list:
                if pdfReader.decrypt(i) == 1:
                    password = i
                    nb = pdfReader.numPages
                    break
                else:
                    password = 'Password not found.'

        else:
            nb = pdfReader.numPages

        if password == 'Password not found.':
            nb = 0
            print('Password not found.')

        return nb, pdfReader.isEncrypted, password

    def get_text_from_OCR(self, max_pages):

        '''
            Part #1 : Converting PDF_Automation to images
        '''

        # Store all the pages of the PDF_Automation in a variable
        if not self.is_encrypted:
            pages = convert_from_path(self.path, DPI_for_OCR, poppler_path =poppler_path)
        else:
            pages = convert_from_path(self.path, DPI_for_OCR, userpw=self.password,poppler_path =poppler_path)

        # Counter to store images of each page of PDF_Automation to image
        image_counter = 1

        # Iterate through all the pages stored above
        print('\nExtracting text: Scanning {} pages'.format(max_pages))
        for page in pages[:max_pages]:
            # Declaring filename for each page of PDF_Automation as JPG
            # For each page, filename will be:
            # PDF_Automation page 1 -> page_1.jpg
            # ....
            # PDF_Automation page n -> page_n.jpg
            filename = temp_folder_path + '/page_' + str(image_counter) + ".jpg"

            # Save the image of the page in system
            page.save(filename, 'JPEG')

            # Increment the counter to update filename
            image_counter = image_counter + 1

        ''' 
        Part #2 - Recognizing text from the images using OCR 
        '''

        # Variable to get count of total number of pages
        filelimit = image_counter - 1

        # Create the output string
        pdfText = ''

        # Iterate from 1 to total number of pages
        for i in range(1, filelimit + 1):
            # Set filename to recognize text from
            # Again, these files will be:
            # page_1.jpg
            # page_2.jpg
            # ....
            # page_n.jpg
            filename = temp_folder_path + "/page_" + str(i) + ".jpg"

            # Recognize the text as string in image using pytesserct
            pageText = str(((pytesseract.image_to_string(Image.open(filename)))))

            # The recognized text is stored in variable text
            # Any string processing may be applied on text
            # Here, basic formatting has been done:
            # In many PDFs, at line ending, if a word can't
            # be written fully, a 'hyphen' is added.
            # The rest of the word is written in the next line
            # Eg: This is a sample text this word here GeeksF-
            # orGeeks is half on first line, remaining on next.
            # To remove this, we replace every '-\n' to ''.
            pageText = pageText.replace('-\n', '')
            pdfText = pdfText + pageText

        return pdfText

    def get_config(self):
        # load config file. Check keywords are in text.
        for key in configs_list.keys():

            config = configs_list[key]

            # initiate at True and assign false as soon a keyword is not in the text
            check_all_keywords = True

            for keyword in config['keywords']:
                if keyword.lower() not in self.text.lower():
                    check_all_keywords = False
                    break

            if check_all_keywords:
                print('Assigned config "{}" for {}.'.format(key, self.path))
                logging.info('Assigned config "{}" for {}.'.format(key, self.path))
                return config, key

        print('No config found for {}.'.format(self.path[cut_path:]))
        logging.info('No config found for {}.'.format(self.path[cut_path:]))
        return None, None

    def get_date(self):
        # Parse the pdf to get the date of the visit
        date = None
        for i in range(len(self.config['regex_date'])):
            dateRegex = re.compile(self.config['regex_date'][i]['regex_string'])
            mo = dateRegex.findall(self.text)

            if mo is not None:
                for k in range(len(mo)):
                    # extract the matches into a string
                    de = mo[k]
                    date_extract = de.replace('ler','1er') #issue with Bred
                    date_extract = de.replace('aodt', 'aout') #issue with releves BNPP
                    date_extract = de.replace('aott', 'aout')  # issue with releves BNPP
                    try:
                        #                         date = datetime.datetime.strptime(date_extract, self.config['regex_date'][i]['extract_format'])
                        if 'extract_format' in self.config['regex_date'][i].keys():
                            date = dateparser.parse(date_extract,
                                                    date_formats=[self.config['regex_date'][i]['extract_format']])
                            print('Used the extract format for the date parsing.')
                            logging.info('Used the extract format for the date parsing.')
                        else:
                            date = dateparser.parse(date_extract)
                    except:
                        pass
                    if date is not None:
                        break

            # exit the for loop if found a match
            if date is not None:
                break
            else:
                continue
        # print('Assigned date : {}'.format(date))
        logging.info('Assigned date : {}'.format(date))
        return date

    def __str__(self):
        if self.password == 'Password not found.':
            output = """PDF Object
            File path : {}
            PASSWORD NOT FOUND
            """.format(self.path[cut_path:])
        else:
            output = """PDF Object
            File path : {}
            Is valid : {}
            Type : {}
            Class : {}
            AI tag : {}
            Config name : {}
            Assigned date : {}
            Target filename : {}
            Target folder : {}
            """.format(self.path,
                       self.is_valid,
                       self.type if self.config != None else 'not defined',
                       self.__class__,
                       self.AI_tag,
                       self.config_name if self.config != None else 'not defined',
                       self.date if self.config != None else 'not defined',
                       self.target_filename if self.config != None else 'not defined',
                       self.target_folder if self.config != None else 'not defined')

        return output

    def __repr__(self):
        return "PDF object _ {}".format(self.path[cut_path:])

    def get_target_folder(self):

        if (self.config['target_folder_add_year'] is True) and (self.date is not None):

            if 'month_shift' in self.config.keys():
                shifted_date = add_months(self.date, self.config['month_shift'])
            else:
                shifted_date = self.date

            return self.config['target_folder'] + '/' + str(shifted_date.year)
        else:
            return self.config['target_folder']

    def get_target_filename(self):
        # define the target name

        if self.config['filename_datetype'] == 'quarter' and self.date != None:
            if 'month_shift' in self.config.keys():
                shifted_date = add_months(self.date, self.config['month_shift'])
            else:
                shifted_date = self.date

            quarter = (shifted_date.month - 1) // 3 + 1
            return self.config['filename_base'] + ' - ' + str(shifted_date.year) + ' Q' + str(quarter)

        elif self.config['filename_datetype'] == 'year' and self.date != None:
            if 'month_shift' in self.config.keys():
                return self.config['filename_base'] + ' - ' + add_months(self.date,
                                                                         self.config['month_shift']).strftime('%Y')
            else:
                return self.config['filename_base'] + ' - ' + self.date.strftime('%Y')

        elif self.config['filename_datetype'] == 'month' and self.date != None:
            if 'month_shift' in self.config.keys():
                return self.config['filename_base'] + ' - ' + add_months(self.date,
                                                                         self.config['month_shift']).strftime('%Y %m')
            else:
                return self.config['filename_base'] + ' - ' + self.date.strftime('%Y %m')

        elif self.config['filename_datetype'] == 'day' and self.date != None:
            return self.config['filename_base'] + ' - ' + self.date.strftime('%Y %m %d')

        else:
            return self.config['filename_base']

    def move_or_rename(self, new_path):
        """
        Amend the path, can be used for moving or renaming
        """

        # create folder if doesn't exist
        if not os.path.isdir(os.path.dirname(new_path)):
            os.makedirs(os.path.dirname(new_path))

        # check if a similar path already exist
        k = 1
        target_name = os.path.splitext(os.path.basename(new_path))[0]

        while os.path.exists(new_path):
            print('A file named {} already exist.'.format(os.path.basename(new_path)))
            logging.info('A file named {} already exist.'.format(os.path.basename(new_path)))
            new_path = os.path.dirname(new_path) + '/' + target_name + ' - ' + str(k) + \
                       os.path.splitext(os.path.basename(new_path))[1]
            k = k + 1

        # rename the file
        # facing  [Errno 18] Cross-device link - use shutil.move instead
        # os.rename(self.path, new_path)
        shutil.move(self.path, new_path)

        # redefine the variables that have changed
        self.path = new_path
        self.filename = os.path.splitext(os.path.basename(new_path))[0]
        self.directory = os.path.dirname(new_path)

        print('Moved and/or renamed to {}.\n'.format(self.path[cut_path:]))
        logging.info('Moved and/or renamed to {}.\n'.format(self.path[cut_path:]))
        Pover.pushover_send('PDF Management', 'Moved and/or renamed to {}.'.format(self.path[cut_path:]))
        ios_notify('PDF Management - Moved', 'Moved and/or renamed to {}.'.format(self.path[cut_path:]))

    def rename_to_target_filename(self):

        if self.config != None and self.is_valid:
            new_path = self.directory + '/' + self.target_filename + self.extension
            if new_path != self.path:
                self.move_or_rename(new_path)
            else:
                print('Already named with the target filename.')
                logging.info('Already named with the target filename.')
        else:
            print('No config assigned.\n')
            logging.info('No config assigned.\n')

    def move_and_rename_to_target(self):

        if self.config != None and self.is_valid:
            new_path = self.target_folder + '/' + self.target_filename + self.extension
            self.move_or_rename(new_path)
        else:
            print('No config assigned.\n')
            logging.info('No config assigned.\n')

    def rename_to_append_tag(self):

        new_path = self.directory + '/' + self.AI_tag + ' - ' + self.filename + self.extension
        self.move_or_rename(new_path)

    def append_tag_and_move_to_sort_folder(self):

        # 2021 03 07 -> decided to remove the tag in the file name
        # new_path = to_sort_folders + '/' + self.AI_tag + '/' + self.AI_tag + ' - ' + self.filename + self.extension
        new_path = to_sort_folders + '/' + self.AI_tag + '/' + self.filename + self.extension
        # if not os.path.exists(to_sort_folders + '/' + self.AI_tag ):
        #     os.makedirs(to_sort_folders + '/' + self.AI_tag )
        self.move_or_rename(new_path)

    def get_ML_tag(self):
        model_input = vectorizer.transform([self.text])
        return model.predict(model_input)[0]

    def test_config(self, config):
        for i in configs_list[config]['keywords']:
            if i.lower() in self.text.lower():
                print('"{}" in the text'.format(i))
            else:
                print('"{}" not in the text'.format(i))

            # In[15]:

    def handle_and_sort(self):

        if self.type == None:
            self.append_tag_and_move_to_sort_folder()

        # handling standard pdf
        if self.type == 'standard':
            if self.is_valid:
                self.move_and_rename_to_target()
            else:
                self.append_tag_and_move_to_sort_folder()

        # handling health pdf
        if self.type == 'health':
            if self.is_valid_health:
                self.rename_and_move_to_emailtosend_folder()
                # pdf.write_in_excel_file() # done when sending emails
                # open_health_excel()
            else:
                self.move_to_nonvalid_folder()





# __________ MAIN ____________


if __name__ == "__main__":

    # import watchdog.version
    #
    # print(watchdog.version.__version__)
    # print(watchdog.version.__spec__)

    # __________ WATCHDOG ____________
    # http://thepythoncorner.com/dev/how-to-create-a-watchdog-in-python-to-look-for-filesystem-changes/

    # Event handler
    patterns = files_types_to_monitor
    ignore_patterns = ""
    ignore_directories = True
    case_sensitive = True
    my_event_handler = PatternMatchingEventHandler(patterns, ignore_patterns, ignore_directories, case_sensitive)
