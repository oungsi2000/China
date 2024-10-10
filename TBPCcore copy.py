import requests
import json
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import threading
from seleniumwire import webdriver as proxydriver
import gzip
import re
from urllib.parse import quote, unquote
import random
from bs4 import BeautifulSoup
import concurrent.futures
import logging
import traceback
from lxml import etree
from Proxycrawl.Proxycrawl import Proxycrawl
import html

lock = threading.Lock()
logging.basicConfig(filename=f'datas/logging/TBcore.log', level=logging.INFO, force=True)
p = Proxycrawl(UseSelenium=False)

class WebDriverPool:
    def __init__(self) -> None:
        self.driver_path = '/Users/jung-yongjun/Desktop/china/chromedriver-mac-arm64/chromedriver'
        with open('Proxycrawl/ProxyServer.txt', 'r') as file:
            self.proxies = file.readlines()

        self.proxyDriverPool = []
        self._proxyDriverPool = []

        self.options = Options()
        # prefs = {"profile.managed_default_content_settings.images": 2}

        # self.options.add_experimental_option('prefs', prefs)
        # self.options.add_argument("--headless")
        self.options.add_argument("--disable-blink-features=AutomationControlled")
        self.options.add_argument('--ignore-certificate-errors')

        threads = []
        for _ in range(5):
            t = threading.Thread(target=self.put_new_driver)
            t.start()
            threads.append(t)

        for thread in threads:
            thread.join()

    
    def put_new_driver(self):
        proxy = random.choice(self.proxies).strip()
        wire_option = {
        'proxy': {
                'http': 'http://' + proxy,
                'https': 'https://' + proxy,
                'no_proxy': 'localhost,127.0.0.1' # 프록시를 사용하지 않을 호스트를 지정
            },
        }
        pdriver = proxydriver.Chrome(service=Service(executable_path=self.driver_path), options=self.options, seleniumwire_options=wire_option)
        with lock:
            self.proxyDriverPool.append(pdriver)    
            self._proxyDriverPool.append(pdriver)

