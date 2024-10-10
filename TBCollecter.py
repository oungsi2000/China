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
import threading
import pymongo
import imgkit
import tempfile
import multiprocessing
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import concurrent.futures
import subprocess

class _Collecter:
    def __init__(self):
        self.공백 =['']

        self.pagelink = []
        self.page_amount_start= []
        self.page_amount_finish = []
        self.prohibit_filer_keywords = []
        self.already_done = []
        self.word_pairs = {}
        
        self.client = pymongo.MongoClient('mongodb+srv://twobasestore:djawnstlr@twobasestore.znc2ay2.mongodb.net/')
        self.db = self.client['twobasestore']

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
    def zero (self, number:int) -> int:
        return int((number // 10)*10)

    def data_loader(self, file_name):
        print('수집 링크를 불러옵니다')
        df = pd.read_excel(file_name)
        for i in df['PageLink'].loc[df['수집여부']== 'Completed']:
            self.pagelink.append(i)

        for i in df['PageAmount_START'].loc[df['수집여부']== 'Completed']:
            self.page_amount_start.append(i)
        for i in df['PageAmount_FINISH'].loc[df['수집여부']== 'Completed']:
            self.page_amount_finish.append(i)
        print('불러오기가 완료되었습니다')

    def prohibit_word_loader(self, prohibit_filter_name):
        print('단어를 불러옵니다')
        df = pd.read_excel(prohibit_filter_name)
        for i in df['단어']:
            self.prohibit_filer_keywords.append(i)
        
        self.prohibit_filer_keywords = set([str(j) for j in self.prohibit_filer_keywords])
        self.prohibit_filer_keywords = list(self.prohibit_filer_keywords)
            
        print('단어 불러오기가 완료되었습니다')

    def rewrite_restart_point(self, file_name, where_to_ended, index_of_link, manager):
        with manager:
            print('페이지 작성')
            df = pd.read_excel(file_name)
            df.loc[index_of_link, 'PageAmount_START'] = where_to_ended
            df.to_excel(file_name, index=False)
            print('페이지 작성 완료')

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

            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/Users/jung-yongjun/Desktop/china/alien-hour-386816-2123060270ca.json'
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

class TBCollecter(_Collecter):
    def __init__(self, upload_account, margin_rate=1.3, extra_cost=12000):
        super().__init__()
        self.공백 = ['']
        #html형식으로 입력
        self.up_image = 'https://i.ibb.co/MSj54nK/AEup.png'
        self.down_image = 'https://i.ibb.co/8Mw2Gwq/AEdown.png'

        self.margin_rate = margin_rate
        self.extra_cost = extra_cost
        self.upload_account = upload_account

        self.load_file_name = '수집목록.xlsx'
        prohibit_links_file_name = 'LinkCollector/수집제한목록.json'
        prohibit_word_file_name = '금지단어.xlsx'
        word_pair_file_name = '제외단어.xlsx'

        self.data_loader(self.load_file_name)
        self.prohibit_word_loader(prohibit_word_file_name)
        self.replace_word_loader(word_pair_file_name)

        self.prohibit_links = self.load_prohibit_links(prohibit_links_file_name)
        self.driver_path = '/Users/jung-yongjun/Desktop/china/chromedriver-mac-arm64/chromedriver'
    
    def refine(self, dataframe, manager):
        try:
            local_time = time.localtime()
            formatted_local_time = time.strftime("%Y-%m-%d %H:%M:%S", local_time)   

            if dataframe['request'] == 'failed':
                print('수집에 실패했습니다 ' + ': ' + dataframe['data'])
                with manager:
                    self.failed_task += 1

            elif dataframe['request'] == 'success':

                text_content = dataframe['data']['product_name'] + dataframe['data']['detail'] + dataframe['data']['opt_title'] + str(dataframe['data']['opt_values'])
                matched_keywords = [keyword for keyword in self.prohibit_filer_keywords if keyword.lower() in text_content.lower()]
                matched_keywords = ','.join(matched_keywords)

                is_prohibit_word = any(keyword.lower() in text_content.lower() for keyword in self.prohibit_filer_keywords)

                if is_prohibit_word:
                    print(f'금지단어가 발견되었습니다 : {matched_keywords}' )
                    self.prohibit_task += 1
                    return
                
                id = dataframe['data']['link'].split('id=')[1].split('&')[0]
                product_real_url = f'https://item.taobao.com/item.htm?&id={id}'

                productname = self.title_keyword1 +' '+ self.title_keyword2 + ' '+ self.replace_word(dataframe['data']['product_name'], self.word_pairs)+' '+ self.title_keyword3
                normal_price = self.zero(int(int(float(dataframe['data']['product_price']))*self.margin_rate + self.extra_cost))
                normal_price = str(normal_price)

                option_prices = []
                for opt_price in dataframe['data']['opt_prices']:
                    p = self.zero(int(int(float(opt_price))*self.margin_rate + self.extra_cost))
                    np = int(normal_price)
                    option_prices.append(str(p - np))

                option_images = dataframe['data']['opt_imgs']
                opt_imgs = list(set(dataframe['data']['opt_imgs']))
                option_values = dataframe['data']['opt_values']
                product_info = dataframe['data']['product_info']

                custom_html = subprocess.run(['python3', 'OptionCreator.py', '-l', json.dumps(opt_imgs), json.dumps(option_values), json.dumps(product_info)], capture_output=True, text=True)
                product_images = dataframe['data']['product_images']

                detail_contents = dataframe['data']['detail']
                option_name = dataframe['data']['opt_title']

                with manager:
                    with open('tracking.png', "rb") as image_file:
                        encoded_string = base64.b64encode(image_file.read()).decode()
                
                for _ in range(5):
                    tracker_url = self.module.get_url(encoded_string)
                    if tracker_url != None:
                        break

                if tracker_url == None:
                    raise OSError('트래커 업로드 실패')

                detail = f'''
                        <div style=\"text-align:center;\">
                            <img src=\"{tracker_url}\" border=\"0\">
                            <img src=\"{self.up_image}\" border=\"0\" width=\"860\">
                            {custom_html}
                            {detail_contents}
                            <img src=\"{self.down_image}\" border=\"0\" width=\"860\">
                        </div>
                        '''
                data = {
                    '카테고리' : {
                        '네이버' : self.category_Naver, #str
                        '옥션' : self.category_AC, #str
                        '지마켓' : self.category_GMKT, #str
                        '11번가' : self.category_11st, #str
                        '쿠팡' : self.category_Coupang #str
                        },
                    '브랜드' : '', #str
                    '상품링크' : product_real_url, #str
                    '상품명' : productname, #str
                    '수집가격' : normal_price, #str
                    '상품이미지': product_images[1], #array
                    '상품상세' : detail,
                    '옵션명' : option_name, #str / name1(str)-name2(str)
                    '옵션 가격' : option_prices, #array / value1(str)-value2(str)
                    '옵션 항목' : option_values, #array / value1(str)-value2(str)
                    '옵션 이미지' : option_images, #array / str
                    '업로드 사업자' : self.upload_account #str
                }

                n = self.generate_code(12)
                product_manage_code = f'AE_{n}'
                
                data['고유상품코드'] = product_manage_code

                # self.db['pd_data'].insert_one(data)
                # self.db['done_list'].insert_one({'DONE' : link})

                print(f'수집 완료 되었습니다 : {formatted_local_time}')
                with manager:
                    self.succeed_task +=1
        except Exception as e:
            print('수집에 실패했습니다 : ' + str(e))
            self.failed_task +=1

        finally:
            with manager:
                total_task = self.succeed_task + self.failed_task + self.prohibit_task
                print(f'전체 : {total_task}, 성공 : {self.succeed_task}, 실패 : {self.failed_task}, 금지 : {self.prohibit_task}')

    def run(self, linkcount, manager, **kwargs):

        #셀레니움 웹드라이버 호출
        import TBMBcore
        pool = TBMBcore.WebDriverPool()
        p1 = TBMBcore.Processor(pool)

        self.module = _AdditionalModules()
        self.options = Options()
        # self.options.add_argument('--headless')
        self.options.add_argument("--disable-blink-features=AutomationControlled")
     
        self.driver = webdriver.Chrome(service=Service(executable_path=self.driver_path), options=self.options)

        self.cookies = kwargs.get('cookies')
        self.total_task = kwargs.get('total_task')
        self.succeed_task = kwargs.get('succeed_task')
        self.failed_task = kwargs.get('failed_task')
        self.prohibit_task = kwargs.get('prohibit_task')

        self.driver.get(self.pagelink[linkcount])
        self.driver.add_cookie(self.cookies)
        self.driver.get(self.pagelink[linkcount])

        self.driver.execute_script('window.scrollTo(0, document.body.scrollHeight)')
        self.driver.implicitly_wait(10)

        #링크 될떄까지 계속 수집
        #제목 앞 키워드
        with manager:
            title = pd.read_excel(self.load_file_name).fillna('')
            self.title_keyword1 = title['TitleKeyword1'].loc[linkcount]
            self.title_keyword2 = title['TitleKeyword2'].loc[linkcount]
            self.title_keyword3 = title['TitleKeyword3'].loc[linkcount]
            
            start_point = self.page_amount_start[linkcount]
            end_point = self.page_amount_finish[linkcount]+1

            self.category_Naver = str(title['category_Naver'].loc[linkcount])
            self.category_AC = str(title['category_AC'].loc[linkcount])
            self.category_GMKT = str(title['category_GMKT'].loc[linkcount])
            self.category_11st = str(title['category_11st'].loc[linkcount])
            self.category_Coupang = str(title['category_Coupang'].loc[linkcount])

            #카테고리코드를 수집하면 될 듯 함

        #사이트 내 검색 후 해당 링크 get 요청 
        for PageA in range(start_point, end_point):
            
            pageSelector = self.driver.find_element(By.CSS_SELECTOR, '#root > div > div:nth-child(3) > div.PageContent--contentWrap--mep7AEm > div.LeftLay--leftWrap--xBQipVc > div.LeftLay--leftContent--AMmPNfB > div.Pagination--pgWrap--kfPsaVv > div > div > span.next-input.next-medium.next-pagination-jump-input > input')
            pageSelector.send_keys(PageA)
            pageSelector.send_keys(Keys.ENTER)
            div = self.driver.find_elements(By.CSS_SELECTOR, '#root > div > div:nth-child(3) > div.PageContent--contentWrap--mep7AEm > div.LeftLay--leftWrap--xBQipVc > div.LeftLay--leftContent--AMmPNfB > div.Content--content--sgSCZ12 > div > div')
            while len(div) == 0:
                div = self.driver.find_elements(By.CSS_SELECTOR, '#root > div > div:nth-child(3) > div.PageContent--contentWrap--mep7AEm > div.LeftLay--leftWrap--xBQipVc > div.LeftLay--leftContent--AMmPNfB > div.Content--content--sgSCZ12 > div > div')

            tb_links = []

            for inner_div in div:
                raw_link = inner_div.find_element(By.CSS_SELECTOR, 'a').get_attribute('href')
                id = raw_link.split('id=')[1].split('&')[0]
                link = f'https://m.intl.taobao.com/detail/detail.html?abbucket=6&id={id}&ns=1&spm=a21n57.1.0.0.75c4523crIEqr7'
                tb_links.append(link)

            print(f'총 {len(tb_links)} 개의 타오바오 코드를 수집했습니다')
   
            #수집된 링크에서 정보 수집 (멀티스레딩)
            for link in tb_links:
                is_already_done = self.db['done_list'].find_one({'DONE' : link}) != None
                is_prohibit_link = link in self.prohibit_links 

                if is_already_done:
                    print('이미 수집된 링크입니다')
                    self.failed_task += 1
                
                elif is_prohibit_link:
                    print('수집이 제한된 링크입니다')
                    self.prohibit_task += 1

                else:
                    dataframe = p1.collect(link)
                    time.sleep(random.randint(10,40)/10)
                    self.refine(dataframe, manager)
                                
            #한 페이지가 끝날 때마다 재작성  
            self.rewrite_restart_point('수집목록.xlsx', PageA, linkcount, manager)

def collect(linkcount, account, lock, **kwargs):
    TBCollecter(account).run(linkcount, lock, **kwargs)

class RunMultiProcess(TBCollecter):
    def __init__(self, account, max_workers=4):
        super().__init__(account)
        self.max_workers = max_workers
        self.account = account
        self.cookies = {'name' : 'sgcookie', 'domain' : '.taobao.com', 'value' : 'E100O5vUIn3RPwXUXYZc3DNTfmv0toZls2RoiuFfR2gIhxlkbqd/MINPlrCPyIutI18jwhkigfjDmNO9JzZmg9ZujF4/JJmMO20X24Ry5f7NANM='}

    def run_multiprocess(self):
        manager = multiprocessing.Manager()
        lock = manager.Lock()
        
        pool = multiprocessing.Pool(processes=self.max_workers)
        processes = []

        #전역 프로세스 변수
        total_task = multiprocessing.Value('i', 0).value
        succeed_task = multiprocessing.Value('i', 0).value
        failed_task = multiprocessing.Value('i', 0).value
        prohibit_task = multiprocessing.Value('i', 0).value
 
        for linkcount in range(len(self.pagelink)):
            process = pool.apply_async(collect, args=(linkcount, self.account, lock), 
                kwds={
                    'cookies' : self.cookies,
                    'total_task' : total_task,
                    'succeed_task' : succeed_task,
                    'failed_task' : failed_task,
                    'prohibit_task' : prohibit_task,
                    })
            processes.append(process)

        for process in processes:
            try:
                process.get()
            except:
                traceback.print_exc()

if __name__ == '__main__':
    logging.basicConfig(filename=f'datas/logging/TBCollecter.log', level=logging.INFO, force=True)
    
    #타오바오 콜렉터는 1개의 워커로 작동하는 것을 추천합니다
    RunMultiProcess('투베이스6', max_workers=1).run_multiprocess()
         

##일단 수집목록.xlsx 요거 + 카테고리 수집 코드 추가 + 추가이미지?