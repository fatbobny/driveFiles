from basicfunctions import extract_json_content, add_months
import logging
from googleDriveAPI import GoogleDriveFileManager
import re
import dateparser #pip install dateparser

class pdf_or_image_file():

    def __init__(self,file_details:dict,pdf_configs:list,drive_manager:GoogleDriveFileManager,ml_model, ml_vectorizer):
        self.pdf_configs = pdf_configs
        self.drive_manager = drive_manager
        self.ml_model = ml_model
        self.ml_vectorizer = ml_vectorizer
        self.error = ''
        for keys in file_details:
            setattr(self,keys,file_details[keys])
        self.path = self.drive_manager.get_path_from_id(self.file_id)
        logging.info('')
        logging.info(f'Initiating file for {self.path}')
        self.config, self.config_name = self.get_config()
        if self.config:
            self.date = self.get_date() # if there is a config, need date to set target folder
        else:
            self.machine_learning_tag = self.get_ml_tag() # if there is no config, need ML tag to set target folder
        self.target_folder_path, self.target_folder_id =  self.get_target_folder_path_and_create_if_needed() #need to initiate last as needs Dates or ML tag
        self.target_filename = self.get_target_filename()

        logging.info(f'Successfully initiated file for {self.path} - Error: {self.error}')
        logging.info('')

    def __repr__(self):
        output = f"pdf_file object\n"
        for attr_name, attr_value in vars(self).items():
            output += f"   {attr_name}: {attr_value}\n"
        return output

    def get_config(self):
        # load config file. Check keywords are in text.
        if self.extracted_text:

            for key in self.pdf_configs.keys():

                config = self.pdf_configs[key]

                # initiate at True and assign false as soon a keyword is not in the text
                check_all_keywords = True

                for keyword in config['keywords']:
                    if keyword.lower() not in self.extracted_text.lower():
                        check_all_keywords = False
                        break

                if check_all_keywords:
                    logging.info(f'Assigned config "{key}" for {self.file_name}')
                    logging.info(f'Config: {config}')
                    return config, key

            logging.info(f'No config found for {self.file_name}')
            return None, None

    def get_date(self):
        # Parse the pdf to get the date of the visit
        date = None
        for i in range(len(self.config['regex_date'])):
            dateRegex = re.compile(self.config['regex_date'][i]['regex_string'])
            mo = dateRegex.findall(self.extracted_text)

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

    def get_target_filename(self):
        # define the target name
        if self.config:
            if self.config['filename_datetype'] == 'quarter' and self.date != None:
                if 'month_shift' in self.config.keys():
                    shifted_date = add_months(self.date, self.config['month_shift'])
                else:
                    shifted_date = self.date

                quarter = (shifted_date.month - 1) // 3 + 1
                target_filename = self.config['filename_base'] + ' - ' + str(shifted_date.year) + ' Q' + str(quarter)

            elif self.config['filename_datetype'] == 'year' and self.date != None:
                if 'month_shift' in self.config.keys():
                    target_filename = self.config['filename_base'] + ' - ' + add_months(self.date,
                                                                             self.config['month_shift']).strftime('%Y')
                else:
                    target_filename = self.config['filename_base'] + ' - ' + self.date.strftime('%Y')

            elif self.config['filename_datetype'] == 'month' and self.date != None:
                if 'month_shift' in self.config.keys():
                    target_filename = self.config['filename_base'] + ' - ' + add_months(self.date,
                                                                             self.config['month_shift']).strftime('%Y %m')
                else:
                    target_filename = self.config['filename_base'] + ' - ' + self.date.strftime('%Y %m')

            elif self.config['filename_datetype'] == 'day' and self.date != None:
                target_filename = self.config['filename_base'] + ' - ' + self.date.strftime('%Y %m %d')

            else:
                target_filename = self.config['filename_base']

        else :
            target_filename = self.file_name

        logging.info(f'Target filename: {target_filename}')

        return target_filename

    def get_target_folder_path_and_create_if_needed(self):

        if self.config:
            if (self.config['target_folder_add_year'] is True) and (self.date is not None):

                if 'month_shift' in self.config.keys():
                    shifted_date = add_months(self.date, self.config['month_shift'])
                else:
                    shifted_date = self.date

                target_folder_path = self.config['target_folder'] + '/' + str(shifted_date.year)
            else:
                target_folder_path =  self.config['target_folder']
        else:
            target_folder_path = f"Downloads/A_To Sort/{self.machine_learning_tag}"

        logging.info(f'Target folder: {target_folder_path}')
        self.drive_manager.create_folder_by_path(target_folder_path)
        target_folder_id = self.drive_manager.find_folder_id_by_path(target_folder_path)
        return target_folder_path, target_folder_id

    def get_ml_tag(self):
        model_input = self.ml_vectorizer.transform([self.extracted_text])
        ml_tag = self.ml_model.predict(model_input)[0]
        logging.info(f'ML tag: {ml_tag}')
        return ml_tag


    def rename_and_sort(self):
        self.drive_manager.rename_file(self.file_id, self.target_filename)
        self.drive_manager.move_file(self.file_id, self.target_folder_id)



if __name__ == '__main__':
    pdf_configs = extract_json_content('../../config/config_pdf.json')
    print(pdf_configs)