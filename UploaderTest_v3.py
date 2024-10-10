import time
import json
import os
import concurrent.futures
from PIL import Image as IMG
from io import BytesIO
import requests
import time
import sys
import jwt
import traceback
import logging
import tempfile
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from urllib.parse import quote
import threading
import pymongo
import warnings
import hmac
import hashlib
import urllib.parse
import pandas as pd
from datetime import datetime
from selenium.webdriver.chrome.service import Service
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import re
import brotli
import argparse
from tkinter import *
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from Exceptions import *
import signal
import queue
import uuid
from google.cloud import storage
import google.api_core.exceptions
import io


lock = threading.Lock()

#DB연결
client = pymongo.MongoClient('mongodb+srv://twobasestore:9GssjMAUHiWraHsF@twobasestore.5bmmzbq.mongodb.net/')
db = client['twobasestore']

#완료된 전체 작업 개수 (공유 리소스)
completed_task = 0

class GUI:
    def __init__(self, account) -> None:
        self.tk = Tk()
        self.tk.title(account + ' 상품 업로드 진행상황')
        self.text_queue = queue.Queue()
        self.is_done_queue = queue.Queue()

        frame1 = ttk.Frame(self.tk)
        frame1.pack(side='left')

        frame2 = ttk.Frame(self.tk)
        frame2.pack()

        self.label_text1 = StringVar()
        self.label_text1.set("전체 : 0")
        self.label1 = Label(frame1, textvariable=self.label_text1)
        self.label1.pack(padx=12, pady=6)

        self.label_text2 = StringVar()
        self.label_text2.set("완료 : 0")
        self.label2 = Label(frame1, textvariable=self.label_text2)
        self.label2.pack(padx=12, pady=6)

        self.label_text3 = StringVar()
        self.label_text3.set("진행률 : -%")
        self.label3 = Label(frame1, textvariable=self.label_text3)
        self.label3.pack(padx=12, pady=6)

        self.console = ScrolledText(frame2, height=14, width=60)
        self.console.pack()

        self.tk.bind('<<update_count>>', self.update_count)
        self.tk.bind('<<update_console>>', self.update_console)

        self.tk.protocol('WM_DELETE_WINDOW', self.exit)
        self.check_is_all_done()

    def check_is_all_done(self):
        if self.is_done_queue.qsize() == max_workers:
            self.update_console_subthread('상품 등록이 모두 완료되었습니다 !')
        else:
            self.tk.after(100, self.check_is_all_done)
        
    def exit(self):
        os.kill(os.getpid(), signal.SIGTERM)
    
    def update_count(self, e):
        self.label_text1.set('전체 : ' + str(self.all_task))
        self.label_text2.set('완료 : ' + str(self.completed_task))
        self.label_text3.set('진행률 : ' + str(self.progress_value)+'%')
    
    def update_console(self, e):
        text = self.text_queue.get()
        self.console.insert('1.0', text+'\n')

    def update_count_subthread(self, all_task, completed_task, progress_value):
        self.all_task = all_task
        self.completed_task= completed_task
        self.progress_value = progress_value
        self.tk.event_generate("<<update_count>>", when="tail")

    def update_console_subthread(self, text):
        self.text_queue.put(text)
        self.tk.event_generate('<<update_console>>', when='tail')


