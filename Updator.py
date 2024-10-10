import json
import os
import requests
import time
import bcrypt
import pybase64
from bs4 import BeautifulSoup
import traceback
import time
import hmac, hashlib
import threading
import google.api_core.exceptions
from google.cloud import storage
import concurrent.futures
import pandas as pd
import jwt
from datetime import datetime, timedelta
import pymongo
import sys
from selenium.webdriver.chrome.service import Service
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import re
import logging
from Exceptions import *
import argparse
from tkinter import *
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from Exceptions import *
import queue
import signal

#1. 일단 self.complete_data를 뽑아옴
#2. 모든 상품링크에 접속하여 품절여부 확인, 
#3. 품절여부를 self.complete_data에 작성 -> 
    #고민1. 데이터를 쓰게 할 때 인자를 뭘로 받을지, -> 즉 2번에서 무엇을 반환하는지에 따라 달라질 것 같음 -> 
    #->애초에 2번 인자를 뭘로 받는데? -> 2번 인자는 완료 데이터, 인덱스를 받게 하면 되려나...
    #즉 2번에서 인자를 리스트 데이터 인자를 받는다
    #인덱스나, 상품 키 값이나, 가리키는 것은 똑같기 때문에 
    #재고 체크는 인덱스로 하고, 체크된 재고는 각 리스트의 요소에 담긴 고유 키 값을 ijson으로 찾은 후, 변경하기
    # 3번에서 각 키:값을 적용할 수 있음
    
    #어차피 메인 함수가 필요함 -> 근데 생각해보니까 어차피 각 반복문에서 돌아가는 데이터는 똑같잖아 인덱스든, 키 값이든 
    #2번의 결과와 키 값을 그냥 3번에 전달하면 되지 않나

lock = threading.Lock()
client = pymongo.MongoClient('')
db = client['twobasestore']

completed_task = 0

class GUI:
    def __init__(self, account) -> None:
        self.tk = Tk()
        self.tk.title(account + ' 상품 업데이트 진행상황')
        self.text_queue = queue.Queue()
        self.input_queue = queue.Queue()
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
        self.tk.bind('<<input_value>>', self.input_value)

        self.tk.protocol('WM_DELETE_WINDOW', self.exit)
        self.check_is_all_done()

    def update_count(self, e):
        self.label_text1.set('전체 : ' + str(self.all_task))
        self.label_text2.set('완료 : ' + str(self.completed_task))
        self.label_text3.set('진행률 : ' + str(self.progress_value)+'%')
    
    def update_console(self, e):
        text = str(self.text_queue.get())
        self.console.insert('1.0', text+'\n')

    def get_input_value(self, e):
        text = self.text_queue.get()
        raw_input = self.console.get('1.0', 'end-1c')
        input_value = raw_input.split(text)[1].split('\n')[0]
        self.input_queue.put(input_value)

    def input_value(self, e):
        self.tk.bind('<Return>', self.get_input_value)
        
    def exit(self):
        os.kill(os.getpid(), signal.SIGTERM)
    
    def input_value_subthread(self, text):
        self.text_queue.put(text)
        self.tk.event_generate('<<update_console>>', when='tail')

        self.text_queue.put(text)
        self.tk.event_generate('<<input_value>>')

    def update_count_subthread(self, all_task, completed_task, progress_value):
        self.all_task = all_task
        self.completed_task= completed_task
        self.progress_value = progress_value
        self.tk.event_generate("<<update_count>>", when="tail")

    def update_console_subthread(self, text):
        self.text_queue.put(text)
        self.tk.event_generate('<<update_console>>', when='tail')

    def check_is_all_done(self):
        if self.is_done_queue.qsize() == max_workers:
            self.update_console_subthread('상품 삭제가 모두 완료되었습니다 !')
        else:
            self.tk.after(100, self.check_is_all_done)
    

