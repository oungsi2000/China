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
import os

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
        self.options.add_argument("--headless")
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
            for _ in range(2):
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
        try:
            desc_link = self.data['data']['item']['taobaoDescUrl']
            self.pdriver.get('https:'+desc_link)
            self.pdriver.implicitly_wait(1)
        except:
            self.restart()

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
                        price = self.apistack['skuCore']['sku2info'][i['skuId']]['price']['priceText']
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
            
            self.id = self.link.split('&id=')[1].split('&')[0]
            target = 'https://h5api.m.taobao.com/h5/mtop.taobao.detail.getdetail/6.0/?jsv=2.7.2&appKey=12574478&t=1704163073737&sign=333711df5deb39a141ccea69aaeb5915&api=mtop.taobao.detail.getdetail&v=6.0&ttid=2017%40htao_h5_1.0.0&preventFallback=true&type=jsonp&dataType=jsonp&smToken=token&queryToken=sm&sm=sm&callback=mtopjsonp4&data=%7B%22exParams%22%3A%22%7B%5C%22countryCode%5C%22%3A%5C%22KR%5C%22%2C%5C%22channel%5C%22%3A%5C%22oversea_seo%5C%22%7D%22%2C%22channel%22%3A%22oversea_seo%22%2C%22itemNumId%22%3A%22677048284641%22%7D'.replace('677048284641', self.id)
                     
            headers = {
                'Referer' : 'https://m.intl.taobao.com/',
                'User-Agent' : 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                'Cookie' : '_samesite_flag_=true; cookie2=1fd501b35eec2efa8fe451f3ad25dc9e; t=6d6f7d2bdc470278fba6e6d252f09c1d; thw=cn; WAPFDFDTGFG=%2B4cMKKP%2B8PI%2BKK8fr%2Fcw3WtT9jubOai29w%3D%3D; _w_app_lg=0; useNativeIM=false; wwUserTip=false; linezing_session=6lXwD0G9BqeWtE3iongAAfXy_1703675064561WyY0_2; ariaDefaultTheme=default; ariaFixed=true; ockeqeudmj=j%2F13Ixw%3D; x=e%3D1%26p%3D*%26s%3D0%26c%3D0%26f%3D0%26g%3D0%26t%3D0; hng=KR%7Czh-CN%7CKRW%7C410; xlly_s=1; ariaBigsrc=true; ariaScale=1; ariaReadtype=1; ariaoldFixedStatus=false; ariaStatus=false; _tb_token_=1b0a3ef335f3; _m_h5_tk=a0b8f65df88981e5588e5ca358534131_1704181415416; _m_h5_tk_enc=12cdecda8b77a41e0b842e7e40361092; mt=ci=0_0; cna=JiCcHUa74xUCAXfBH2SonNhU; sgcookie=E1002do6%2B4uajkFNawGhiBYBzhYXpuq0g4OnHs6FoR3hTG1uF5NLqrYLUQQRj0UeFfsOMAlMJdqxDckOozQcMGT5fCk1byh%2FDs2BzDz75dU66Vg%3D; unb=2217145293020; uc3=id2=UUpgQcOkRk%2Flt%2FRxzA%3D%3D&lg2=WqG3DMC9VAQiUQ%3D%3D&nk2=F5RDK1TFqqBCUweusVs%3D&vt3=F8dD3Cbzb2T8PQ9Kh98%3D; csg=49ab7699; lgc=tb677937849087; cancelledSubSites=empty; cookie17=UUpgQcOkRk%2Flt%2FRxzA%3D%3D; dnk=tb677937849087; skt=8554f5828b30fe7a; existShop=MTcwNDE3NTUwOA%3D%3D; uc4=nk4=0%40FY4I6FcqAh4ZkBcz4EHN56P9mz%2FwRQfpZg%3D%3D&id4=0%40U2gqztqJTKskOEK5s3RxDF8bPoxs3Zow; tracknick=tb677937849087; _cc_=W5iHLLyFfA%3D%3D; _l_g_=Ug%3D%3D; sg=709; _nk_=tb677937849087; cookie1=VFdi5%2Bs5QbJmZ7rbr42HlFEfce%2Bcyp%2BE5HZmZ4rOpcs%3D; uc1=pas=0&cookie16=URm48syIJ1yk0MX2J7mAAEhTuw%3D%3D&cookie14=UoYekRdflg7sKA%3D%3D&cookie15=Vq8l%2BKCLz3%2F65A%3D%3D&cookie21=VT5L2FSpdiBh&existShop=false; _uetsid=a3af5040a88c11ee958e495f76004653; _uetvid=cfe1cf005dd411eeab05974d43170b95; l=fBSwt7AVPwieL4cOBOfZPurza779sIRxmuPzaNbMi9fPOSfe5PPVW1Bm8E8wCnHNF6yBR3yI_B6WBeYBc_C-nxv9rNWQtWkmnmOk-Wf..; tfstk=eInJhHbEbKB8YS5ao3LDLOS9K_9Ds0Hyqbk1xWVlRjhxCjy3xBkQdkhjtLPodQlKvSZ784V3ZWEKLfpDshxiUYrUVCAMjupY24rI9b5uRYkzYtWcOF0jUMLBMoIE-BTGuCjntc2WWs9DuOrJ_fU81xtVAMFfjzNsFSIBtmeRO5M7MMsC4biiX-CVs5ehPKpA8wz73rHL7F3O8eNzH5v0Ew7UkEyYsKpA8wz73-FMn8bF8rLV.; isg=BKOjlqDlwhnSKo7HFxD5_NfxMuFNmDfa55Aaj9UA_4J5FMM2XWjHKoFNC_oan4_S'
            }
            while True:
                res = p.collect_requests(target, headers=headers)
                try:
                    pattern = r'mtopjsonp4\((.*)\)'
                    e = re.search(pattern, res.text ,re.DOTALL)
                    self.data = json.loads(e.group(1))
                    self.mockData = json.loads(self.data['data']['mockData'])
                    self.apistack = json.loads(self.data['data']['apiStack'][0]['value'])
                    break
                    
                except:
                    print('타오바오 동결')
                    os.system('pkill -f python')

                        
            
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
            
links = ['https://detail.tmall.com/item.htm?abbucket=6&id=684162226561&ns=1&spm=a21n57.1.0.0.14d2523ctpkRyT',
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