class Uploader:
    def __init__(self, gui, business_acount, chunk=1000):

        #나중에 입력을 받을 때에는 json파일로 따로 만들면 될 듯 (사용자 정보 입력)
        with open('datas/Auth/Accounts.json', 'r', encoding='utf-8') as file:
            self.market_acount = json.load(file) 

        self.business_acount = business_acount
        self.upload_acount = self.market_acount[business_acount]
        self.chunk = chunk
        self.ctgr_df = pd.read_excel('datas/11st_newctgy.xlsx', sheet_name='개편맵')
        self.do_ESM = True
        self.gui = gui

        #이닛에서는 각 마켓 계정 정보, api 정보, 업로드할 데이터를 불러오자, 그리고 업로드를 할 때마다 클래스를 재지정 하는거임, 
        #셀레니움으로 업로드 시 한 번만 정의하고 링크만 번갈이끼기

    def refine_category_11st(self, old_category) -> int:
        try:
            d = self.ctgr_df.loc[self.ctgr_df['구소카번호'] == old_category, '변경사항']
            if d.values.__len__() == 0:
                d = self.ctgr_df.loc[self.ctgr_df['구세카번호'] == old_category, '변경사항']
            
            if '삭제' in str(d.values.tolist()[0]):
                try:
                    m = self.ctgr_df.loc[d.index.tolist(), '구중카번호'].values[0]
                    try:
                        new_category = int(self.ctgr_df.loc[(self.ctgr_df['구중카번호'] == m) & (self.ctgr_df['변경사항'].str.contains('세카 생성')), '번호'].values[0])
                    except:
                        new_category = int(self.ctgr_df.loc[(self.ctgr_df['구중카번호'] == m) & (self.ctgr_df['변경사항'].str.contains('소카 생성')), '번호'].values[0])
                except:
                    m = self.ctgr_df.loc[d.index.tolist(), '구대카번호'].values[0]
                    try:
                        new_category = int(self.ctgr_df.loc[(self.ctgr_df['구대카번호'] == m) & (self.ctgr_df['변경사항'].str.contains('세카 생성')), '번호'].values[0])
                    except:
                        new_category = int(self.ctgr_df.loc[(self.ctgr_df['구대카번호'] == m) & (self.ctgr_df['변경사항'].str.contains('소카 생성')), '번호'].values[0])
                return new_category
            else:
                return old_category
        except:
            traceback.print_exc()
            return old_category 
    
    def cut_name_by_byte(self, pd_name):
        pd_name = pd_name.encode('utf-8')
        cut_name = pd_name[:100]
        
        tries = 100
        while True:
            try:
                cut_name = cut_name[:tries]
                cut_name = cut_name.decode('utf-8')
                return cut_name
            except UnicodeDecodeError:
                tries -= 1
                pass
    
    def upload_naver(self, upload_index, up_data, cookies_naver):
        try:
            with lock:
                with open('datas/settings_Naver/payload_naver.json', 'r', encoding='utf-8') as file:
                    payload = json.load(file)
                with open(f'datas/settings_Naver/settings_{self.business_acount}', 'r', encoding='utf-8') as file:
                    settings = json.load(file)
            
            
            payload.update(settings['simpleAccountInfo'])
            payload['product']['deliveryInfo'] = settings['deliveryInfo']
            payload['product']['detailAttribute']['productInfoProvidedNotice'] = settings['productInfoProvidedNotice']
            payload['product']['accountNo'] = settings['accountNo']
            payload['product']['detailAttribute']['afterServiceInfo'] = settings['afterServiceInfo']
            payload['singleChannelProductMap']['STOREFARM']['channelNo'] = settings['defaultChannelNo']

            headers = {
                'Content-Type' : 'application/json;charset=UTF-8',
            }
            data = brotli.decompress(up_data[upload_index]['상품상세']).decode()
            res = requests.post('https://sell.smartstore.naver.com/api/v2/editor/convert?editorType=NONE', headers=headers, data=data.encode('utf-8'), cookies=cookies_naver)
            detail = {
                'json' : json.dumps(res.json()),
                'documentId' : ""
            }
            detail = json.dumps(detail)

            #이미지를 따로 업로드 해야 한다면 따로 업로드
            payload['product']['images'] = []
            images =[up_data[upload_index]['상품이미지']] + up_data[upload_index]['추가이미지']
            for idx, image in enumerate(images[:9]):
                with tempfile.TemporaryDirectory(suffix='.png') as temp_dir:
                    try:
                        filename = temp_dir + '/dataimg.png'
                        res = requests.get(image)
                        io = BytesIO(res.content)
                        img = IMG.open(io)
                        img.save(filename)
                        
                        headers = {
                            'Referer' : 'https://sell.smartstore.naver.com/'
                        }
                        with open(filename, 'rb') as f:
                            files = {'file': (filename, f, 'image/png')}
                            res = requests.post('https://sell.smartstore.naver.com/api/file/photoinfra/uploads?acceptedPatterns=image%2Fjpeg,image%2Fgif,image%2Fpng,image%2Fbmp', cookies=cookies_naver, headers=headers, files=files)

                        if idx == 0:
                            payload['product']['images'].append({
                            "imageType": "REPRESENTATIVE",
                            "order": idx+1,
                            "imageUrl": res.json()[0]['imageUrl'],
                            "width": res.json()[0]['width'],
                            "height": res.json()[0]['height'],
                            "fileSize": res.json()[0]['fileSize']
                                })
                        else:
                            payload['product']['images'].append({
                            "imageType": "OPTIONAL",
                            "order": idx,
                            "imageUrl": res.json()[0]['imageUrl'],
                            "width": res.json()[0]['width'],
                            "height": res.json()[0]['height'],
                            "fileSize": res.json()[0]['fileSize']
                                })
                    except:
                        pass


            payload['product']['detailAttribute']['sellerCodeInfo']['sellerManagementCode'] = up_data[upload_index]['고유상품코드']
            payload['product']['customerBenefit']['immediateDiscountPolicy']['discountMethod']['value'] = up_data[upload_index]['수집가격'] #판매자할인 50%
            payload['product']['customerBenefit']['immediateDiscountPolicy']['mobileDiscountMethod']['value'] = up_data[upload_index]['수집가격']

            payload['product']['category']['id'] = up_data[upload_index]['카테고리']['네이버']
            payload['product']['name'] = up_data[upload_index]['상품명'][:99]
            payload['product']['salePrice'] = int(up_data[upload_index]['수집가격'])*2
            payload['product']['detailContent']['productDetailInfoContent'] = detail

            payload['product']['stockQuantity'] = 9999

            #옵션
            if up_data[upload_index]['옵션명'] != '':
                payload['product']['detailAttribute']['optionInfo'] = {
                    "optionUsable": True,
                    "options" : [],
                    "optionCombinations" : [],
                    "optionStandards" : [],
                    "optionDeliveryAttributes" : [],
                    "useStockManagement" : True
                }

                option_names = up_data[upload_index]['옵션명'].split('-')
                for option_name in option_names:
                    payload['product']['detailAttribute']['optionInfo']['options'].append({
                        "groupName":option_name[:24],
                        "usable":True,
                        "optionType":"COMBINATION",
                        "sortType":"CREATE"
                    })
                option_values = up_data[upload_index]['옵션 항목']
                option_prices = up_data[upload_index]['옵션 가격']
                수집가격 = int(up_data[upload_index]['수집가격'])

                for option_value, option_price in zip(option_values, option_prices):
                    if int(float(option_price)) + 수집가격 < 수집가격*1.5 and int(float(option_price)) + 수집가격 > 수집가격*0.5:
                        parsed_opt_values = option_value.split('-')

                        if len(parsed_opt_values) == 1:
                            payload['product']['detailAttribute']['optionInfo']['optionCombinations'].append({
                                "price":option_price,
                                "stockQuantity":"500",
                                "usable":True,
                                "optionType":"COMBINATION",
                                "sortType":"CREATE",
                                "optionName1":parsed_opt_values[0][:24],
                            })
                        elif len(parsed_opt_values) == 2:
                            payload['product']['detailAttribute']['optionInfo']['optionCombinations'].append({
                                "price":option_price,
                                "stockQuantity":"500",
                                "usable":True,
                                "optionType":"COMBINATION",
                                "sortType":"CREATE",
                                "optionName1":parsed_opt_values[0][:24],
                                "optionName2":parsed_opt_values[1][:24]
                            })

                    payload['product']['stockQuantity'] = 500*len(payload['product']['detailAttribute']['optionInfo']['optionCombinations'])
            headers = {
                'Content-Type' : 'application/json;charset=UTF-8'
            }
            res = requests.post('https://sell.smartstore.naver.com/api/products', data=json.dumps(payload), cookies=cookies_naver, headers=headers)
            try:
                product_num_naver = res.json()['singleChannelProductMap']['STOREFARM']['id']
                self.gui.update_console_subthread('네이버 상품등록 완료 : ' + str(product_num_naver))
                return product_num_naver
            except:
                raise OSError(res.text)
            
        except Exception as e:
            self.gui.update_console_subthread('네이버 상품등록 실패 : ' + str(e))
            logging.exception(up_data[upload_index]['고유상품코드'] + ' : ' +str(e))
            return None

    def login_naver(self):
        driver = webdriver.Chrome(service=Service(executable_path='/Users/jung-yongjun/Desktop/china/chromedriver-mac-arm64/chromedriver'))
        driver.get('https://accounts.commerce.naver.com/login?url=https%3A%2F%2Fsell.smartstore.naver.com%2F%23%2Flogin-callback%3FreturnUrl%3Dhttps%253A%252F%252Fsell.smartstore.naver.com%252F%2523%252Fhome%252Fdashboard')
        driver.implicitly_wait(5)

        naver_id = self.upload_acount['네이버']['ID']
        naver_pw = self.upload_acount['네이버']['PW']

        driver.find_element(By.CSS_SELECTOR, '#root > div > div.Layout_wrap__3uDBh > div > div > div.Login_login_area__cMnCU.Login_type__nM7Ia > div.Login_login_content__Ia6Rm > div > ul.Login_login_list__3IVTB > li:nth-child(1) > input').send_keys(naver_id)
        driver.find_element(By.CSS_SELECTOR, '#root > div > div.Layout_wrap__3uDBh > div > div > div.Login_login_area__cMnCU.Login_type__nM7Ia > div.Login_login_content__Ia6Rm > div > ul.Login_login_list__3IVTB > li:nth-child(2) > input').send_keys(naver_pw)

        WebDriverWait(driver, 200).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#_gnb_nav"))
        )
        
        time.sleep(1)
        cookies = driver.get_cookies()
        cookies_dict = {}

        for cookie in cookies:
            cookies_dict[cookie['name']] = cookie['value']

        with open(f'datas/Auth/NAVER_AUTH_{self.business_acount}.json', 'w', encoding='utf-8') as file:
            json.dump(cookies_dict, file, ensure_ascii=False, indent=4)

        driver.quit()
        
        res = requests.get('https://sell.smartstore.naver.com/api/products?_action=create', cookies=cookies_dict)
        data = res.json()
        data['product']['deliveryInfo']['claimDeliveryInfo']['returnDeliveryCompany'] = {
            "id": 2428050
        }

        settings = {
            'accountNo' : data['product']['accountNo'],
            'productInfoProvidedNotice' : data['product']['detailAttribute']['productInfoProvidedNotice'],
            'simpleAccountInfo' : data['simpleAccountInfo'],
            'deliveryInfo' : data['product']['deliveryInfo'],
            'afterServiceInfo' : data['product']['detailAttribute']['afterServiceInfo'],
            'defaultChannelNo' : data['simpleAccountInfo']['defaultChannelNo']
        }

        with open(f'datas/settings_Naver/settings_{self.business_acount}', 'w', encoding='utf-8') as file:
            json.dump(settings, file, ensure_ascii=False, indent=4)

        return cookies_dict

        
    def login_ESM(self):        
        try :
            try:
                with open(f'datas/Auth/ESM_AUTH_{self.business_acount}.json', 'r', encoding='utf-8') as file:
                    cookies_dict = json.load(file)
      
                decoded_token = jwt.decode('.'.join(cookies_dict['ESM_TOKEN'].split('.')[:3]), algorithms='HS512', options={"verify_signature": False})
                exp = decoded_token['iat']
                expiration_date = datetime.fromtimestamp(exp) + timedelta(hours=2)

                if datetime.utcnow() + timedelta(hours=9) > expiration_date:
                    cookies_dict = self.refresh_token_by_request()

            except:
                cookies_dict = self.refresh_token_by_request()

            with open('datas/settings_ESM/headers_ESM.json', 'rb') as file:
                header = json.load(file)

            self.ACid = self.upload_acount['옥션']['ID']
            self.GMKTid = self.upload_acount['지마켓']['ID']

            data1 = {'siteId' : 1, 'sellerId' : self.ACid, 'categoryCode' : '28681000'}
            data1 = json.dumps(data1)

            data2 = {'siteId' : 2, 'sellerId' : self.GMKTid, 'categoryCode' : '100000014200002344300021153'}
            data2 = json.dumps(data1)

            #ShipmentPlaceNo, MembAddrNo, JejuAddDeliveryFee, BackwoodsAddDeliveryFee
            response_GetShipmentPlaces = requests.get('https://www.esmplus.com/SELL/SYI/GetShipmentPlaces', cookies=cookies_dict, data=data1)

            try:
                for i in range(len(response_GetShipmentPlaces.json())):
                    is_default = response_GetShipmentPlaces.json()[i]['DefaultIs']

                    if is_default == True:
                        ShipmentPlaceNo = response_GetShipmentPlaces.json()[i]['ShipmentPlaceNo']

                #DeliveryFeeTemplateNo, 
                data = {'shipmentPlaceNo' : ShipmentPlaceNo}
                data = json.dumps(data)
                response_DeliveryFee = requests.get(f'https://www.esmplus.com/SELL/SYI/GetDefaultDeliveryFeeTemplatesNo?shipmentPlaceNo={ShipmentPlaceNo}', cookies=cookies_dict, headers=header, data=data)

                #IacTransPolicyNo, GmktTransPolicyNo

                response_TransPolicy1 = requests.get(f'https://www.esmplus.com/SELL/SYI/GetTransPolicyList?siteId=1&sellerId={self.ACid}&categoryCode=28681000', cookies=cookies_dict, headers=header, data=data1)
                for element in response_TransPolicy1.json():
                    if element['DefaultIs']:
                        response_TransPolicy1 = element['TransPolicyNo']
                        break

                response_TransPolicy2 = requests.get(f'https://www.esmplus.com/SELL/SYI/GetTransPolicyList?siteId=2&sellerId={self.GMKTid}&categoryCode=100000014200002344300021153', cookies=cookies_dict, headers=header, data=data2)
                for element in response_TransPolicy2.json():
                    if element['DefaultIs']:
                        response_TransPolicy2 = element['TransPolicyNo']
                        break
                
                headers={
                    'Content-Type' : 'application/json, text/plain, */*'
                }
                response_customid = requests.get('https://www.esmplus.com/Member/AntiMoneyLaundering/GetAMLSellerList', headers=headers, cookies=cookies_dict)
                custom_id = json.loads(response_customid.json())[1]['SellerCustNo']

                #LicenseSeq
                data_seq = {'custNo': custom_id}
                data_seq = json.dumps(data_seq)
                response_LicenseSeq = requests.post('https://www.esmplus.com/sell/popup/GetGoodsDealerLicense', cookies=cookies_dict, headers=header, data=data_seq)
                if response_LicenseSeq.text == '':
                    response_LicenseSeq = ''
                else:
                    response_LicenseSeq = [str(response_LicenseSeq.json()[0]['LicenseSeq'])]
            except:
                raise LoginError('ESM 기본 정보 수집에 실패했습니다. 수집 전 기본 셋팅 확인 부탁드립니다')

            ESM_setting = {
                'ShipmentPlaceNo' : str(ShipmentPlaceNo),
                'hdnBundleDeliveryTempNo' : str(response_GetShipmentPlaces.json()[0]['MembAddrNo']),
                'JejuAddDeliveryFee' : int(response_GetShipmentPlaces.json()[0]['JejuAddDeliveryFee']),
                'BackwoodsAddDeliveryFee' : int(response_GetShipmentPlaces.json()[0]['BackwoodsAddDeliveryFee']),
                'ReturnExchangeDeliveryFeeStr' : self.upload_acount['반품배송비'],
                'IacTransPolicyNo' : str(response_TransPolicy1),
                'GmktTransPolicyNo' : str(response_TransPolicy2),
                'DeliveryFeeTemplateNo' : response_DeliveryFee.text,
                'LicenseSeqGMKT' : response_LicenseSeq

            }

            with open(f'datas/settings_ESM/settings_{self.business_acount}.json', 'w', encoding='utf-8') as file:
                json.dump(ESM_setting, file, ensure_ascii=False, indent=4)

            return cookies_dict
        
        except :
            self.gui.update_console_subthread('로그인 실패 재시작 해주세요')
            traceback.print_exc()
            sys.exit()
            
    def refresh_token_ESM(self):
        try:
            driver = webdriver.Chrome(service=Service(executable_path='/Users/jung-yongjun/Desktop/china/chromedriver-mac-arm64/chromedriver'))
            driver.get('https://www.esmplus.com/Home/Home#HTDM395')
            driver.implicitly_wait(5)

            driver.execute_script("document.querySelector('#container > div > div > div.box__content > div > button.button__tab.button__tab--gmarket').click()")
            gmkt_id = self.upload_acount['지마켓']['ID']
            gmkt_pw = self.upload_acount['지마켓']['PW']
            
            driver.find_element(By.CSS_SELECTOR, '#typeMemberInputId01').send_keys(gmkt_id)
            driver.find_element(By.CSS_SELECTOR, '#typeMemberInputPassword01').send_keys(gmkt_pw)

            WebDriverWait(driver, 200).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#header > h1 > a > img"))
            )
            
            time.sleep(1)
            cookies = driver.get_cookies()
            cookies_dict = {}

            for cookie in cookies:
                cookies_dict[cookie['name']] = cookie['value']

            with open(f'datas/Auth/ESM_AUTH_{self.business_acount}.json', 'w', encoding='utf-8') as file:
                json.dump(cookies_dict, file, ensure_ascii=False, indent=4)

            driver.quit()
            
            return cookies_dict
        
        except TimeoutException:
            self.do_ESM = False

        except:
            self.gui.update_console_subthread('시스템 오류')
            sys.exit()
    
    def refresh_token_by_request(self):
        try:
            head = {
                'Content-Type' : 'application/json',
                'Referer' : 'https://signin.esmplus.com/login',
                'Cookie' : 'ESM_PC=pcid=ODMwMjUyOTgzNjY1MjgzOTU4OQ; '
            }
            data = {
                "atoCollectData":{
                    "data" : '',
                    "duration":278,
                    "resultCode":"success",
                    "resultMessage":"",
                    "uuidKey":"5b3637eb39184e59b92d5b31d98fe81c"
                    },
                "captchaRequest":{
                    "input":"",
                    "sessionID":"",
                    "token":""
                },
                "loginId":self.upload_acount['지마켓']['ID'],
                "nextUrl":"",
                "password":self.upload_acount['지마켓']['PW'],
                "rememberMe":False,
                "siteType":"GMARKET",
                "captcha":False
            }
            res = requests.post('https://signin.esmplus.com/api/login', headers=head, data=json.dumps(data), allow_redirects=False)
            token = res.json()['data']['encData']
            cookieValue = res.json()['data']['cookieValue']
            head = {
                'Cookie' : cookieValue,

            }
            res = requests.get(f'https://www.esmplus.com/Member/Authenticate/JwtAuthService?JwtToken={token}&NextUrl=/Member/SignIn/RegisterContacts&ClientIp=172.30.201.6', headers=head, allow_redirects=False)

            esm_token = re.findall(r'ESM_TOKEN=(.*);', res.headers['Set-Cookie'])[0]
            esm_auth = re.findall(r'ESM_AUTH=(.*);', res.headers['Set-Cookie'])[0]

            head = {
                'Cookie' : f'ESM_TOKEN={esm_token}; ESM_AUTH={esm_auth};'
            }

            res = requests.get('https://www.esmplus.com/Member/SignIn/RegisterContacts', headers=head, allow_redirects=False)

            esm_request_auth_pc = re.findall(r'ESM_REQUEST_AUTH_PC=(.*);', res.headers['Set-Cookie'])[0]
            esm_pc = re.findall(r'ESM_PC=(.*);', cookieValue)[0]

            cookies_dict = {
                'ESM_TOKEN' : esm_token,
                'ESM_AUTH' : esm_auth,
                'ESM_REQUEST_AUTH_PC' : esm_request_auth_pc,
                'ESM_PC' : esm_pc
            }

            with open(f'datas/Auth/ESM_AUTH_{self.business_acount}.json', 'w', encoding='utf-8') as file:
                json.dump(cookies_dict, file, ensure_ascii=False, indent=4)

            self.gui.update_console_subthread('로그인 성공')
            return cookies_dict
    
        except:
            self.refresh_token_ESM()

    #판매자 할인, 고객혜택 기능 추가
    def upload_ESM(self, cookies, upload_index, up_data, upload_supplement=False):

        try:
            with open('datas/settings_ESM/payload.json', 'rb') as file:
                json_payload = json.load(file)

            with open('datas/settings_ESM/headers_ESM.json', 'rb') as file:
                json_headers = json.load(file)

            with open(f'datas/settings_ESM/settings_{self.business_acount}.json', 'rb') as file:
                settings = json.load(file)

            current_time = datetime.utcnow()
            end_time = current_time + timedelta(days=90)
            
            if not self.do_ESM:
                self.gui.update_console_subthread('3시간이 지나 ESM 계정이 로그아웃 되었습니다. 로그인 후 재시도 해주세요')
                return None
            
            try:
                with open(f'datas/Auth/ESM_AUTH_{self.business_acount}.json', 'r', encoding='utf-8') as file:
                    cookies_dict = json.load(file)
       

                decoded_token = jwt.decode('.'.join(cookies_dict['ESM_TOKEN'].split('.')[:3]), algorithms='HS512', options={"verify_signature": False})
                exp = decoded_token['iat']
                expiration_date = datetime.fromtimestamp(exp) + timedelta(hours=2)

                if datetime.utcnow() + timedelta(hours=9) > expiration_date:
                    cookies_dict = self.refresh_token_by_request()

            except:
                cookies_dict = self.refresh_token_by_request()

            #브랜드 검색
            brand = up_data[upload_index]['브랜드']
            brand = quote(brand)

            params = {
                'keywordType' : 0,
                'keyword' : brand
            }

            params = json.dumps(params)
            response = requests.get(f'https://www.esmplus.com/Sell/Common/GetSdBrandSearchResult?keywordType=0&keyword={brand}', headers=json_headers, data=params, cookies=cookies_dict)

            if len(response.json()['BrandMakerListT']) == 1:
                makerid = response.json()['BrandMakerListT'][0]['MakerSeq']
                brandid = response.json()['BrandMakerListT'][0]['BrandSeq']

                json_payload['model']['SdInfo']['SdMakerId'] = makerid
                json_payload['model']['SdInfo']['SdBrandId'] = brandid

            #지옥션 계정 설정
            json_payload['model']['SYIStep1']['SiteSellerId'][0]['value'] = self.upload_acount['옥션']['ID']
            json_payload['model']['SYIStep1']['SiteSellerId'][1]['value'] = self.upload_acount['지마켓']['ID']

            #상품명 입력, 100바이트 미만으로 자르기
            cut_name = self.cut_name_by_byte(up_data[upload_index]['상품명'])

            json_payload['model']['SYIStep1']['GoodsName']['GoodsName'] = cut_name
            json_payload['model']['SYIStep1']['GoodsName']['GoodsNameSearch'] = cut_name

            #카테고리 입력
            json_payload['model']['SYIStep1']['SiteCategoryCode'][0]['value'] = up_data[upload_index]['카테고리']['옥션']
            json_payload['model']['SYIStep1']['SiteCategoryCode'][1]['value'] = up_data[upload_index]['카테고리']['지마켓']

            #판매가 입력
            json_payload['model']['SYIStep2']['Price']['GoodsPrice'] = int(up_data[upload_index]['수집가격'])*2
            json_payload['model']['SYIStep2']['Price']['GoodsPriceIAC'] = int(up_data[upload_index]['수집가격'])*2
            json_payload['model']['SYIStep2']['Price']['GoodsPriceGMKT'] = int(up_data[upload_index]['수집가격'])*2

            #판매자할인 입력
            json_payload['model']['SYIStep3']['SellerDiscount']['DiscountAmtIac1'] = up_data[upload_index]['수집가격']
            json_payload['model']['SYIStep3']['SellerDiscount']['DiscountAmtGmkt1'] = up_data[upload_index]['수집가격']
            json_payload['model']['SYIStep3']['SellerDiscount']['DiscountAmt'] = up_data[upload_index]['수집가격']
            json_payload['model']['SYIStep3']['SellerDiscount']['DiscountAmt1'] = up_data[upload_index]['수집가격']
            json_payload['model']['SYIStep3']['SellerDiscount']['DiscountAmtIac'] = up_data[upload_index]['수집가격']
            json_payload['model']['SYIStep3']['SellerDiscount']['DiscountAmtGmkt'] = up_data[upload_index]['수집가격']


            #판매자 고유상품코드 입력
            json_payload['model']['SYIStep2']['ItemCode'] = up_data[upload_index]['고유상품코드']

            #상품상세 입력
            json_payload['model']['SYIStep2']['NewDescription']['Text'] = brotli.decompress(up_data[upload_index]['상품상세']).decode()

            #이미지 설정
            json_payload['model']['SYIStep2']['GoodsImage']['AdditionalImagesSite'] = "3"
            json_payload['model']['SYIStep2']['GoodsImage']['AdditionalImages'] = []

            #추가이미지 입력
            for add_image in up_data[upload_index]['추가이미지']:
                json_payload['model']['SYIStep2']['GoodsImage']['AdditionalImages'].append({
                    "Operation":"1",
                    "Url":add_image,
                    "BigImage":True
                })

            #메인이미지 입력
            for image in ['PrimaryImage', 'ListImage', 'FixedImage', 'ExpandedImage']:
                json_payload['model']['SYIStep2']['GoodsImage'][image] = {
                    "Operation":"1",
                    "Url":up_data[upload_index]['상품이미지'],
                    "BigImage":True
                }

            #기간설정
            json_payload['model']['SYIStep2']['SellingPeriod']['IAC']['StartDate'] = str(current_time.replace(microsecond=0))
            json_payload['model']['SYIStep2']['SellingPeriod']['IAC']['EndDate'] = str(end_time.replace(microsecond=0))

            json_payload['model']['SYIStep2']['SellingPeriod']['GMKT']['StartDate'] = str(current_time.replace(microsecond=0))
            json_payload['model']['SYIStep2']['SellingPeriod']['GMKT']['EndDate'] = str(end_time.replace(microsecond=0))

            #옵션
            if up_data[upload_index]['옵션명'] != '':
                OptionInfoList = []
                수집가격 = int(float(up_data[upload_index]['수집가격']))

                option_names = up_data[upload_index]['옵션명'].split('-')
                if len(option_names) == 1:
                    OptName1 = option_names[0]
                    OptName2 = ""
                elif len(option_names) == 2:
                    OptName1 = option_names[0]
                    OptName2 = option_names[1]

                for item, price in zip(up_data[upload_index]['옵션 항목'], up_data[upload_index]['옵션 가격']):
                    hashed_item = item.split('-')
                    if len(hashed_item) == 1:
                        hashed_item.append("")
                    
                    if int(float(price)) + 수집가격 < 수집가격*1.5 and int(float(price)) + 수집가격 > 수집가격*0.5:
                        opt_data = {
                            "OptType":"2",
                            "OptValue1":hashed_item[0][:25],
                            "RcmdOptValueNo1":"0",
                            "OptName1":OptName1[:25],
                            "RcmdOptNo1":"0",
                            "OptValue2":hashed_item[1][:25],
                            "RcmdOptValueNo2":"0",
                            "OptName2":OptName2[:25],
                            "RcmdOptNo2":"0",
                            "OptValue3":"",
                            "RcmdOptValueNo3":"0",
                            "OptName3":"",
                            "RcmdOptNo3":"0",
                            "SellerStockCode":None,
                            "SkuMatchingVerNo":None,
                            "AddAmnt":int(float(price)),
                            "OptRepImageLevel":"0",
                            "OptRepImageUrl":"",
                            "OptionInfoCalculation":None,
                            "SkuList":None,
                            "SiteOptionInfo":[
                            {
                            "SiteId":"1",
                            "ExposeYn":"Y",
                            "SoldOutYn":"N",
                            "StockQty":None
                            },
                            {
                            "SiteId":"2",
                            "ExposeYn":"Y",
                            "SoldOutYn":"N",
                            "StockQty":None
                            }
                            ],
                            "OptionNameLangList":[
                            {
                            "LangCode":"ENG",
                            "Opt1":"",
                            "Opt2":"",
                            "Opt3":None
                            },
                            {
                            "LangCode":"JPN",
                            "Opt1":"",
                            "Opt2":"",
                            "Opt3":None
                            },
                            {
                            "LangCode":"CHN",
                            "Opt1":"",
                            "Opt2":"",
                            "Opt3":None
                            }],
                            "OptionValueLangList":[
                            {
                            "LangCode":"ENG",
                            "Opt1":"",
                            "Opt2":"",
                            "Opt3":None
                            },
                            {
                            "LangCode":"JPN",
                            "Opt1":"",
                            "Opt2":"",
                            "Opt3":None
                            },
                            {
                            "LangCode":"CHN",
                            "Opt1":"",
                            "Opt2":"",
                            "Opt3":None
                            }]
                        }
                        if opt_data['OptName2'] == '':
                            opt_data['OptType'] = '1'
                        OptionInfoList.append(opt_data)
                
                json_payload['model']['SYIStep2']['OrderOption'] = {
                    "OptType":"2",
                    "StockMngIs":False,
                    "UnifyStockIs":False,
                    "OptionInfoList": OptionInfoList            
                }


            #배송, 반품 템플릿 설정
            json_payload['model']['SYIStep2']['DeliveryInfo']['ShipmentPlaceNo'] = settings['ShipmentPlaceNo']
            json_payload['model']['SYIStep2']['DeliveryInfo']['BundleDeliveryTempNo'] = settings['DeliveryFeeTemplateNo']
            json_payload['model']['SYIStep2']['DeliveryInfo']['ReturnExchangeADDRNo'] = settings['hdnBundleDeliveryTempNo']

            DeliveryFeeTemplateJSON = json_payload['model']['SYIStep2']['DeliveryInfo']['DeliveryFeeTemplateJSON']
            DeliveryFeeTemplateJSON = json.loads(DeliveryFeeTemplateJSON)

            DeliveryFeeTemplateJSON['ShipmentPlaceNo'] = settings['ShipmentPlaceNo']
            DeliveryFeeTemplateJSON['JejuAddDeliveryFee'] = settings['JejuAddDeliveryFee']
            DeliveryFeeTemplateJSON['BackwoodsAddDeliveryFee'] = settings['BackwoodsAddDeliveryFee']

            json_payload['model']['SYIStep2']['DeliveryInfo']['DeliveryFeeTemplateJSON'] = str(json.dumps(DeliveryFeeTemplateJSON))
            json_payload['model']['SYIStep2']['DeliveryInfo']['IacTransPolicyNo'] = settings['IacTransPolicyNo']
            json_payload['model']['SYIStep2']['DeliveryInfo']['GmktTransPolicyNo'] = settings['GmktTransPolicyNo']
            json_payload['model']['SYIStep2']['DeliveryInfo']['ReturnExchangeDeliveryFeeStr'] = settings['ReturnExchangeDeliveryFeeStr']

            #건기식 전용 세팅
            if upload_supplement:
       
                json_payload['model']['SYIStep2']['OfficialNotice'] = {
                    "NoticeItemGroupNo":"22",
                    "NoticeItemCodes":[
                        {
                        "NoticeItemCode":"22-15",
                        "NoticeItemValue":"기본"
                        },
                        {
                        "NoticeItemCode":"22-2",
                        "NoticeItemValue":"iHerb"
                        },
                        {
                        "NoticeItemCode":"22-3",
                        "NoticeItemValue":"상세설명참조"
                        },
                        {
                        "NoticeItemCode":"22-5",
                        "NoticeItemValue":"상세설명참조"
                        },
                        {
                        "NoticeItemCode":"22-6",
                        "NoticeItemValue":"상세설명참조"
                        },
                        {
                        "NoticeItemCode":"22-7",
                        "NoticeItemValue":"상세설명참조"
                        },
                        {
                        "NoticeItemCode":"22-8",
                        "NoticeItemValue":"상세설명참조"
                        },
                        {
                        "NoticeItemCode":"22-9",
                        "NoticeItemValue":"상세설명참조"
                        },
                        {
                        "NoticeItemCode":"22-16",
                        "NoticeItemValue":"상세설명참조"
                        },
                        {
                        "NoticeItemCode":"22-10",
                        "NoticeItemValue":"상세설명참조"
                        },
                        {
                        "NoticeItemCode":"22-12",
                        "NoticeItemValue":"수입식품안전관리 특별법에 따른 수입신고를 필함"
                        },
                        {
                        "NoticeItemCode":"22-13",
                        "NoticeItemValue":"상세설명참조"
                        },
                        {
                        "NoticeItemCode":"22-14",
                        "NoticeItemValue":"주문 후 1주 소요"
                        },
                        {
                        "NoticeItemCode":"999-5",
                        "NoticeItemValue":""
                        }
                    ]
                }

                json_payload['model']['SYIStep2']['CertIAC']['HealthFoodCert'] = {
                    "AdDeliberationNo":"2023-0404237",
                    "IsUse":True,
                    "CertificationOfficeName":"아흐트",
                    "CertificationNo":"2023-0404237",
                    "Operation":"1"
                    }

                json_payload['model']['SYIStep2']['Origin'] = {
                    "ProductType":"4",
                    "Type":"3",
                    "Name":None,
                    "Code":None,
                    "IsMultipleOrigin":False
                    }
            
                json_payload['model']['SYIStep2']['LicenseSeqGMKT'] = settings['LicenseSeqGMKT']

            json_payload = json.dumps(json_payload)
            
            try:
                response = requests.post('https://www.esmplus.com/Sell/SingleGoods/Save', data=json_payload, headers=json_headers, cookies=cookies_dict)
                soup = BeautifulSoup(response.content, 'html.parser')

                AC = soup.select('.ls0')[0].text
                GMKT = soup.select('.ls0')[1].text

                self.gui.update_console_subthread(f'상품등록이 완료되었습니다 : {AC}')
                self.gui.update_console_subthread(f'상품등록이 완료되었습니다 : {GMKT}')
                
                return AC, GMKT
            except:
                try:
                    for element in OptionInfoList:
                        del element['OptionValueLangList']
                        del element['OptionNameLangList']
                    json_payload = json.loads(json_payload)
                    json_payload['model']['SYIStep2']['OrderOption']['OptionInfoList'] = OptionInfoList
                    json_payload = json.dumps(json_payload)

                    response = requests.post('https://www.esmplus.com/Sell/SingleGoods/Save', data=json_payload, headers=json_headers, cookies=cookies_dict)
                    soup = BeautifulSoup(response.content, 'html.parser')

                    AC = soup.select('.ls0')[0].text
                    GMKT = soup.select('.ls0')[1].text

                    self.gui.update_console_subthread(f'상품등록이 완료되었습니다 : {AC}')
                    self.gui.update_console_subthread(f'상품등록이 완료되었습니다 : {GMKT}')
                    
                    return AC, GMKT
                except:
                    self.gui.update_console_subthread(response.text)            
                    return None, None
        except Exception as e:
            self.gui.update_console_subthread(f'상품 등록에 실패했습니다 : {e}')
            return None, None
    
    #건기식 업로드 기능 미구현, 향후 리셀에 집중한다면 추가 예정
    #추후 해외출고지 + 상세페이지 변경 + 판매자 직접할인 관련하여 추후 업데이트 예정 --v3에는 사용불가!
    
    def upload_11st(self, upload_index, up_data, upload_supplement=False):
        try:
            api_key = self.upload_acount['11번가']['api-key']

            headers = {
                'openapikey' : api_key
            }
            old_ctgy = int(up_data[upload_index]['카테고리']['11번가'])
            new_ctgy = str(self.refine_category_11st(old_ctgy))
            cut_name = self.cut_name_by_byte(up_data[upload_index]['상품명'])

            data = f'''<?xml version="1.0" encoding="utf-8" standalone="yes"?>
            <Product>
            <abrdBuyPlace>D</abrdBuyPlace>
            <selMthdCd>01</selMthdCd>
            <dispCtgrNo><![CDATA[1020810]]></dispCtgrNo>
            <prdTypCd>01</prdTypCd>
            <hsCode>000</hsCode>
            <prdNm>{cut_name}</prdNm>
            <brand>{up_data[upload_index]['브랜드']}</brand>
            <rmaterialTypCd>05</rmaterialTypCd>
            <orgnTypCd>03</orgnTypCd>
            <orgnNmVal>상세설명참조</orgnNmVal>
            <orgnCountry>상세설명참조</orgnCountry>
            <beefTraceStat>02</beefTraceStat>
            <sellerPrdCd>{up_data[upload_index]['고유상품코드']}</sellerPrdCd>
            <suplDtyfrPrdClfCd>01</suplDtyfrPrdClfCd>
            <prdStatCd>01</prdStatCd>
            <minorSelCnYn>Y</minorSelCnYn>
            <prdImage01>{up_data[upload_index]['상품이미지']}</prdImage01>
            <prdImage02></prdImage02>
            <prdImage03></prdImage03>
            <prdImage04></prdImage04>
            <htmlDetail><![CDATA[{brotli.decompress(up_data[upload_index]['상품상세']).decode()}]]></htmlDetail>
            <ProductCertGroup>
                <crtfGrpTypCd/>
                <crtfGrpObjClfCd>02</crtfGrpObjClfCd>
                <crtfGrpExptTypCd>02</crtfGrpExptTypCd>
                <ProductCert>
                <certTypeCd>131</certTypeCd>
                <certKey/>
                </ProductCert>
            </ProductCertGroup>
            <selTermUseYn>N</selTermUseYn>
            <selPrc>{up_data[upload_index]['수집가격']}</selPrc>
            <prdSelQty>500</prdSelQty>
            <dlvCnAreaCd>01</dlvCnAreaCd>
            <dlvWyCd>01</dlvWyCd>
            <dlvEtprsCd>00034</dlvEtprsCd>
            <dlvCstInstBasiCd>01</dlvCstInstBasiCd>
            <bndlDlvCnYn>N</bndlDlvCnYn>
            <dlvCstPayTypCd>03</dlvCstPayTypCd>
            <jejuDlvCst>4000</jejuDlvCst>
            <islandDlvCst>8000</islandDlvCst>
            <outsideYnOut>N</outsideYnOut>
            <outsideYnIn>N</outsideYnIn>
            <abrdCnDlvCst>{self.upload_acount['반품배송비']}</abrdCnDlvCst>
            <rtngdDlvCst>{self.upload_acount['반품배송비']}</rtngdDlvCst>
            <exchDlvCst>{str(int(self.upload_acount['반품배송비'])*2)}</exchDlvCst>
            <asDetail>구매대행 제품 특성 상 as가 어렵습니다</asDetail>
            <rtngExchDetail>해외 출고 제품으로 반품 시 15000원의 국제 운송료가 부담됩니다</rtngExchDetail>
            <dlvClf>02</dlvClf>
            <abrdInCd>03</abrdInCd>
            <prdWght>1</prdWght>
            <ntShortNm>중국(CN)</ntShortNm>
            <mbAddrLocation05>02</mbAddrLocation05>
            <mbAddrLocation06>02</mbAddrLocation06>
            <ProductNotification>
                <type>891045</type>
                <item>
                <code>23759100</code>
                <name>상세설명참조</name>
                </item>
                <item>
                <code>23756033</code>
                <name>상세설명참조</name>
                </item>
                <item>
                <code>11905</code>
                <name>상세설명참조</name>
                </item>
                <item>
                <code>23760413</code>
                <name>상세설명참조</name>
                </item>
                <item>
                <code>11800</code>
                <name>상세설명참조</name>
                </item>
                
            </ProductNotification>
            </Product>
            '''

            warnings.filterwarnings("ignore")
            soup_11st = BeautifulSoup(data, 'xml')
            for idx, img in enumerate(up_data[upload_index]['추가이미지'][:3]):
                target = soup_11st.select_one(f'prdImage0{idx+2}')
                target.string = img
            if up_data[upload_index]['브랜드'] == '':
                soup_11st.select_one('brand').string = '&#39;알수없음&#39;'

            if up_data[upload_index]['옵션명'] != '':
                option_name = up_data[upload_index]['옵션명'].split('-')

                option_data = f'''
                <root>
                <optSelectYn>Y</optSelectYn>
                <txtColCnt>1</txtColCnt>
                <optionAllQty>9999</optionAllQty>
                <optionAllAddPrc>0</optionAllAddPrc>
                <prdExposeClfCd>04</prdExposeClfCd>
                <optMixYn>N</optMixYn>
                <optionAllAddWght/>            
                <ProductOptionExt>
                </ProductOptionExt>
                </root>
                '''
                
                soup_option = BeautifulSoup(option_data, 'xml')
                수집가격 = int(float(up_data[upload_index]['수집가격']))
               
                for item, price in zip(up_data[upload_index]['옵션 항목'], up_data[upload_index]['옵션 가격']):
                    if int(float(price)) + 수집가격 < 수집가격*1.5 and int(float(price)) + 수집가격 > 수집가격*0.5:
                        hashed_item = item.split('-')

                        new_opt_1 = soup_option.new_tag('ProductOption')
                        new_price_1 = soup_option.new_tag('colOptPrice')
                        new_price_1.string = str(int(float(price)))
                        new_value_1 = soup_option.new_tag('optionMappingKey')
                        is_use = soup_option.new_tag('useYn')
                        is_use.string = 'Y'

                        if len(option_name) == 1:
                            new_value_1.string = f'{option_name[0]}:{hashed_item[0]}'
                        elif len(option_name) == 2:
                            new_value_1.string = f'{option_name[0]}:{hashed_item[0]}†{option_name[1]}:{hashed_item[1]}'

                        new_opt_1.append(new_price_1)
                        new_opt_1.append(new_value_1)
                        new_opt_1.append(is_use)
                        soup_option.select('ProductOptionExt')[0].append(new_opt_1)

                content = soup_option.select_one('root')
                soup_11st.select_one('Product').append(content)
            
            response = requests.post('http://api.11st.co.kr/rest/prodservices/product', data=str(soup_11st).replace('</root>', '').replace('<root>', '').encode('utf-8'), headers=headers)
            soup_result = BeautifulSoup(response.content, 'xml')
            if soup_result.select_one('resultCode').text == '200':
                pd_num = soup_result.select_one('productNo').text
                self.gui.update_console_subthread(f'상품 등록 완료 : {pd_num}')
                return pd_num
            else:
                self.gui.update_console_subthread(f'상품 등록에 실패했습니다 : {response.text}')
                return None
            
        except Exception as e:
            self.gui.update_console_subthread(f'상품 등록에 실패했습니다 : {e}')
            logging.exception(e)
            return None
               
    #건기식 업로드 기능 미구현, 향후 리셀에 집중한다면 추가 예정
    #수집한 상품이미지 + 상세페이지의 이미지를 구글에 업로드 후 삭제 기능 + 판매자 직접할인 -> 플레이오토의 성능이 좋지 못할 때 구현합니다
    def upload_coupang(self, upload_index, up_data, upload_supplement=False):
        try:
            os.environ['TZ'] = 'GMT+0'

            api_key = self.upload_acount['쿠팡']['api-key']
            secret_key = self.upload_acount['쿠팡']['secret-key']
            vendorId = self.upload_acount['쿠팡']['vendorId']

            #hmac 인증 후 헤더 발급
            def get_header(path, method, query=None):
                datetime=time.strftime('%y%m%d')+'T'+time.strftime('%H%M%S')+'Z'
                if query != None:
                    query = urllib.parse.urlencode(query)
                else:
                    query = ''

                #hmac 인증
                message = datetime+method+path+query

                signature=hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'),hashlib.sha256).hexdigest()
                authorization = "CEA algorithm=HmacSHA256, access-key="+api_key+", signed-date="+datetime+", signature="+signature

                header = {
                    'authorization' : authorization, 
                    'Content-type' : 'application/json;charset=UTF-8'
                    }
                return header
            
            def get_shipping_place():
                path = '/v2/providers/marketplace_openapi/apis/api/v1/vendor/shipping-place/outbound'
                headers = get_header(path, "GET", query={'pageNum':'1', 'pageSize':'10'})
                response = requests.get('https://api-gateway.coupang.com'+ path + '?pageNum=1&pageSize=10', headers=headers)
                return response.json()['content'][0]['outboundShippingPlaceCode']
            
            def get_return_place():
                path = f'/v2/providers/openapi/apis/api/v4/vendors/{vendorId}/returnShippingCenters'
                headers = get_header(path, "GET", query={'pageNum':'1', 'pageSize':'10'})
                response = requests.get('https://api-gateway.coupang.com'+ path + '?pageNum=1&pageSize=10', headers=headers)
                return response.json()['data']['content'][0]

            path = '/v2/providers/seller_api/apis/api/v1/marketplace/seller-products'
            headers = get_header(path, 'POST')

            current_time = datetime.now()
            formatted_time = current_time.strftime("%Y-%m-%dT%H:%M:%S")
            return_info = get_return_place()

            payload = {
                'sellerProductName' : up_data[upload_index]['상품명'],
                'vendorId' : vendorId,
                'saleStartedAt' : str(formatted_time),
                'saleEndedAt' : "2099-01-01T00:00:00",
                'brand' : up_data[upload_index]['브랜드'],
                'deliveryMethod' : 'AGENT_BUY',
                'deliveryCompanyCode' : 'CJGLS',
                'deliveryChargeType' : 'FREE',
                'deliveryCharge' : '0',
                'freeShipOverAmount' : '0',
                'deliveryChargeOnReturn' : self.upload_acount['반품배송비'],
                'remoteAreaDeliverable' : 'Y',
                'unionDeliveryType' : 'NOT_UNION_DELIVERY',

                #출고지, 반품지 입력 ------
                'returnCenterCode' : return_info['returnCenterCode'],
                'returnChargeName' : return_info['shippingPlaceName'],
                'companyContactNumber' : return_info['placeAddresses'][0]['companyContactNumber'],
                'returnZipCode' : return_info['placeAddresses'][0]['returnZipCode'],
                'returnAddress' : return_info['placeAddresses'][0]['returnAddress'],
                'returnAddressDetail' : return_info['placeAddresses'][0]['returnAddressDetail'],
                'returnCharge' : self.upload_acount['반품배송비'],
                'outboundShippingPlaceCode' : get_shipping_place(),
                
                'vendorUserId' : self.upload_acount['쿠팡']['ID'],
                'requested' : True,
                'items' : [
                    {
                        'itemName' : up_data[upload_index]['상품명'],
                        'originalPrice' : up_data[upload_index]['수집가격'],
                        'salePrice' : up_data[upload_index]['수집가격'],
                        'maximumBuyCount' : '9999',
                        'maximumBuyForPerson' : '0',
                        'maximumBuyForPersonPeriod' : '1',
                        'outboundShippingTimeDay' : '3',
                        'unitCount' : '0',
                        'adultOnly' : 'EVERYONE',
                        'taxType' : 'TAX',
                        'parallelImported' : 'NOT_PARALLEL_IMPORTED',
                        'overseasPurchased' : 'OVERSEAS_PURCHASED',
                        'pccNeeded' : True,
                        'externalVendorSku' : up_data[upload_index]['고유상품코드'],
                        'images' : [
                            {
                                'imageOrder' : '0',
                                'imageType' : 'REPRESENTATION',
                                'vendorPath' : up_data[upload_index]['상품이미지']
                            }
                        ],
                        'attributes' : [],
                        'contents' : [
                            {
                                'contentsType' : 'HTML',
                                'contentDetails' : [
                                    {
                                        'content' : brotli.decompress(up_data[upload_index]['상품상세']).decode(),
                                        'detailType' : 'TEXT'
                                    }
                                ]
                            }
                        ],
                        'notices' : [
                            {
                                'noticeCategoryName' : '기타 재화',
                                'noticeCategoryDetailName' : '품명 및 모델명',
                                'content' : '상세설명참조'
                            },
                            {
                                'noticeCategoryName' : '기타 재화',
                                'noticeCategoryDetailName' : '법에 의한 인증·허가 등을 받았음을 확인할 수 있는 경우 그에 대한 사항',
                                'content' : '상세설명참조'
                            },
                            {
                                'noticeCategoryName' : '기타 재화',
                                'noticeCategoryDetailName' : '제조국 또는 원산지',
                                'content' : '상세설명참조'
                            },
                            {
                                'noticeCategoryName' : '기타 재화',
                                'noticeCategoryDetailName' : '제조자, 수입품의 경우 수입자를 함께 표기',
                                'content' : '상세설명참조'
                            },
                            {
                                'noticeCategoryName' : '기타 재화',
                                'noticeCategoryDetailName' : 'A/S 책임자와 전화번호 또는 소비자 상담 관련 전화번호',
                                'content' : '상세설명참조'
                            }
                        ]
                    }
                ]

            }
            #이미지 삽입
            for idx, img in enumerate(up_data[upload_index]['추가이미지']):
                img_data = {
                    'imageOrder' : idx+1,
                    'imageType' : 'DETAIL',
                    'vendorPath' : img
                }
                payload['items'][0]['images'].append(img_data)

            if up_data[upload_index]['옵션명'] != '':
                hashed_option_name = up_data[upload_index]['옵션명'].split('-')
                수집가격 = int(float(up_data[upload_index]['수집가격']))

                #옵션이미지 체크
                try:
                    up_data[upload_index]['옵션 이미지']
                except KeyError:
                    up_data[upload_index]['옵션 이미지'] = []
                    for _ in range(up_data[upload_index]['옵션 항목']):
                        up_data[upload_index]['옵션 이미지'].append("NONE")

                for idx, (item, price, image) in enumerate(zip(up_data[upload_index]['옵션 항목'], up_data[upload_index]['옵션 가격'], up_data[upload_index]['옵션 이미지'])):
                    if int(float(price)) + 수집가격 < 수집가격*1.5 and int(float(price)) + 수집가격 > 수집가격*0.5:
                        hashd_item = item.split('-')
                        option_data = {
                            'itemName' : item,
                            'originalPrice' : str(수집가격 + int(float(price))),
                            'salePrice' : str(수집가격 + int(float(price))),
                            'maximumBuyCount' : '9999',
                            'maximumBuyForPerson' : '0',
                            'maximumBuyForPersonPeriod' : '1',
                            'outboundShippingTimeDay' : '3',
                            'unitCount' : '0',
                            'adultOnly' : 'EVERYONE',
                            'taxType' : 'TAX',
                            'parallelImported' : 'NOT_PARALLEL_IMPORTED',
                            'overseasPurchased' : 'OVERSEAS_PURCHASED',
                            'pccNeeded' : True,
                            'externalVendorSku' : up_data[upload_index]['고유상품코드'],
                            'images' : payload['items'][0]['images'], #나주
                            'attributes' : [
                                {
                                    'attributeTypeName' : hashed_option_name[0],
                                    'attributeValueName' : hashd_item[0],
                                    "groupNumber": "NONE",
                                    'exposed' : 'EXPOSED'
                                }
                            ],
                            'contents' : [
                                {
                                    'contentsType' : 'HTML',
                                    'contentDetails' : [
                                        {
                                            'content' : brotli.decompress(up_data[upload_index]['상품상세']).decode(),
                                            'detailType' : 'TEXT'
                                        }
                                    ]
                                }
                            ],
                            'notices' : payload['items'][0]['notices'],
                        }
                        #옵션 이미지 등록
                        if image != "NONE":
                            option_data['images'] = []
                            option_data['images'].append({
                                'imageOrder' : '0',
                                'imageType' : 'REPRESENTATION',
                                'vendorPath' : image
                            })
                            option_data['images'].extend(payload['items'][0]['images'][1:])
                        else:
                            pass

                        if len(hashd_item) == 2:
                            additional_opt = {
                                'attributeTypeName' : hashed_option_name[1],
                                'attributeValueName' : hashd_item[1]
                            }
                            option_data['attributes'].append(additional_opt)

                        payload['items'].append(option_data)
                del payload['items'][0]

            payload = json.dumps(payload)
            response = requests.post('https://api-gateway.coupang.com'+path, headers=headers, data=payload)
            if response.status_code == 200:
                pd_num = response.json()['data']
                self.gui.update_console_subthread(f'상품 등록이 완료되었습니다 : {pd_num}')
                return pd_num
            else:
                self.gui.update_console_subthread(f'상품 등록에 실패했습니다 : {response.text}')
                return None
        except Exception as e:
            self.gui.update_console_subthread(f'상품 등록에 실패했습니다 : {e}')
            logging.exception(e)
            return None
        
