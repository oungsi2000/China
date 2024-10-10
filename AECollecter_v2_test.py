import time
import pandas as pd
import random
import json
import time
import concurrent.futures
import re
import logging
import queue
import requests
import base64
import threading
import js2py
import itertools
import subprocess
from bs4 import BeautifulSoup
import html
import brotli
from _Collector import _Collector, _AdditionalModules
from Exceptions import *
import argparse
from tkinter import *
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from tkinter import messagebox
import os
import signal
import threading

parser = argparse.ArgumentParser(description='알리익스프레스의 상품을 대량 수집합니다')
parser.add_argument('-a', '--account', help='업로드 사업자를 설정합니다', type=str, required=False, default='투베이스1')
parser.add_argument('-t', '--threads', help='작업 스레드 수를 설정합니다. 기본값은 4입니다', type=int, default=4)
parser.add_argument('-m', '--margin_rate', help='마진율을 설정합니다 기본값은 1.3입니다', type=float, default=1.3)
parser.add_argument('-e', '--extra_cost', help='추가 금액을 설정합니다 기본값은 9000원 입니다', type=int, default=9000)

args = parser.parse_args()

#전역 프로세스 변수
total_task = 0
succeed_task = 0
failed_task = 0
prohibit_task = 0

lock = threading.Lock()
user_agents = open('Proxycrawl/UserAgent.txt').readlines()


