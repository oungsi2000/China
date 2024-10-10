import pandas as pd
import random
import string
import json
import time
import re
import logging
import os
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from msrest.authentication import CognitiveServicesCredentials
from PIL import Image
import traceback
import requests
import base64
from io import BytesIO
import rembg
import io
from google.cloud import storage
import uuid
import pymongo
import imgkit
import tempfile

class _Collector:
    def __init__(self):
        self.공백 =['']

        self.pagelink = []
        self.page_amount_start= []
        self.page_amount_finish = []
        self.prohibit_filer_keywords = []
        self.already_done = []
        self.word_pairs = {}
        
        self.client = pymongo.MongoClient('mongodb+srv://twobasestore:9GssjMAUHiWraHsF@twobasestore.5bmmzbq.mongodb.net/')
        self.db = self.client['twobasestore']

    def print(self, msg):
        print(msg)

    #고유상품코드 등록 함수
    def generate_code(self, length):
        characters = string.ascii_letters + string.digits
        
        while True:
            random_string = ''.join(random.choice(characters) for _ in range(length))
            code1 = self.db['pd_data'].find_one({'고유상품코드' : random_string})
            code2 = self.db['complete_data'].find_one({'고유상품코드' : random_string})

            if code1 == None and code2==None:
                return random_string

    #가격 끝자리 0으로 변경
    def zero (self, number) -> int:
        return int((number // 10)*10)

    def data_loader(self, file_name):
        self.print('수집 링크를 불러옵니다')
        df = pd.read_excel(file_name)
        for i in df['PageLink'].loc[df['수집여부']== 'Completed']:
            self.pagelink.append(i)

        for i in df['PageAmount_START'].loc[df['수집여부']== 'Completed']:
            self.page_amount_start.append(i)
        for i in df['PageAmount_FINISH'].loc[df['수집여부']== 'Completed']:
            self.page_amount_finish.append(i)
        self.print('불러오기가 완료되었습니다')

    def prohibit_word_loader(self, prohibit_filter_name):
        self.print('단어를 불러옵니다')
        df = pd.read_excel(prohibit_filter_name)
        for i in df['단어']:
            self.prohibit_filer_keywords.append(i)
        
        self.prohibit_filer_keywords = set([str(j) for j in self.prohibit_filer_keywords])
        self.prohibit_filer_keywords = list(self.prohibit_filer_keywords)
            
        self.print('단어 불러오기가 완료되었습니다')

    def rewrite_restart_point(self, file_name, where_to_ended, index_of_link, manager):
        with manager:
            self.print('페이지 작성')
            df = pd.read_excel(file_name)
            df.loc[index_of_link, 'PageAmount_START'] = where_to_ended
            df.to_excel(file_name, index=False)
            self.print('페이지 작성 완료')

    def replace_brackets(self, product_name):
        bracket_pattern = r'\[[^\]]*\]'
        product_name = re.sub(bracket_pattern, "", product_name)
        bracket_pattern = r'\★[^\★]*\)'
        product_name = re.sub(bracket_pattern, "", product_name)
        product_name = product_name.strip()
        return product_name

    def replace_word_loader(self, word_pairs_file):
        df_word_pairs = pd.read_excel(word_pairs_file)

        for index, row in df_word_pairs.iterrows():
            self.word_pairs[row['단어1']] = row['단어2']
            if pd.isna(row['단어2']):
                self.word_pairs[row['단어1']] = ""
            else:
                self.word_pairs[row['단어1']] = row['단어2']
        
    def replace_word(self, text, word_pairs):

        word_pairs_lower = {str(k).lower(): v for k, v in word_pairs.items()}
        pattern = re.compile("|".join(map(re.escape, word_pairs_lower.keys())), re.IGNORECASE)

        def replace_match(match):
            return word_pairs_lower[match.group(0).lower()]
        
        return pattern.sub(replace_match, text)

    def load_prohibit_links(self, file_name):
        with open(file_name, 'r', encoding='utf-8') as file:
            prohibit_links = json.load(file)
        return prohibit_links
        

class _AdditionalModules():
    def __init__(self) -> None:
        pass

    class _ImageEditer():
        def __init__(self):
            pass

        def get_image_base64(self, input_image_url):
            try:
                get_image_path = requests.get(input_image_url, stream=True)
                get_image_path.raise_for_status()

                image_data = get_image_path.content
                image_base64 = base64.b64encode(image_data).decode("utf-8")
                
                return image_base64
            except Exception as e:
                logging.error(e)
                image_base64 = None

            return image_base64

        def image_segmentation(self, input_image_path, background_image_path):

            try:
                input_data = base64.b64decode(input_image_path)
                output_data = rembg.remove(input_data)

                transparent_image = Image.open(BytesIO(output_data)).convert('RGBA').resize((1000,1000))
                background = Image.open(background_image_path).convert('RGBA')

                # 배경 이미지를 원래 이미지 크기로 조정
                resized_background = background.resize(transparent_image.size, Image.LANCZOS)
                combined_image = Image.alpha_composite(resized_background, transparent_image)
                combined_image = combined_image.convert("RGBA")

                output_buffer = BytesIO()
                combined_image.save(output_buffer, format="PNG", optimize=True)
                no_bg_img = base64.b64encode(output_buffer.getvalue()).decode("utf-8")
                output_buffer.close()

            except Exception as e:
                traceback.print_exc()
                logging.error(e)
                no_bg_img = None

            return no_bg_img

        def insult_watermark(self, no_bg_img, watermark_image):
            try:
            #워터마크 삽입
                img_data = base64.b64decode(no_bg_img)
                img_buffer = BytesIO(img_data)

                no_bg_image = Image.open(img_buffer)
                watermark = Image.open(watermark_image)

                x_position = 0
                y_position = no_bg_image.height - watermark.height
                
                # 원본 이미지와 워터마크 이미지 합성
                merged_image = no_bg_image.copy()
                merged_image.paste(watermark, (x_position, y_position), watermark)
                
                image_bytes = io.BytesIO()
                merged_image.save(image_bytes,format="PNG")
                image_bytes.seek(0)

                encoded_image = base64.b64encode(image_bytes.read())

            except Exception as e:
                traceback.print_exc()
                encoded_image = None

            return encoded_image
        
    def get_url(self, base64_img, is_pdimg=False):
        try:
            unique_id = str(uuid.uuid4()).replace('-','')

            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/Users/jung-yongjun/Desktop/china/datas/alien-hour-386816-2123060270ca.json'
            storage_client = storage.Client()

            bucket = storage_client.bucket('twobasestore')
            blob = bucket.blob(unique_id)
            image_data = base64.b64decode(base64_img)

            if is_pdimg:
                with tempfile.NamedTemporaryFile(delete=True, suffix='.jpg') as file:
                    file.write(image_data)
                    blob = bucket.blob('pd/'+unique_id + '.jpg')
                    blob.upload_from_filename(file.name, timeout=120)

                    blob.content_type = 'image/jpeg'
                    blob.update()
            
            else:
                blob.upload_from_string(image_data, timeout=120)
            
            return blob.public_url
        except:
            return None
        
    def get_path(self, base64_img):
        try:
            if not os.path.exists('datas/raw_img/'):
                os.makedirs('datas/raw_img/')

            unique_id = str(uuid.uuid4()).replace('-','')
            path = f'datas/raw_img/{unique_id}.png'
            data = base64.b64decode(base64_img)
            with open(path, 'wb') as file:
                file.write(data)
            return path
        except:
            return None

    def html_to_b64img(self, html):
        with tempfile.NamedTemporaryFile(suffix=".jpeg", delete=True) as temp_output:
            options = {
                'encoding': "UTF-8",
                'format': 'jpeg',
                'quality' : 75,
                'quiet' : '',
                'log-level' : 'error',
                "enable-local-file-access": ""
            }
            #html -> jpeg

            for count in range(3):
                try:
                    imgkit.from_string(html, temp_output.name, options=options)
                    break
                except:
                    if count == 2:
                        raise OSError('이미지 생성 실패')

            with open(temp_output.name, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode()

            return encoded_string

    def decode_base64(self, img, process_idx):

        decoded_image = base64.b64decode(img)

        # 이미지 데이터를 바이트 형식으로 변환
        image_bytes = io.BytesIO(decoded_image)

        # 이미지 데이터를 로드하고 PIL 이미지 개체로 변환
        image = Image.open(image_bytes)

        # 이미지를 파일로 저장 (PNG 형식)
        image.save(f"{process_idx}.png")

    def detect_person(self, image_url):
        try:
            # Set API key and endpoint.
            subscription_key = "94d344201f9b495491fbb47b0e2e68ba"
            endpoint = "https://twobasestore.cognitiveservices.azure.com/"

            # Create an instance of the Computer Vision client.
            computervision_client = ComputerVisionClient(endpoint, CognitiveServicesCredentials(subscription_key))

            # Analyze the image.
            detect_objects_results = computervision_client.detect_objects(image_url)
            # Print the results.azure.cognitiveservices.vision.computervision import

            result = []

            for object in detect_objects_results.objects:
                result.append(object.object_property)
                
        except Exception as e:
            logging.error(e)
            result = []

        return result