class TempImgUploader:
    def __init__(self) -> None:
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/Users/jung-yongjun/Desktop/china/datas/alien-hour-386816-2123060270ca.json'
        self.storage_client = storage.Client()
        self.blob_id = queue.Queue()
        self.thread_list = []
        self.thread_order = queue.Queue()
        self.results = queue.Queue() #[order_index, result]
        self.exc_q = queue.Queue()
        self.retry_count = 0

    def __enter__(self):
        return self
    
    def upload(self, *args)->list:
        for i, link in enumerate(args):
            t = threading.Thread(target=self._upload, args=(link, i))
            t.daemon = True
            self.thread_list.append(t)
            self.thread_order.put(i)
            t.start()
        
        for thread in self.thread_list:
            thread.join()

        downloaded_link_list = [0]*self.results.qsize()
        while not self.exc_q.empty():
            raise self.exc_q.get()
        
        while not self.results.empty():
            index, result = self.results.get()
            downloaded_link_list[index] = result
        
        return downloaded_link_list
    
    def _upload(self, link, index):
        unique_id = str(uuid.uuid4()).replace('-','')
        try:
            if link == 'NONE':
                self.results.put((index, 'NONE'))
                return
            else:
                res = requests.get(link, timeout=60)

                if res.status_code != 200:
                    self.exc_q.put(BadDataError('이미지가 정상적으로 로드되지 않았습니다'))
                    return
                
                image = IMG.open(io.BytesIO(res.content))
                if image.mode == 'RGBA':
                    image = image.convert('RGB')
                output = io.BytesIO()
                image.save(output, format='JPEG')
                b_img = output.getvalue()
                
        except requests.exceptions.ConnectionError:
            if self.retry_count > 5:
                self.exc_q.put(BadDataError('네트워크 연결이 불안정합니다'))
                return

            self.retry_count += 1
            self._upload(link, index)
            return

        except requests.exceptions.ReadTimeout:
            if self.retry_count > 5:
                self.exc_q.put(BadDataError('네트워크 연결이 불안정합니다'))
                return
            
            self.retry_count += 1
            self._upload(link, index)
            return
        
        except:
            self.exc_q.put(BadDataError('네트워크 연결이 불안정합니다'))

        try:
            bucket = self.storage_client.bucket('twobasestore')
            blob = bucket.blob(unique_id)

            blob.upload_from_string(b_img)
            output.close()
            blob.content_type = 'image/jpeg'
            blob.update()
            self.blob_id.put(unique_id)

        except requests.exceptions.ReadTimeout:
            if self.retry_count > 5:
                self.exc_q.put(BadDataError('네트워크 연결이 불안정합니다'))
                return

            self.retry_count += 1
            self._upload(link, index)
            return
      
        except requests.exceptions.ConnectionError:
            if self.retry_count > 5:
                self.exc_q.put(BadDataError('네트워크 연결이 불안정합니다'))
                return

            self.retry_count += 1
            self._upload(link, index)
            return

        except:
            self.exc_q.put(BadDataError('네트워크 연결이 불안정합니다'))
        
        self.results.put((index, blob.public_url))
    
    def _delete(self, unique_id):
        try:
            bucket = self.storage_client.bucket('twobasestore')
            blob = bucket.blob(unique_id)
            blob.delete()

        except google.api_core.exceptions.NotFound:
            pass

        except:
            self.exc_q.put(ElementDeleteFailedError('임시 이미지 파일 삭제에 실패했습니다'))

    def __exit__(self, exc_type, exc_val, exc_tb):

        while not self.blob_id.empty():
            blob = self.blob_id.get()
            t = threading.Thread(target=self._delete, args=(blob, ))
            t.daemon = True
            self.thread_list.append(t)
            t.start()

        for thread in self.thread_list:
            thread.join()

        while not self.exc_q.empty():
            raise self.exc_q.get()
        
           