class AECollecter(_Collector):
    def __init__(self, gui, upload_account, margin_rate=args.margin_rate, extra_cost=args.extra_cost):
        super().__init__()
        
        #html형식으로 입력
        self.margin_rate = margin_rate
        self.extra_cost = extra_cost
        self.upload_account = upload_account
        self.gui = gui

        ###기본 설정은 이곳에서 확인바랍니다
        self.up_image = 'https://i.ibb.co/MSj54nK/AEup.png'
        self.down_image = 'https://i.ibb.co/8Mw2Gwq/AEdown.png'
        self.load_file_name = f'datas/수집목록_{self.upload_account}.xlsx'
        prohibit_links_file_name = 'LinkCollector/수집제한목록.json'
        prohibit_word_file_name = 'datas/금지단어.xlsx'
        word_pair_file_name = 'datas/제외단어.xlsx'

        self.prohibit_links = self.load_prohibit_links(prohibit_links_file_name)

        self.data_loader(self.load_file_name)
        self.prohibit_word_loader(prohibit_word_file_name)
        self.replace_word_loader(word_pair_file_name)
    
    def print(self, msg):
        self.gui.update_console_subthread(msg)

    def load_ctgy_kw(self, linkcount):
        with lock:
            self.title = pd.read_excel(self.load_file_name).fillna('')
            self.title_keywords1 = self.title['TitleKeyword1'].loc[linkcount].split(',')
            self.title_keywords2 = self.title['TitleKeyword2'].loc[linkcount].split(',')
            self.title_keywords3 = self.title['TitleKeyword3'].loc[linkcount].split(',')
            
            self.start_point = self.page_amount_start[linkcount]
            self.end_point = self.page_amount_finish[linkcount]+1

            self.category_Naver = str(self.title['category_Naver'].loc[linkcount])
            self.category_AC = str(self.title['category_AC'].loc[linkcount])
            self.category_GMKT = str(self.title['category_GMKT'].loc[linkcount])
            self.category_11st = str(self.title['category_11st'].loc[linkcount])
            self.category_Coupang = str(self.title['category_Coupang'].loc[linkcount])

            self.is_season_pd = str(self.title['is_season'].loc[linkcount])
            if self.is_season_pd == 'T' or 'True':
                self.is_season_pd = True
            else:
                self.is_season_pd = False

    def get_item_data(self):
        for script in self.scripts :
            if 'searchRefineFilters' in script.text:
                while True:
                    try:
                        data = js2py.eval_js(script.text)
                        break
                    except:
                        pass
                    

                data = data.to_dict()    
                try:
                    pd_data = data['data']['data']['root']['fields']['mods']['itemList']['content']
                except KeyError:
                    try:
                        pd_data = data['data']['data']['root']['fields']['searchResult']['mods']['itemList']['content']
                    except KeyError:
                        pd_data = []
                for code in pd_data:
                    self.product_url.append('https://ko.aliexpress.com/item/'+code['productId']+'.html?')
                break

        if 'x5referer' in script.text and self.product_url.__len__() == 0:
            raise WebsiteShutdownError()
        
    def get_pd_name(self):
        self.productname = self.raw_data['productInfoComponent']['subject'].strip()

    def get_pd_desc(self):
        description_link = self.raw_data['productDescComponent']['descriptionUrl']
        response = requests.get(description_link)

        raw_detail_contents = re.sub(r'style="[^"]*"', 'style="padding-top:12px;"', response.text)
        raw_detail_contents = re.sub(r'align="[^"]*"', '', raw_detail_contents)

        soup_dt_cont = BeautifulSoup(raw_detail_contents, 'html.parser')

        #스크립트 태그 제거
        for tag in soup_dt_cont.find_all('script'):
            tag.decompose()

        img_links = soup_dt_cont.select('img')
        for element in img_links:
            try:
                if 'http' not in element['src'] and '//' in element['src']:
                    element['src'] = 'https:'+element['src']
            except KeyError:
                pass

        detailmodule_html = soup_dt_cont.select_one('.detailmodule_html')
        detail_contents = str(detailmodule_html)

        if detail_contents == 'None' or len(soup_dt_cont.select('.detailmodule_html')) > 1:
            detail_contents = soup_dt_cont.new_tag('div')
            detail_contents['class'] = 'detailmodule_html'
            detail_contents['style'] = 'text-align:center; font-size:16px;'
            detail_contents.append(soup_dt_cont)
            self.detail_contents = str(detail_contents)
        else:
            detailmodule_html['style'] = 'text-align:center; font-size:16px;'
            self.detail_contents = str(detailmodule_html)

    def get_pd_info(self):
        try:
            self.product_info = self.raw_data['productPropComponent']['props']
        except:
            self.product_info = ''

    def get_opt_data(self):
        raw_opt_values = []
        raw_option_images = []
        self.option_values = []
        self.option_names = []
        self.option_images = []

        raw_option_value_codes = []
        self.option_value_codes = []

        if self.raw_data['skuComponent']['hasSkuProperty']:
            for option_data in self.raw_data['skuComponent']['productSKUPropertyList']:
                if option_data['skuPropertyName'] != '배송지':
                    self.option_names.append(option_data['skuPropertyName'])
                    inner_opt_value = []
                    inner_opt_value_codes = []
                    inner_opt_images = []

                    txt_count = 1
                    for inner_value in option_data['skuPropertyValues']:
                        if inner_value['skuPropertyTips'].replace('-', ' ') in inner_opt_value:
                            inner_opt_value.append(inner_value['skuPropertyTips'].replace('-', ' ')+'(2)')
                        else:
                            inner_opt_value.append(inner_value['skuPropertyTips'].replace('-', ' '))
                        inner_opt_value_codes.append(str(option_data['skuPropertyId']) +':'+ str(inner_value['propertyValueId'])) 
                        
                        try:
                            opt_img = inner_value['skuPropertyImagePath']                     
                            opt_text = f'[0{txt_count}] ' + inner_value['skuPropertyValueTips']
                            self.opt_texts.append(opt_text)
                            self.opt_imgs.append(opt_img)

                            txt_count +=1
                            inner_opt_images.append(opt_img)

                        except KeyError:
                            inner_opt_images.append('NONE')
                            pass

                    raw_opt_values.append(inner_opt_value)
                    raw_option_value_codes.append(inner_opt_value_codes)
                    raw_option_images.append(inner_opt_images)
            
            if raw_opt_values.__len__() != 0:
                for combo in itertools.product(*raw_opt_values):
                    self.option_values.append('-'.join(combo))
                for combo in itertools.product(*raw_option_value_codes):
                    self.option_value_codes.append('@$'.join(combo))                 
                for combo in itertools.product(*raw_option_images):
                    self.option_images.append(combo[0])
                
        #옵션 이름 정제
        self.option_name = '-'.join(self.option_names)      

        #옵션 개수 3개 이상인지 체크              
        self.is_over_3_opt = len(self.option_name.split('-')) > 2
    
    def get_opt_price(self):
        self.option_prices = []

        if self.raw_data['skuComponent']['hasSkuProperty']:
            for option_value_code in self.option_value_codes:
                targets = option_value_code.split('@$')

                price_list = self.raw_data['priceComponent']['skuPriceList']
                for price_info in price_list:
                    if all(True if target in price_info['skuAttr'] else False for target in targets):
                        try:
                            option_price = price_info['skuVal']['skuActivityAmount']['value'] + self.shipping_price
                        except KeyError:
                            option_price = price_info['skuVal']['skuAmount']['value'] + self.shipping_price
                        option_price = str(self.zero(option_price*self.margin_rate + self.extra_cost) - int(self.normal_price))
                        self.option_prices.append(option_price)
                        break
    def get_img(self):
        self.product_images = []
        for item in self.raw_data['imageComponent']['imagePathList']:
            if 'http' not in item:
                item = 'https:' + item
            self.product_images.append(item)

    def get_price(self):

        self.is_shipping_unavailable = False
        
        try:
            raw_price = self.raw_data['priceComponent']['discountPrice']['minActivityAmount']['value']
        except KeyError:
            raw_price = self.raw_data['priceComponent']['origPrice']['minAmount']['value']

        #스탠다드 쉬핑 배송비 수집
        shipping_data = self.raw_data['webGeneralFreightCalculateComponent']['originalLayoutResultList']

        try:
            target = list(filter(lambda data:data['bizData']['deliveryProviderName'] == 'AliExpress Standard Shipping', shipping_data))
        except:
            self.is_shipping_unavailable = True

        if target.__len__() == 0:
            target = [shipping_data[0]]

        try:
            self.shipping_price = target[0]['bizData']['displayAmount']
        except KeyError:
            self.shipping_price = 0
        
        raw_price += self.shipping_price
        self.normal_price = str(self.zero(raw_price*self.margin_rate + self.extra_cost))

    def refine_detail(self):
        
        detail = str(html.unescape(self.detail_contents))
        
        with lock:
            with open('datas/tracking.png', "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode()
        
        for _ in range(5):
            # tracker_url = self.module.get_url(encoded_string)
            tracker_url = ''
            if tracker_url != None:
                break

        if tracker_url == None:
            raise OSError('트래커 업로드 실패')
        
        self.detail = f'''
        <div style=\"text-align:center;\">
            <img src=\"{tracker_url}\" border=\"0\">
            <img src=\"{self.up_image}\" border=\"0\" width=\"860\">
            {self.custom_html}
            {detail}
            <img src=\"{self.down_image}\" border=\"0\" width=\"860\">
        </div>
        '''

    def run(self, linkcount, cookie):
        self.module = _AdditionalModules()

        #진행상황 인자 받기
        global total_task 
        global succeed_task 
        global failed_task 
        global prohibit_task

        #제목 앞 키워드
        self.load_ctgy_kw(linkcount)

        #사이트 내 검색 후 해당 링크 get 요청

        for PageA in range(self.start_point, self.end_point):
            link_list = self.pagelink[linkcount].split('&page=')[0]

            with lock:
                try:
                    #유저에이전트 뽑기
                    for _ in range(5):
                        user_agent = random.choice(user_agents).replace('\n', '')
                        link = link_list+f'&page={PageA}'
                        res = requests.get(link, headers=
                                        {'User-Agent' : user_agent,
                                            'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                                            "Referer" : 'https://www.aliexpress.com//w/wholesale-.html/_____tmd_____/punish?x5secdata=xcQORzktCGJtwIGtYoW1A%2fcmANUCgfgFmj%2fZgP9cLmW7r3SC5lSJ8HK3uXYrmqSAUUcxYb6aWfIXgvacPlWDoQ80knudGU2gFUri7jN%2fEADa%2bMkranBJ%2ff0ZDRMkSCqDx5Aa9RdH8ACKtK%2b%2f2ARdVscdkmc0E%2by9DrpoPIQya7dBEH7evES0OE4Cld4p%2bq1YXJXoYKPigDSyEqVXld377EK00VyUmF5E1U8pfJeWPnXJOK4dLdxkfFzhHSMSjOz7VQTYFmeNlvNbJcMqjURiZEzVsJrYO5OiSCZC59S%2fHLZwg%3d__bx__www.aliexpress.com%2fw%2fwholesale-.html&x5step=1',
                                            'Cookie' : cookie.strip()})
                        soup = BeautifulSoup(res.text, 'html.parser')
                        e = soup.select('.search-card-item')
                        f = soup.select('.lazy-load')

                        count = len(e) + len(f)
                        if count != 0:
                            break
                    
                    self.scripts = soup.select('script')
                    self.product_url = []

                    #상품 정보를 담고 있는 js실행
                    
                    self.get_item_data()

                    countcode = len(self.product_url)
                    self.gui.update_console_subthread(f'총 {countcode} 개의 코드를 수집했습니다')
                    
                    if countcode < 10:
                        time.sleep(random.randint(20, 25))

                except WebsiteShutdownError:
                    self.gui.update_console_subthread(f'접속이 제한되었습니다 쿠키 재설정 부탁드립니다: {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                    self.gui.reset_cookie_subthread(linkcount)
                    return
                
                except:
                    self.gui.update_console_subthread(f'수집 페이지 로딩에 실패했습니다 : {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                        
                    logging.exception(f'에러 발생! : {link}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')

            for num in range(countcode):
                
                #결과값 중복 수집을 막기 위한 이벤트 신호 do_check (boolen)                    
                try : 
                    #수집된 링크에서 정보 수집
                    self.gui.update_console_subthread(self.product_url[num])

                    #Optioncreator 전용 변수
                    self.opt_imgs = []
                    self.opt_texts = []

                    #유저 에이전트 뽑기
                    count = 0
                    
                    while True:

                        res = requests.get(self.product_url[num],
                                           headers={
                                               'Cookie' : cookie.strip()
                                           })
                        soup = BeautifulSoup(res.text, 'html.parser')
                        if 'metaDataComponent' in res.text:
                            break
                        elif count > 10:
                            # self.gui.update_console_subthread(f'페이지가 없습니다 : {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                            break
                        else:
                            count += 1

                    self.pd_scripts = soup.select('script')

                    #상품 정보를 담고 있는 자바스크립트 파일 실행
                    for pd_script in self.pd_scripts:
                        if 'metaDataComponent' in pd_script.text:
                            while True:
                                try:
                                    raw_data = js2py.eval_js('function custom(){'+pd_script.text+'return window.runParams} custom()')
                                    break
                                except:
                                    pass
                            
                            self.raw_data = raw_data.to_dict()['data']
                            break
                    
                    #수집제한링크 필터링
                    # is_prohibit_link = self.product_url[num] in self.prohibit_links 

                    # #금지단어 필터링 / 이때 알리 원본을 수집하고 수집

                    # #1.상품명
                    # self.get_pd_name()

                    # #2.상품상세
                    # self.get_pd_desc()
                    
                    # #3.옵션 수집
                    # self.get_opt_data()

                    # #4. 상품정보고시 수집
                    # self.get_pd_info()

                    # #5. 가격 수집
                    # self.get_price()

                    # #텍스트 조합
                    # text_content = self.productname + ',' + self.detail_contents + ','+ str(self.product_info)
                    # matched_keywords = [keyword for keyword in self.prohibit_filer_keywords if keyword.lower() in text_content.lower()]
                    # matched_keywords = ','.join(matched_keywords)

                    # is_prohibit_word = any(keyword.lower() in text_content.lower() for keyword in self.prohibit_filer_keywords)

                    # #수집한 상품 여부 체크
                    # is_already_done = self.db['pd_data'].find_one({'상품링크' : self.product_url[num]}) != None
                    # is_out_of_stock = self.raw_data['inventoryComponent']['totalAvailQuantity'] == 0

                    # #작업결과1
                    if random.randint(1,10) > 5:
                        self.gui.update_console_subthread(f'금지단어가 발견되어 수집대상에서 제외합니다 : {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                        prohibit_task += 1
                        continue

                    elif random.randint(1,10) > 9:
                        self.gui.update_console_subthread(f'이미 수집된 상품입니다 : {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                        failed_task +=1
                        continue
                    
                    # elif is_prohibit_link:
                    #     self.gui.update_console_subthread(f'수집이 제한된 링크입니다 : {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                    #     prohibit_task +=1
                    #     continue
                    
                    # elif is_out_of_stock:
                    #     self.gui.update_console_subthread(f'전체 옵션 품절 상품입니다 : {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                    #     failed_task +=1
                    #     continue

                    # elif self.is_over_3_opt:
                    #     self.gui.update_console_subthread(f'옵션 개수가 3개 이상입니다 : {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                    #     self.gui.update_console_subthread('3개 이상의 옵션은 향후 추가 예정입니다')
                    #     failed_task +=1
                    #     continue

                    # elif self.is_shipping_unavailable:
                    #     self.gui.update_console_subthread(f'배송이 불가능한 상품입니다 : {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                    #     prohibit_task +=1
                    #     continue

                    # #브랜드명 수집 -> 알리에선 수집 안함
                    # brand = ''

                    # #상품명 수집
                    # title_keyword1 = random.choice(self.title_keywords1)
                    # title_keyword2 = random.choice(self.title_keywords2)
                    # title_keyword3 = random.choice(self.title_keywords3)
                    # self.productname = title_keyword1 +' '+ title_keyword2 + ' '+ self.replace_word(self.productname, self.word_pairs)+' '+ title_keyword3

                    # #이미지 수집
                    # self.get_img()

                    # #옵션 가격 수집
                    # self.get_opt_price()

                    # #OptionCreator.py 실행
                    # result = subprocess.run(['python3', 'OptionCreator.py', '-l', json.dumps(self.opt_imgs), json.dumps(self.opt_texts), json.dumps(self.product_info)], capture_output=True, text=True)
                    # self.custom_html = result.stdout.strip()
                    # product_real_url = self.product_url[num]
                
                    # self.refine_detail()

                    # #별도의 스레드 실행, data 인자 전달
                    # arg_data = {
                    #     '카테고리' : {
                    #         '네이버' : self.category_Naver, #str
                    #         '옥션' : self.category_AC, #str
                    #         '지마켓' : self.category_GMKT, #str
                    #         '11번가' : self.category_11st, #str
                    #         '쿠팡' : self.category_Coupang #str
                    #         },
                    #     '브랜드' : brand, #str
                    #     '상품링크' : product_real_url, #str
                    #     '상품명' : self.productname, #str
                    #     '수집가격' : self.normal_price, #str
                    #     '상품이미지': self.product_images[1], #array
                    #     '상품상세' : {
                    #         '상단이미지' : self.up_image,
                    #         '커스텀 옵션' : self.custom_html,
                    #         '상세페이지' : self.detail_contents,
                    #         '하단이미지' : self.down_image
                    #     }, #str / html
                    #     '옵션명' : self.option_name, #str / name1(str)-name2(str)
                    #     '옵션 가격' : self.option_prices, #array / value1(str)-value2(str)
                    #     '옵션 항목' : self.option_values, #array / value1(str)-value2(str)
                    #     '옵션 이미지' : self.option_images, #array / str
                    #     '업로드 사업자' : self.upload_account, #str
                    #     '시즌성여부' : self.is_season_pd, #boolen
                    # }
                    # if len(self.product_images) > 1:
                    #     del self.product_images[1]
                    #     arg_data['추가이미지'] = self.product_images #array
                    # else:
                    #     arg_data['추가이미지'] = []
                    
                    # n = self.generate_code(12)
                    # product_manage_code = f'AE_{n}'
                    
                    # arg_data['고유상품코드'] = product_manage_code
                    # arg_data['상품상세'] = brotli.compress(self.detail.encode())

                    # self.db['pd_data'].insert_one(arg_data)

                    self.gui.update_console_subthread(f'수집 완료 되었습니다 : {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
         
                    with lock:
                        succeed_task +=1

                except Exception as error:
                    with lock:
                        self.gui.update_console_subthread(f'수집에 실패했습니다 : {error} {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                        
                        failed_task += 1
                        logging.exception(f'에러 발생! {self.product_url[num]}, {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}')
                
                finally:
                    with lock:
                        total_task = succeed_task + failed_task + prohibit_task
                        self.gui.update_count_subthread()
                        self.gui.update_console_subthread(f'전체 : {total_task}, 성공 : {succeed_task}, 실패 : {failed_task}, 금지 : {prohibit_task}')

            #한 페이지가 끝날 때마다 재작성  
            self.rewrite_restart_point(self.load_file_name, PageA, linkcount, lock)
        self.gui.is_done_queue.put(True)

class GUI(AECollecter):
    def __init__(self, account, max_workers) -> None:
        
        self.account = account
        self.max_workers = max_workers
        self.text_queue = queue.Queue()
        self.retry_linkcount_queue = queue.Queue()
        self.future_queue = queue.Queue()
        self.is_done_queue = queue.Queue()

        self.main_window_info()
        super().__init__(self, account)

        self.cookie_alert()
        self.cookie_window_info()

    def exit(self):
        os.kill(os.getpid(), signal.SIGTERM)

    def paste(self, event):
        try:
            clipboard_content = self.input_cookie.clipboard_get()
            # 클립보드 내용을 검사하고, 필요한 경우 수정하거나 특정 조건을 적용
            # 예: 특정 형식에 맞지 않는 내용을 걸러내거나 변형
            # 그 후, 텍스트 위젯에 내용을 삽입
            self.input_cookie.insert(INSERT, clipboard_content)
        except TclError:
            # 클립보드에 텍스트가 없는 경우 처리
            pass
        return "break" # 기본 붙여넣기 동작을 방지
    
    def cookie_alert(self):
        messagebox.showinfo('주의', '정확한 쿠키 미입력 시 이벤트 가격으로 수집됩니다. 꼭 정확한 쿠키 입력 부탁드립니다')

    def cookie_window_info(self):

        self.cookie_window = Toplevel()
        self.cookie_window.title(self.account + ' 알리익스프레스 쿠키 입력')
        self.cookie_window.geometry('300x300')

        self.input_cookie = Text(self.cookie_window, width=40, height=15)
        self.input_cookie.pack(pady=10)
        self.input_cookie.bind("<Command-v>", self.paste)


        self.button = ttk.Button(self.cookie_window, text="확인", command=self.button_clicked)
        self.is_clicked = BooleanVar(self.cookie_window, False)  # 버튼 클릭 상태를 저장할 변수
        self.button.pack()

        self.cookie_window.protocol('WM_DELETE_WINDOW', self.exit)

        self.button.wait_variable(self.is_clicked)
        self.is_clicked.set(False)


        self.switch_to_main()

    def check_is_all_done(self):
        if self.is_done_queue.qsize() == max_workers:
            self.update_console_subthread('상품 수집이 모두 완료되었습니다 !')
        else:
            self.tk.after(100, self.check_is_all_done)

    def button_clicked(self):
        self.is_clicked.set(True)

    def main_window_info(self):
        self.tk = Tk()
        self.tk.title(self.account + ' 알리익스프레스 수집 진행상황')

        frame1 = ttk.Frame(self.tk)
        frame1.pack(side='left')

        frame2 = ttk.Frame(self.tk)
        frame2.pack()

        self.label_text1 = StringVar()
        self.label_text1.set("전체 : 0")
        self.label1 = Label(frame1, textvariable=self.label_text1)
        self.label1.pack(padx=12, pady=6)

        self.label_text2 = StringVar()
        self.label_text2.set("성공 : 0")
        self.label2 = Label(frame1, textvariable=self.label_text2)
        self.label2.pack(padx=12, pady=6)

        self.label_text3 = StringVar()
        self.label_text3.set("실패 : 0")
        self.label3 = Label(frame1, textvariable=self.label_text3)
        self.label3.pack(padx=12, pady=6)

        self.label_text4 = StringVar()
        self.label_text4.set("금지 : 0")
        self.label4 = Label(frame1, textvariable=self.label_text4)
        self.label4.pack(padx=12, pady=6)
        
        self.console = ScrolledText(frame2, height=14, width=60)
        self.console.pack()

        self.tk.bind('<<update_count>>', self.update_count)
        self.tk.bind('<<update_console>>', self.update_console)
        self.tk.bind('<<reset_cookie>>', self.reset_cookie)

        self.tk.protocol('WM_DELETE_WINDOW', self.exit)

    def switch_to_main(self):
        self.cookie = self.input_cookie.get("1.0", "end-1c")
        self.cookie_window.withdraw()

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)

        for linkcount in range(len(self.pagelink)):
            future = executor.submit(self.execute_AECollector, linkcount, self.cookie)
            self.future_queue.put(future)

        executor.shutdown(wait=False)
        
    def get_new_cookie(self):
        self.cookie = self.input_cookie.get("1.0", "end-1c")
        self.cookie_window.withdraw()
        linkcount = self.retry_linkcount_queue.get()
        
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)

        for linkcount in range(linkcount, len(self.pagelink)):
            future = executor.submit(self.execute_AECollector, linkcount, self.cookie)
            self.future_queue.put(future)

        executor.shutdown(wait=False)

    def execute_AECollector(self, linkcount, cookie):
        AECollecter(self, self.account).run(linkcount, cookie)

    def update_count(self, e):
        self.label_text1.set('전체 : ' + str(total_task))
        self.label_text2.set('성공 : ' + str(succeed_task))
        self.label_text3.set('실패 : ' + str(failed_task))
        self.label_text4.set('금지 : ' + str(prohibit_task))
    
    def update_console(self, e):
        text = self.text_queue.get()
        self.console.insert('1.0', text+'\n')

    def reset_cookie(self, e):
        self.cookie_window.deiconify()
        self.button.wait_variable(self.is_clicked)
        self.is_clicked.set(False)
        self.get_new_cookie()

    def update_count_subthread(self):
        self.tk.event_generate("<<update_count>>", when="tail")

    def update_console_subthread(self, text):
        self.text_queue.put(text)
        self.tk.event_generate('<<update_console>>', when='tail')

    def reset_cookie_subthread(self, linkcount):
        self.retry_linkcount_queue.put(linkcount)
        
        with lock:
            while not self.future_queue.empty():
                future = self.future_queue.get()
                future.cancel()
        self.tk.event_generate('<<reset_cookie>>', when='tail')


if __name__ == '__main__':
    
    # account = args.account
    account = '<사업자 상호명>'
    max_workers = args.threads

    logging.basicConfig(filename=f'datas/logging/AECollector_debug.log', level=logging.INFO, force=True)

    GUI(account, max_workers).tk.mainloop()