class Deleter:
    def __init__(self, gui:GUI, business_account):
        self.gui = gui
        with open('datas/Auth/Accounts.json', 'r') as file:
            self.market_acount = json.load(file)
        self.business_acount = business_account
        self.upload_acount = self.market_acount[business_account]
        self.do_ESM = True


    def _get_ESM_pd_data(self, pd_codes:list)->list:
        try:
            try:
                with lock:
                    with open(f'datas/Auth/ESM_AUTH_{self.business_acount}.json', 'r', encoding='utf-8') as file:
                        cookies_dict = json.load(file)
            
                decoded_token = jwt.decode(cookies_dict['ESM_TOKEN'], algorithms='HS512', options={"verify_signature": False})
                exp = decoded_token['iat']
                expiration_date = datetime.utcfromtimestamp(exp) + timedelta(hours=11)
                if datetime.utcnow() + timedelta(hours=9) > expiration_date:
                    cookies_dict = self.refresh_token_by_request()

            except:
                cookies_dict = self.refresh_token_by_request()

            if not self.do_ESM:
                self.gui.update_console_subthread('ESM 로그인 실패 재시작 해주세요')
                sys.exit()

            pd_codes_txt = ','.join(pd_codes)
            payload = 'paramsData={\"Keyword\":\"\","SiteId":"1","SellType":0,"CategoryCode":"","CustCategoryCode":0,"TransPolicyNo":0,"StatusCode":"","SearchDateType":0,"StartDate":"","EndDate":"","SellerId":"","StockQty":-1,"SellPeriod":0,"DeliveryFeeApplyType":0,"OptAddDeliveryType":0,"SellMinPrice":0,"SellMaxPrice":0,"OptSelUseIs":-1,"PremiumEnd":0,"PremiumPlusEnd":0,"FocusEnd":0,"FocusPlusEnd":0,"GoodsIds":"3161551326","SellMngCode":"","OrderByType":11,"NotiItemReg":-1,"EpinMatch":-1,"UserEvaluate":"","ShopCateReg":-1,"IsTPLUse":"","GoodsName":"","SdBrandId":0,"SdBrandName":"","IsGiftUse":""}&page=1&start=0&limit=30'
            payload = payload.replace('3161551326', pd_codes_txt).encode('utf-8')

            headers = {
                'Content-Type' : 'application/x-www-form-urlencoded; charset=UTF-8',
            }
            
            
            res = requests.post('https://www.esmplus.com/Sell/SingleGoodsMng/GetSingleGoodsList?_dc=1695800943312', headers=headers, cookies=cookies_dict, data=payload)
            return res.json()['data']
        
        except:
            logging.error('ESM 상품 정보 획득에 실패하였습니다 다음 청크로 넘어갑니다')
            raise BadDataError('ESM 상품 정보 획득에 실패하였습니다 다음 청크로 넘어갑니다')

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
            self.gui.exit()

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

            esm_token = re.findall(r'ESM_TOKEN=(.+?);', res.headers['Set-Cookie'])[0]
            esm_auth = re.findall(r'ESM_AUTH=(.+?);', res.headers['Set-Cookie'])[0]

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
    
    def delete_naver_product(self, pd_num):
        try:
            client_id = self.upload_acount['네이버']['client_id']
            client_secret = self.upload_acount['네이버']['client_secret']

            def get_token(client_id, client_secret):
                
                with lock:
                    token_url = "https://api.commerce.naver.com/external/v1/oauth2/token"
                    timestamp = str(int(time.time() * 1000)) # 현재 시간을 밀리초로 변환
                    # 전자서명 생성
                    clientId = client_id
                    clientSecret = client_secret
                    time.sleep(0.1)
                    # 밑줄로 연결하여 password 생성
                    password = clientId + "_" + str(timestamp)
                    # bcrypt 해싱
                    hashed = bcrypt.hashpw(password.encode('utf-8'), clientSecret.encode('utf-8'))
                    client_secret_sign = pybase64.standard_b64encode(hashed).decode('utf-8')

                    
                    # 인증 정보를 포함한 페이로드 생성
                    payload = {
                        'grant_type': 'client_credentials',
                        'client_id': client_id,
                        'timestamp': timestamp,
                        'client_secret_sign': client_secret_sign,
                        'type': 'SELF',
                    }

                    response = requests.post(token_url, data=payload)
                    
                    if response.status_code == 200:
                        data = response.json()
                        return data
                    else:
                        raise Exception(response.json())

            token = get_token(client_id, client_secret)['access_token']

            headers = {
                'Authorization' : token,
            }
            response = requests.delete(f'https://api.commerce.naver.com/external/v2/products/channel-products/{pd_num}', headers=headers)
            if response.status_code == 200:
                self.gui.update_console_subthread(f'상품 삭제가 완료되었습니다 : {pd_num}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')

            else:
                message = response.json()['message']
                self.gui.update_console_subthread(f'네이버 : {message}, {pd_num}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                logging.info('네이버 삭제 살패 : ' + str(message), + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
                raise ElementDeleteFailedError(f'네이버 삭제 살패 : {pd_num}, {str(message)},  {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
            
        except Exception as e:
            logging.exception(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
            raise BadDataError(f'상품 삭제를 실패하였습니다 : {e}')

    def delete_AC_product(self, pd_code, *args):
        try:
            try:
                with lock:
                    with open(f'datas/Auth/ESM_AUTH_{self.business_acount}.json', 'r', encoding='utf-8') as file:
                        cookies_dict = json.load(file)
            
                decoded_token = jwt.decode(cookies_dict['ESM_TOKEN'], algorithms='HS512', options={"verify_signature": False})
                exp = decoded_token['iat']
                expiration_date = datetime.utcfromtimestamp(exp) + timedelta(hours=11)
                if datetime.utcnow() + timedelta(hours=9) > expiration_date:
                    cookies_dict = self.refresh_token_by_request()

            except:
                cookies_dict = self.refresh_token_by_request()

            if not self.do_ESM:
                self.gui.update_console_subthread('ESM 로그인 실패 재시작 해주세요')
                sys.exit()
            
            # payload = 'paramsData={\"Keyword\":\"\","SiteId":"1","SellType":0,"CategoryCode":"","CustCategoryCode":0,"TransPolicyNo":0,"StatusCode":"","SearchDateType":0,"StartDate":"","EndDate":"","SellerId":"","StockQty":-1,"SellPeriod":0,"DeliveryFeeApplyType":0,"OptAddDeliveryType":0,"SellMinPrice":0,"SellMaxPrice":0,"OptSelUseIs":-1,"PremiumEnd":0,"PremiumPlusEnd":0,"FocusEnd":0,"FocusPlusEnd":0,"GoodsIds":"3161551326","SellMngCode":"","OrderByType":11,"NotiItemReg":-1,"EpinMatch":-1,"UserEvaluate":"","ShopCateReg":-1,"IsTPLUse":"","GoodsName":"","SdBrandId":0,"SdBrandName":"","IsGiftUse":""}&page=1&start=0&limit=30'
            # payload = payload.replace('3161551326', pd_code)

            # headers = {
            #     'Content-Type' : 'application/x-www-form-urlencoded; charset=UTF-8',
            # }

            # try:
            #     res = requests.post('https://www.esmplus.com/Sell/SingleGoodsMng/GetSingleGoodsList?_dc=1695800943312', headers=headers, cookies=cookies_dict, data=payload)
            #     res = res.json()['data'][0]
            # except IndexError:
            #     self.gui.update_console_subthread(f'옥션 : 상품 데이터가 없습니다 데이터를 삭제합니다, {pd_code}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
            #     return
            res = args[0]
            if res.__len__() == 0:
                self.gui.update_console_subthread(f'옥션 : 상품 데이터가 없습니다 데이터를 삭제합니다, {pd_code}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                return
            
            param = {
                'param' : [
                    {

                    "SingleGoodsNo":res['SingleGoodsNo'],
                    "ShowIAC":True,
                    "ShowGMKT":True,
                    "popupParamModel" : [
                        {
                            "SiteId":1,
                            "GoodsNo":res['SingleGoodsNo'],
                            "SiteGoodsNo":pd_code,
                            "SellerCustNo":res['SellerCustNoIAC'],
                            "SellerId":self.upload_acount['옥션']['ID'],
                            "SellType":"1",
                            },
                            {
                            "SiteId":2,
                            "GoodsNo":res['SingleGoodsNo'],
                            "SiteGoodsNo":res['SiteGoodsNoGMKT'],
                            "SellerCustNo":res['SellerCustNoGMKT'],
                            "SellerId":self.upload_acount['지마켓']['ID'],
                            "SellType":"1",
                            },
                        ]
                    },
                ],
                "siteType":"0"
            }
            if res['SiteGoodsNoGMKT'] == None:
                del param['param'][0]['popupParamModel'][1]
                param['param'][0]['ShowGMKT'] = False

            param = json.dumps(param).encode('utf-8')
            headers = {
                'Content-Type' : 'application/json; charset=utf-8'
            }

            requests.post('https://www.esmplus.com/Sell/SingleGoodsMng/SetSellStateChangeStop', cookies=cookies_dict, headers=headers, data=param)
            res = requests.post('https://www.esmplus.com/Sell/SingleGoodsMng/SetSellStateDelete', cookies=cookies_dict, headers=headers, data=param)

            if res.json()['Info'][0]['Info'][0]['Success']:
                self.gui.update_console_subthread(f'옥션 : 상품 삭제가 완료되었습니다, {pd_code}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')

            else:
                self.gui.update_console_subthread(f'옥션 : 상품 삭제를 실패했습니다, {pd_code}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                logging.info('옥션 : 상품 삭제 실패 ' + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
                raise ElementDeleteFailedError()

        except:
            self.gui.update_console_subthread(f'옥션 : 상품 삭제를 실패했습니다, {pd_code}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}' )
            logging.exception(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
            raise BadDataError()
            

    def delete_GMKT_product(self, pd_code, *args):
        try:
            try:
                with lock:
                    with open(f'datas/Auth/ESM_AUTH_{self.business_acount}.json', 'r', encoding='utf-8') as file:
                        cookies_dict = json.load(file)
            
                decoded_token = jwt.decode(cookies_dict['ESM_TOKEN'], algorithms='HS512', options={"verify_signature": False})
                exp = decoded_token['iat']
                expiration_date = datetime.utcfromtimestamp(exp) + timedelta(hours=11)
                if datetime.utcnow() + timedelta(hours=9) > expiration_date:
                    cookies_dict = self.refresh_token_by_request()

            except:
                cookies_dict = self.refresh_token_by_request()
            
            if not self.do_ESM:
                self.gui.update_console_subthread('ESM 로그인 실패 재시작 해주세요')
                sys.exit()

            # payload = 'paramsData={\"Keyword\":\"\","SiteId":"2","SellType":0,"CategoryCode":"","CustCategoryCode":0,"TransPolicyNo":0,"StatusCode":"","SearchDateType":0,"StartDate":"","EndDate":"","SellerId":"","StockQty":-1,"SellPeriod":0,"DeliveryFeeApplyType":0,"OptAddDeliveryType":0,"SellMinPrice":0,"SellMaxPrice":0,"OptSelUseIs":-1,"PremiumEnd":0,"PremiumPlusEnd":0,"FocusEnd":0,"FocusPlusEnd":0,"GoodsIds":"3161551326","SellMngCode":"","OrderByType":11,"NotiItemReg":-1,"EpinMatch":-1,"UserEvaluate":"","ShopCateReg":-1,"IsTPLUse":"","GoodsName":"","SdBrandId":0,"SdBrandName":"","IsGiftUse":""}&page=1&start=0&limit=30'
            # payload = payload.replace('3161551326', pd_code)

            # headers = {
            #     'Content-Type' : 'application/x-www-form-urlencoded; charset=UTF-8',
            # }

            # try:
            #     res = requests.post('https://www.esmplus.com/Sell/SingleGoodsMng/GetSingleGoodsList?_dc=1695800943312', headers=headers, cookies=cookies_dict, data=payload)
            #     res = res.json()['data'][0]
            # except IndexError :
            #     self.gui.update_console_subthread(f'지마켓 : 상품 데이터가 없습니다 데이터를 삭제합니다, {pd_code}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
            #     return 

            res = args[0]
            if res.__len__() == 0:
                self.gui.update_console_subthread(f'지마켓 : 상품 데이터가 없습니다 데이터를 삭제합니다, {pd_code}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                return 
            
            param = {
                'param' : [
                    {

                    "SingleGoodsNo":res['SingleGoodsNo'],
                    "ShowIAC":True,
                    "ShowGMKT":True,
                    "popupParamModel" : [
                        {
                            "SiteId":1,
                            "GoodsNo":res['SingleGoodsNo'],
                            "SiteGoodsNo":res['SiteGoodsNoIAC'],
                            "SellerCustNo":res['SellerCustNoIAC'],
                            "SellerId":self.upload_acount['옥션']['ID'],
                            "SellType":"1",
                            },
                            {
                            "SiteId":2,
                            "GoodsNo":res['SingleGoodsNo'],
                            "SiteGoodsNo":pd_code,
                            "SellerCustNo":res['SellerCustNoGMKT'],
                            "SellerId":self.upload_acount['지마켓']['ID'],
                            "SellType":"1",
                            },
                        ]
                    },
                ],
                "siteType":"0"
            }
            if res['SiteGoodsNoIAC'] == None:
                del param['param'][0]['popupParamModel'][0]
                param['param'][0]['ShowIAC'] = False

            param = json.dumps(param).encode('utf-8')
            headers = {
                'Content-Type' : 'application/json; charset=utf-8'
            }

            requests.post('https://www.esmplus.com/Sell/SingleGoodsMng/SetSellStateChangeStop', cookies=cookies_dict, headers=headers, data=param)
            res = requests.post('https://www.esmplus.com/Sell/SingleGoodsMng/SetSellStateDelete', cookies=cookies_dict, headers=headers, data=param)

            if res.json()['Info'][0]['Info'][1]['Success']:
                self.gui.update_console_subthread(f'지마켓 : 상품 삭제가 완료되었습니다, {pd_code}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')

            else:
                self.gui.update_console_subthread(f'지마켓 : 상품 삭제를 실패했습니다, {pd_code}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                logging.info('지마켓 : 상품 삭제 실패 ' + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
                raise ElementDeleteFailedError()

        except:
            self.gui.update_console_subthread(f'지마켓 : 상품 삭제를 실패했습니다, {pd_code}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
            logging.exception(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
            raise BadDataError()
        
    def delete_11st_product(self, custom_code):
        try:
            api_key = self.upload_acount['11번가']['api-key']

            headers = {
                'openapikey' : api_key
            }

            #11번가 상품 번호 획득
            response1 = requests.get(f'http://api.11st.co.kr/rest/prodmarketservice/sellerprodcode/{custom_code}', headers=headers)
            soup = BeautifulSoup(response1.content, 'lxml-xml')
            pd_num = soup.select_one('prdNo').text

            #상품판매중지
            response2 = requests.put(f'http://api.11st.co.kr/rest/prodstatservice/stat/stopdisplay/{pd_num}', headers=headers)
            soup = BeautifulSoup(response2.content, 'lxml-xml')
            message = soup.select_one('message').text

            self.gui.update_console_subthread(f'11번가 : {message}, {pd_num}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')

            if response2.status_code != 200:
                logging.info(message + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
                raise ElementDeleteFailedError()
            
        except AttributeError:
            self.gui.update_console_subthread(f'상품번호 할당에 실패했습니다 : {pd_num}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
        except Exception as e:
            raise BadDataError(f'상품삭제를 실패했습니다 {e}')

    def delete_coupang_product(self, custom_code):
        try:
            
            os.environ['TZ'] = 'GMT+0'

            api_key = self.upload_acount['쿠팡']['api-key']
            secret_key = self.upload_acount['쿠팡']['secret-key']

            #hmac 인증 후 헤더 발급
            def get_header(path, method):
                datetime=time.strftime('%y%m%d')+'T'+time.strftime('%H%M%S')+'Z'

                #hmac 인증
                message = datetime+method+path

                signature=hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'),hashlib.sha256).hexdigest()
                authorization = "CEA algorithm=HmacSHA256, access-key="+api_key+", signed-date="+datetime+", signature="+signature

                header = {
                    'authorization' : authorization, 
                    'Content-type' : 'application/json;charset=UTF-8'
                    }
                return header
            
            #상품번호 발급
            path = f'/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/external-vendor-sku-codes/{custom_code}'
            header = get_header(path, 'GET')

            response = requests.get('https://api-gateway.coupang.com'+path, headers=header)
            try:
                sellerProductId = response.json()['data'][0]['sellerProductId']
            except:
                self.gui.update_console_subthread(f'쿠팡 : {response.text}, {custom_code}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                return
            
            #옵션번호 발급
            path = f'/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{sellerProductId}'
            header = get_header(path, 'GET')
            response = requests.get('https://api-gateway.coupang.com'+path, headers=header)

            vendoritemids = []
            try:
                vendoritem_list = response.json()['data']['items']
                for item in vendoritem_list:
                    vendoritemid = item['vendorItemId']
                    vendoritemids.append(vendoritemid)
            except:
                self.gui.update_console_subthread(f'쿠팡 : {response.json()}, {custom_code}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                return
            

            #상품 옵션 판매중지
            for vendorItemId in vendoritemids:
                path = f'/v2/providers/seller_api/apis/api/v1/marketplace/vendor-items/{vendorItemId}/sales/stop'
                header = get_header(path, 'PUT')
                response = requests.put('https://api-gateway.coupang.com'+path, headers=header)

            #상품 삭제
            path = f'/v2/providers/seller_api/apis/api/v1/marketplace/seller-products/{sellerProductId}'
            header = get_header(path, 'DELETE')
            response = requests.delete('https://api-gateway.coupang.com'+path, headers=header)
            message = response.text

            self.gui.update_console_subthread(f'쿠팡 : {message}, {custom_code}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')

            if response.status_code != 200:
                logging.info(message + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
                raise ElementDeleteFailedError()

        except KeyError:
            self.gui.update_console_subthread(f'쿠팡 계정 없음 : {self.business_acount}')
        except Exception as e:
            raise BadDataError(f'상품 삭제 실패 : {e}')

    def _img_deleter(self, code):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = ''
        storage_client = storage.Client()
        bucket = storage_client.bucket('twobasestore')
        try:
            blob = bucket.blob(code)
            blob.delete()
            self.gui.update_console_subthread(f'이미지 삭제 성공 : {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
        except google.api_core.exceptions.NotFound as e:
            pass
        except:
            raise BadDataError('예기치 않은 이유로 이미지 삭제를 실패했습니다')


class Executor(Deleter):
    def __init__(self, business_account):
        self.business_account = business_account
        self.gui = GUI(business_account)

        super().__init__(self.gui, self.business_account)
        self.cookies = self.refresh_token_by_request()
        logging.basicConfig(filename=f'datas/logging/Updator1.log', level=logging.INFO, force=True)

    def img_deleter(self, data):
        try:
            img_codes = data['상품상세']
            img_codes = BeautifulSoup(img_codes, 'html.parser').select('img')
            img_codes = [img['src'] for img in img_codes if 'twobasestore/' in img['src']]

            img_codes.append(data['상품이미지'])
            img_codes = img_codes + data['추가이미지'] + data['옵션 이미지']
            
            img_codes = [img for img in img_codes if 'twobasestore/' in img]

            for img in img_codes:
                try:
                    img = img.split('twobasestore/')[1]
                    self._img_deleter(img)
                except IndexError:
                    pass
        except BadDataError as e:
            raise e
        except:
            pass

    def _market_deleter(self, data, *args):
        global completed_task

        pd_data_AC = args[0]
        pd_data_GMKT = args[1]

        tg_pd_data_AC = []
        tg_pd_data_GMKT = []

        pd_code = data['고유상품코드']
        is_delete_succeeded = []
        try:
            pd_num_naver = data['업로드 마켓']['네이버']
            if pd_num_naver == None:
                pd_num_naver = 'None'
        except KeyError:
            pd_num_naver = 'None'

        try:
            pd_num_AC = data['업로드 마켓']['옥션']
            if pd_num_AC == None:
                pd_num_AC = 'None'

            for i, d in enumerate(pd_data_AC):
                if d['SiteGoodsNoIAC'] == str(pd_num_AC):
                    tg_pd_data_AC = pd_data_AC[i]
                    break

        except KeyError:
            pd_num_AC = 'None'
        
        try:
            pd_num_GMKT = data['업로드 마켓']['지마켓']
            if pd_num_GMKT == None:
                pd_num_GMKT = 'None'

            for i, d in enumerate(pd_data_GMKT):
                if d['SiteGoodsNoGMKT'] == str(pd_num_GMKT):
                    tg_pd_data_GMKT = pd_data_GMKT[i]
                    break

        except KeyError:
            pd_num_GMKT = 'None'
        
        if '네이버' in self.target_markgets:
            try:
                self.delete_naver_product(pd_num_naver)
                db['pd_data'].update_one(
                    {'고유상품코드' : pd_code},
                    {'$set' : {
                        '업로드 마켓.네이버' : None
                    }}
                    )
                is_delete_succeeded.append(True)
            except:
                is_delete_succeeded.append(False)
                

        if '옥션' in self.target_markgets or '지마켓' in self.target_markgets:
            try:
                self.delete_AC_product(pd_num_AC, tg_pd_data_AC)
                db['pd_data'].update_one(
                    {'고유상품코드' : pd_code},
                    {'$set' : {
                        '업로드 마켓.옥션' : None
                    }}
                    )
                is_delete_succeeded.append(True)
            except:
                is_delete_succeeded.append(False)

            try:
                self.delete_GMKT_product(pd_num_GMKT, tg_pd_data_GMKT)
                db['pd_data'].update_one(
                    {'고유상품코드' : pd_code},
                    {'$set' : {
                        '업로드 마켓.지마켓' : None
                    }}
                    )
                is_delete_succeeded.append(True)
            except:
                is_delete_succeeded.append(False) 

        if '11번가' in self.target_markgets:
            try:
                self.delete_11st_product(pd_code)
                db['pd_data'].update_one(
                    {'고유상품코드' : pd_code},
                    {'$set' : {
                        '업로드 마켓.11번가' : None
                    }}
                    )
                is_delete_succeeded.append(True)
            except:
                is_delete_succeeded.append(False)

        if '쿠팡' in self.target_markgets:
            try:
                self.delete_coupang_product(pd_code)
                db['pd_data'].update_one(
                    {'고유상품코드' : pd_code},
                    {'$set' : {
                        '업로드 마켓.쿠팡' : None
                    }}
                    )
                is_delete_succeeded.append(True)
            except:
                is_delete_succeeded.append(False)
        
        if all(is_delete_succeeded):
            db['pd_data'].delete_one({'고유상품코드' : pd_code})

        with lock:
            completed_task += 1
            progress_value = int(completed_task / self.all_task * 100)
            self.gui.update_count_subthread(self.all_task, completed_task, progress_value)

    def delete(self):
        self.max_workers = 1
        self.complete_data = list(db['pd_data'].find({'업로드 사업자' : self.business_account}))
        self.gui.update_console_subthread(len(self.complete_data))
        
        self.run(self._delete)

    def delete_all(self, max_workers, delete_season_pd=False, ignore_DontDeleteList=False):
        self.max_workers = max_workers
        DontDeleteList = list(db['view'].find())
        DontDeleteList = [i['id'] for i in DontDeleteList]

        if ignore_DontDeleteList:
            self.complete_data = list(db['pd_data'].find({ '$and' : [
                {'업로드 사업자' : self.business_account},
                {'업로드 마켓'  : {'$exists' : True}}
            ]
            }))
        
        elif delete_season_pd:
            self.complete_data = list(db['pd_data'].find({ '$and' : [
                {'업로드 사업자' : self.business_account},
                {'업로드 마켓' : {'$exists' : True}},
                {'고유상품코드' : {'$nin' : DontDeleteList}},
            ]
            }))
        
        else:
            self.complete_data = list(db['pd_data'].find({ '$and' : [
                {'업로드 사업자' : self.business_account},
                {'고유상품코드' : {'$nin' : DontDeleteList}},
                {'업로드 마켓' : {'$exists' : True}},
                {'시즌성여부' : False },
                ]})
            )
        self.gui.update_console_subthread(len(self.complete_data))

        self.run(self._delete_all)

    def delete_many(self):
        self.max_workers = 1
        self.complete_data = list(db['pd_data'].find({'업로드 사업자' : self.business_account}))
        self.gui.update_console_subthread(len(self.complete_data))

        self.run(self._delete_many)
    
    def _delete(self, i):        
        try:
            
            self.gui.input_value_subthread('삭제할 코드 입력 : ')
            ask_code = self.gui.input_queue.get()
            ask_codes = ask_code.split(',')
            self.all_task = len(ask_codes)

            for ask_code in ask_codes:
                data = db['pd_data'].find_one({'$and' : [
                    {'고유상품코드' : ask_code.strip()},
                    {'업로드 사업자' : self.business_account}
                    ]})
                
                self.gui.update_console_subthread(data['고유상품코드']) 
                self._market_deleter(data)                   
                self.img_deleter(data)
                
        except TypeError:
                self.gui.update_console_subthread('코드 없음')
        except:
            logging.exception(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))

    def _delete_all(self, i):
        chunk = len(self.complete_data)
        num = int(chunk/(self.max_workers))
        remainder = chunk - num*(self.max_workers)

        self.all_task = chunk
        #chunk/max_workers가 실수인 경우에도 처리되도록 구현하려면 333+333+334 처럼 되야 할 듯

        if remainder != 0 and i==self.max_workers-1:
            num_for_remainder = num+remainder
        else:
            num_for_remainder = num

        j = i*num
        index = 0
        while j < i*num+num_for_remainder:
            try:
                if index % 30 == 0:
                    try:
                        if j+30 > i*num+num_for_remainder:
                            pd_codes_AC = [self.complete_data[k]['업로드 마켓']['옥션'] for k in range(j, i*num+num_for_remainder)]
                            pd_codes_GMKT = [self.complete_data[k]['업로드 마켓']['지마켓'] for k in range(j, i*num+num_for_remainder)]
                        else:
                            pd_codes_AC = [self.complete_data[k]['업로드 마켓']['옥션'] for k in range(j, j+30)]
                            pd_codes_GMKT = [self.complete_data[k]['업로드 마켓']['지마켓'] for k in range(j, j+30)]

                        pd_codes_AC = [code if code is not None else 'None' for code in pd_codes_AC]
                        pd_codes_GMKT = [code if code is not None else 'None' for code in pd_codes_GMKT]

                        pd_data_AC = self._get_ESM_pd_data(pd_codes_AC)
                        pd_data_GMKT = self._get_ESM_pd_data(pd_codes_GMKT)
     
                    except Exception as e:
                        self.gui.update_console_subthread(str(e))
                        j += 30
                        index += 30
                        continue

                self._market_deleter(self.complete_data[j], pd_data_AC, pd_data_GMKT)
                self.img_deleter(self.complete_data[j])

            except:
                logging.exception(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
            j+=1
            index+=1

        self.gui.is_done_queue.put(True)

    def _delete_many(self, i):
        try:
            df = pd.read_excel('delete_codes.xlsx')
            ask_codes = df['codes']

        except Exception:
            logging.exception(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
                  
        for ask_code in ask_codes:
            try:
                ask_code = ask_code.strip()
                data = db['pd_data'].find_one({'$and' : [
                    {'고유상품코드' : ask_code},
                    {'업로드 사업자' : self.business_account}
                    ]})
                
                self.gui.update_console_subthread(data['고유상품코드'])
                self._market_deleter(data)          
                self.img_deleter(data)
            except TypeError:
                self.gui.update_console_subthread('코드 없음')
            except:
                logging.exception(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))

    def run(self, function):
        self.target_markgets = list(self.market_acount[self.business_account].keys())

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)
        for i in range(self.max_workers):
            executor.submit(function, i)
        executor.shutdown(wait=False)
       
        self.gui.tk.mainloop()


if __name__ == '__main__':
    """재고 설정 후 재고가 없다면 예외를 반환하고 self.delete 메서드에 적용해야함"""

    def delete_wrapper(account, max_workers):
        Executor(account).delete()

    def delete_all_wrapper(account, max_workers, delete_season_pd=False, ignore_DontDeleteList=False):
        Executor(account).delete_all(max_workers=max_workers, delete_season_pd=delete_season_pd, ignore_DontDeleteList=ignore_DontDeleteList)

    def delete_many_wrapper(account, max_workers):
        Executor(account).delete_many()

        
    parser = argparse.ArgumentParser(description='업로드한 상품을 제거합니다')
    parser.add_argument('-a', '--account', help='업로드 사업자를 설정합니다', type=str, required=False, default='투베이스1')
    parser.add_argument('-t', '--threads', help='작업 스레드 수를 설정합니다. 기본값은 3입니다', type=int, default=3)

    # subparsers = parser.add_subparsers(help='commands')
    # parser_command1 = subparsers.add_parser('delete', help='상품 하나 삭제')
    # parser_command1.set_defaults(func=delete_wrapper)

    # parser_command2 = subparsers.add_parser('delete_all', help='모든 상품 삭제')
    # parser_command2.set_defaults(func=delete_all_wrapper)

    # parser_command3 = subparsers.add_parser('delete_many', help='엑셀로 여러 상품 삭제')
    # parser_command3.set_defaults(func=delete_many_wrapper)

    args = parser.parse_args()

    account = '투베이스1'
    max_workers = args.threads
        
    # if hasattr(args, 'func'):
    #     args.func(account, max_workers)

    delete_all_wrapper(account, max_workers, delete_season_pd=True)