class Executor(Uploader):
    def __init__(self, business_account, chunk=1000):

        self.chunk = chunk
        self.business_account = business_account
        self.gui = GUI(business_account)
        super().__init__(self.gui, self.business_account, chunk=self.chunk)

        if '옥션' in list(self.market_acount[self.business_account].keys()) or '지마켓' in list(self.market_acount[self.business_account].keys()):
            try:
                self.cookies_ESM = self.login_ESM()
                self.gui.console.insert('1.0', 'ESM 로그인 성공 \n')
            except:
                self.cookies_ESM = 0
            
        elif '네이버' in list(self.market_acount[self.business_account].keys()):
            try:
                self.cookies_naver = self.login_naver()
                self.gui.console.insert('1.0', '네이버 로그인 성공 \n')
            except:
                self.cookies_naver = 0


    def _main(self, gui, index:int, *args):

        try:
            self.gui.update_console_subthread(f'업로더 {index+1} 로딩중...')
            logging.basicConfig(filename=f'datas/logging/process_status_00{index}.log', level=logging.INFO, force=True)
            up = Uploader(gui, self.business_account, chunk=self.chunk)

            if self.chunk > len(self.up_data):
                self.chunk = len(self.up_data)
            
            all_task = self.chunk
            global completed_task
            
            #chunk/max_workers가 실수인 경우에도 처리되도록 구현하려면 333+333+334 처럼 되야 할 듯
            #프로세스의 개수만큼 할당량을 쪼갬 : 
            #인덱스가 넘어가면 예외처리 해야 할 듯 함

            num = int(self.chunk/(self.max_workers))
            remainder = self.chunk - num*(self.max_workers)
            if remainder != 0 and index==self.max_workers-1:
                num_for_remainder = num+remainder
            else:
                num_for_remainder = num

            self.gui.update_console_subthread('업로더 로딩 완료! 상품 등록을 시작합니다')

        except Exception as e:
            logging.exception(e)

        for j in range(index*num, index*num+num_for_remainder):
            try:
                with TempImgUploader() as temp_uploader:
                    self.up_data[j]['상품이미지'] = temp_uploader.upload(self.up_data[j]['상품이미지'])[0]
                    self.up_data[j]['추가이미지'] = temp_uploader.upload(*self.up_data[j]['추가이미지'])
                    self.up_data[j]['옵션 이미지'] = temp_uploader.upload(*self.up_data[j]['옵션 이미지'])
                    
                    pd_num = self.up_data[j]['고유상품코드']

                    if '네이버' in args:
                        self.gui.update_console_subthread(f'네이버 상품 등록을 시작합니다 : {pd_num}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                        product_num_naver = up.upload_naver(j, self.up_data, self.cookies_naver)
                        db['pd_data'].update_one(
                            {'고유상품코드' : pd_num},
                            {'$set' : {
                                '업로드 마켓.네이버' : product_num_naver
                        }})

                    if '지마켓' in args and '옥션' in args:
                        self.gui.update_console_subthread(f'ESM 상품 등록을 시작합니다 : {pd_num}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                        product_num_auction, product_num_gmarket = up.upload_ESM(self.cookies_ESM, j, self.up_data, upload_supplement=False)
                        db['pd_data'].update_one(
                            {'고유상품코드' : pd_num},
                            {'$set' : {
                                '업로드 마켓.옥션' : product_num_auction,
                                '업로드 마켓.지마켓' : product_num_gmarket
                        }})

                    if '11번가' in args:
                        self.gui.update_console_subthread(f'11번가 상품 등록을 시작합니다 : {pd_num}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                        product_num_11st = up.upload_11st(j, self.up_data)
                        db['pd_data'].update_one(
                            {'고유상품코드' : pd_num},
                            {'$set' : {
                                '업로드 마켓.11번가' : product_num_11st,
                        }})

                    if '쿠팡' in args:
                        self.gui.update_console_subthread(f'쿠팡 상품 등록을 시작합니다 : {pd_num}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                        product_num_coupang = up.upload_coupang(j, self.up_data)
                        db['pd_data'].update_one(
                            {'고유상품코드' : pd_num},
                            {'$set' : {
                                '업로드 마켓.쿠팡' : product_num_coupang,
                        }})
        
            except IndexError:
                raise Exception('인덱스를 벗어나 프로세스를 중단합니다')
            except Exception as e:
                self.gui.update_console_subthread(f'{e.args} : {pd_num}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                logging.exception(f'프로세스에러 : {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
            
            finally:
                with lock:
                    completed_task += 1
                    progress_value = int(completed_task / all_task * 100)
                    self.gui.update_count_subthread(all_task, completed_task, progress_value)
        self.gui.is_done_queue.put(True)
                    
    def _run(self):
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)

        for index in range(self.max_workers):
            executor.submit(self._main, self.gui, index, *self.target_markgets)
        
        executor.shutdown(wait=False)
        self.gui.tk.mainloop()

    def retry(self, target_market_name:str, max_workers=4):
        self.max_workers = max_workers
        up_data = db['pd_data'].find({'$and' : [
                {'업로드 사업자' : self.business_account},
                {f'업로드 마켓.{target_market_name}' : {'$type' : 10}},
                ]})
        self.up_data = list(up_data)

        if '옥션' in target_market_name or '지마켓' in target_market_name:
                self.target_markgets = ['옥션', '지마켓']
        else:
            self.target_markgets = [target_market_name]
            
        self._run()

    def upload(self, max_workers=4):
        self.max_workers = max_workers
        up_data = db['pd_data'].find({'&and' : [
            {'업로드 사업자' : self.business_account},
            {'업로드 마켓' : {'&exist' : False}}
        ]
            })
        self.up_data = list(up_data)
        self.target_markgets = list(self.market_acount[self.business_account].keys())
        self._run()

    
if __name__ == "__main__":
    
    def upload_wrapper(account, chunk, max_workers):
        Executor(account, chunk=chunk).upload(max_workers=max_workers)
    
    def retry_wrapper(tg_markget, account, chunk, max_workers):
        Executor(account, chunk=chunk).retry(tg_markget, max_workers=max_workers)

    parser = argparse.ArgumentParser(description='수집한 상품을 업로드합니다')
    parser.add_argument('-a', '--account', help='업로드 사업자를 설정합니다', type=str, required=False, default='투베이스1')
    parser.add_argument('-t', '--threads', help='작업 스레드 수를 설정합니다. 기본값은 3입니다', type=int, default=5)
    parser.add_argument('-c', '--chunk', help='업로드할 총 상품 개수를 설정합니다. 기본값은 10000입니다', type=int, default=10000)

    # subparsers = parser.add_subparsers(help='commands')
    # parser_command1 = subparsers.add_parser('upload', help='상품 업로드')
    # parser_command1.set_defaults(func=upload_wrapper)

    # parser_command2 = subparsers.add_parser('retry', help='상품 복사등록')
    # parser_command2.set_defaults(func=retry_wrapper)

    args = parser.parse_args()

    account = '투베이스1'
    max_workers = args.threads
    chunk = args.chunk
    
    # if hasattr(args, 'func'):
    #     args.func(account, chunk, max_workers)
    retry_wrapper('11번가', account, chunk, max_workers)