class Processor:
    def __init__(self, WebDriverPool:WebDriverPool):
        
        self.wd = WebDriverPool
        self.get_new_driver()

    def get_new_driver(self):
        with lock:
            try:
                self.pdriver.quit()
                self.wd._proxyDriverPool.pop(0)
            except AttributeError:
                pass
            
        try:
            with lock:
                self.pdriver = self.wd.proxyDriverPool[0]
                self.wd.proxyDriverPool.pop(0)
        except IndexError:
            threads = []
            for _ in range(3):
                t = threading.Thread(target=self.wd.put_new_driver)
                t.start()
                threads.append(t)

            for thread in threads:
                thread.join()
            with lock:
                self.pdriver = self.wd.proxyDriverPool[0]
                self.wd.proxyDriverPool.pop(0)

    def translate(self, string):
        string = quote(string)
        headers = {
            'Content-Type' : 'application/x-www-form-urlencoded;charset=UTF-8',
            'Accept-Language' : 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7,ja;q=0.6,zh-CN;q=0.5,zh;q=0.4'
        }

        data = f"async=translate,sl:zh-CN,tl:ko,st:{string},id:1703690763361,qc:true,ac:false,_id:tw-async-translate,_pms:s,_fmt:pc"

        res = p.collect_requests('https://www.google.com/async/translate?vet=12ahUKEwjevtXM9q-DAxXOqFYBHXGaBHcQqDh6BAgFEDA..i&ei=90GMZZ7nKM7R2roP8bSSuAc&opi=89978449&yv=3&cs=0', data=data, headers=headers, method='post')
        soup = BeautifulSoup(res.text, 'html.parser')
        return soup.select('#tw-answ-target-text')[0].text

    def change_webelement(self, text, element):
        translated = self.translate(text)
        element.text = translated

    def get_product_name(self):
        self.product_name = self.translate(self.data['data']['item']['title'])
    
    def get_detail(self):
        desc_link = self.data['data']['item']['taobaoDescUrl']
        self.pdriver.get('https:'+desc_link)
        self.pdriver.implicitly_wait(1)

        request_list = []
        for i in range(len(self.wd._proxyDriverPool)):
            request_list += self.wd._proxyDriverPool[i].requests
        request_list += self.pdriver.requests

        detail = '<div class="detailmodule_html">'
        for request in request_list:
            if 'h5api.m.taobao.com/h5/mtop.taobao.detail.getdesc' in request.url:
                if self.id in unquote(request.url.split('data=')[1]):
                    body = request.response.body
                    try:
                        body = gzip.decompress(body)
                    except:
                        pass

                    pattern = r'mtopjsonp1\((.*)\)'
                    e = re.search(pattern, body.decode(), re.DOTALL)
                    data = json.loads(e.group(1))
                    
                    if '6.0' in request.url:
                        page = data['data']['wdescContent']['pages']
                        for element in page:
                            if '<txt>' in element:
                                txt = element.split('<txt>')[1].split('</txt>')[0] + '\n'
                                detail += '<p>' + txt + '</p>'
                            if '<img' in element:
                                img = element.split('//')[1].split('</img>')[0] + '\n'

                                if 'size=' in element:
                                    size = element.split('size=')[1].split('>')[0]
                                    w = size.split('x')[0]
                                    h = size.split('x')[0]
                                    detail += f'<img style="width:{w}; height:{h};" src="https://' + img + '">'
                                else:
                                    detail += f'<img src="https://' + img + '">'

                    elif '7.0' in request.url:
                        idlist = []
                        page = data['data']['components']['layout']
                        idlist = [p['ID'] for p in page if 'desc_charity' not in p['ID']]
                        
                        componentData = data['data']['components']['componentData']

                        for id in idlist:
                            try:
                                img = componentData[id]['model']['picUrl']
                                h = componentData[id]['styles']['size']['height']
                                w = componentData[id]['styles']['size']['width']
                                detail += f'<img style="width:{w}px; height:{h}px;" src=' + img + '>\n'
                            except KeyError:
                                try:
                                    text = componentData[id]['model']['text']
                                    detail += '<p>' + text + '</p>'
                                except KeyError:
                                    pass

        detail += '</div>'
        tree = etree.HTML(detail)
        elements = tree.xpath('//*[not(child::*)]')
        tasks = []
        for element in elements:
            text = element.text
            if text != None:
                t = threading.Thread(target=self.change_webelement, args=(text, element))
                t.start()
                tasks.append(t)

        for task in tasks:
            task.join()
        
        detail = etree.tostring(tree).decode('utf-8')
        detail = html.unescape(detail)
        self.detail = str(BeautifulSoup(detail, 'html.parser').select_one('.detailmodule_html'))

    def translate_option_value(self, opt_value):
        
        translated = self.translate(opt_value)
        with lock:
            self.new_opt_values[opt_value] = translated

    def translate_option_values(self):
        self.new_opt_values = {}
        tasks = []
        for opt_value in self.opt_values:
            self.new_opt_values[opt_value] = ''
            t = threading.Thread(target=self.translate_option_value, args=(opt_value, ))
            t.start()
            tasks.append(t)

        for task in tasks:
            task.join()

        return list(self.new_opt_values.values())
    
    def get_option_value(self, idx=1):
        
        if idx==1:
            self.opt_title = ''
            self.opt_values = []
            self.opt_prices = []
            self.opt_imgs = []


        if self.mockData['feature'].__len__() == 0:
            return self.opt_title, self.opt_values, self.opt_prices, self.opt_imgs

        opt_datas = self.data['data']['skuBase']['props']

        if len(opt_datas) > 2:
            self.is_3options = True
            return self.opt_title, self.opt_values, self.opt_prices, self.opt_imgs
        
        #옵션명
        if self.opt_title != '' and '-' not in self.opt_title:
            self.opt_title += '-'
        
        if opt_datas[idx-1]['name'] not in self.opt_title:
            self.opt_title += opt_datas[idx-1]['name']
        
        if idx == 1:
            self.pid1 = opt_datas[idx-1]['pid']

        if idx == 2:
            self.pid2 = opt_datas[idx-1]['pid']

        #옵션 항목
        for inner_value in opt_datas[idx-1]['values']:
            
            if idx == 1:
                try:
                    self.vid1 = inner_value['vid']
                    self.value1 = inner_value['name']
                    self.img = 'https:'+inner_value['image']
                    
                except KeyError:
                    self.img = "None"
            if idx == 2:
                try:
                    self.vid2 = inner_value['vid']
                    self.value2 = inner_value['name']
                    self.img = 'https:'+inner_value['image']
                except KeyError:
                    pass

            if idx != len(opt_datas):
                self.get_option_value(idx=idx+1)
            
            try: #옵션개수 2개
                self.opt_values.append(self.value1 + '-' + self.value2)
                self.opt_imgs.append(self.img)
                
                for i in self.data['data']['skuBase']['skus']:
                    if self.pid1+':' + self.vid1+';'+self.pid2+':'+self.vid2 == i['propPath']:
                        price = self.mockData['skuCore']['sku2info'][i['skuId']]['price']['priceText']
                        price = float(price)*190
                        self.opt_prices.append(str(price))

            except AttributeError: #옵션개수 1개
                self.opt_values.append(self.value1)
                self.opt_imgs.append(self.img)

                for i in self.data['data']['skuBase']['skus']:
                    if self.pid1+':'+self.vid1 == i['propPath']:
                        price = self.apistack['skuCore']['sku2info'][i['skuId']]['price']['priceText']
                        price = float(price)*190
                        self.opt_prices.append(str(price))

        self.opt_values = self.translate_option_values()

        v = []
        for item in self.opt_title.split('-'):
            v.append(self.translate(item))
        self.opt_title = '-'.join(v)
        
    def get_price(self):
        price = float(self.apistack['price']['price']['priceText'].split('-')[0])*190
        self.product_price = str(price)
    
    def get_image(self):
        
        img_list = []
        imgs = self.data['data']['item']['images']
        for img in imgs:
            img = 'https:' + img
            img_list.append(img)
        self.pd_img = img_list

    def translate_pd_info(self, keys, values):
        new_key = self.translate(keys)
        new_value = self.translate(values)
        with lock:
            self.pd_info.append({
                'attrName' : new_key,
                'attrValue' : new_value
            })

    def get_pd_info(self):
        self.pd_info = [
        ]
        tasks = []
        pd_info = self.data['data']['props']['groupProps'][0]['基本信息']

        for pd in pd_info:
            keys = list(pd.keys())[0]
            values = list(pd.values())[0]
            t = threading.Thread(target=self.translate_pd_info, args=(keys, values))
            t.start()
            tasks.append(t)
        
        for task in tasks:
            task.join()
        
        return self.pd_info
    
    def restart(self):
        t = threading.Thread(target=self.wd.put_new_driver)
        t.start()
        self.get_new_driver()
        data = self.collect(self.link)

        t.join()
        return data
    
    def collect(self, link):
        try:
            self.link = link
            print(link)

            self.is_3options = False
            self.is_bad_seller = False

            try:
                self.pdriver.get(self.link)

            except:
                self.restart()
            
            for _ in range(30):
                try:
                    self.pdriver.find_element(By.CSS_SELECTOR, 'body > div.J_MIDDLEWARE_FRAME_WIDGET > img').click()
                except:
                    try:
                        self.pdriver.find_element(By.CSS_SELECTOR, 'body > div:nth-child(14) > img').click()
                    except:
                        pass
            
            time.sleep(2)
            request_list = []
            for i in range(len(self.wd._proxyDriverPool)):
                request_list += self.wd._proxyDriverPool[i].requests
            request_list += self.pdriver.requests

            for request in request_list:
                if 'h5api.m.tmall.com/h5/mtop.taobao.pcdetail.data.get'in request.url and request.response != None:
                    self.id = self.link.split('&id=')[1].split('&')[0]
                    if self.id in unquote(request.url.split('data=')[1]):
                        try:
                            body = request.response.body
                            body = gzip.decompress(body)
                            pattern = r'mtopjsonp1\((.*)\)'
                            e = re.search(pattern, body.decode(),re.DOTALL)
                            self.data = json.loads(e.group(1))
                            self.mockData = json.loads(self.data['data']['mockData'])
                            self.apistack = json.loads(self.data['data']['apiStack'][0]['value'])
                            break
                        except:
                            pass

            try:
                self.apistack
            except AttributeError:
                self.restart()
            
            st = time.time()
            tasks = []


            #1. 상품명 
            t = threading.Thread(target=self.get_product_name)
            t.start()
            tasks.append(t)

            #2. 상품상세
            t = threading.Thread(target=self.get_detail)
            t.start()
            tasks.append(t)

            #3. 옵션
            t = threading.Thread(target=self.get_option_value)
            t.start()
            tasks.append(t)

            #4. 상품정보고시
            t = threading.Thread(target=self.get_pd_info)
            t.start()
            tasks.append(t)

            #---------
            #판매자 필터
            if int(self.data['data']['seller']['creditLevel']) < 10:
                self.is_bad_seller = True
            for eval in self.data['data']['seller']['evaluates']:
                if float(eval['score']) < 4.6:
                    self.is_bad_seller = True
        
            #5. 가격
            t = threading.Thread(target=self.get_price)
            t.start()
            tasks.append(t)

            #6. 상품이미지 
            t = threading.Thread(target=self.get_image)
            t.start()
            tasks.append(t)
            
            for task in tasks:
                task.join()

            dataframe = {
                'request' : 'success',
                'data' : {
                    'link' : self.link,
                    'product_name' : self.product_name,
                    'detail' : self.detail,
                    'opt_title' : self.opt_title,
                    'opt_values' : self.opt_values,
                    'opt_prices' : self.opt_prices,
                    'opt_imgs' : self.opt_imgs,
                    'product_info' : self.pd_info,
                    'product_price' : self.product_price,
                    'product_images' : self.pd_img
                }
            }

            #요청 초기화
            del self.pdriver.requests[:]
            for i in range(len(self.wd.proxyDriverPool)):
                del self.wd.proxyDriverPool[i].requests
            
            #반환
            if self.is_bad_seller:
                return {
                    'request' : 'failed', 
                    'data' : 'ㅂㅅ판매자입니다'
                }
            elif self.is_3options:
                return {
                    'request' : 'failed', 
                    'data' : '3개 이상의 옵션은 지원되지 않습니다'
                }
            print(st - time.time())

            return dataframe
        
        except:
            logging.exception('에렁')
            traceback.print_exc()

            return {
                'request' : 'failed', 
                'data' : '시스템 오류'
            }
            
links = ['https://detail.tmall.com/item.htm?abbucket=6&id=617335418040&ns=1&spm=a21n57.1.0.0.14d2523ctpkRyT',
        ]


if __name__ == '__main__':
    wb = WebDriverPool()
    r3 = Processor(wb)

    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as exe:
        for link in links:
            future = exe.submit(r3.collect, link)
            futures.append(future)

    for future in futures:
        print(future.result())