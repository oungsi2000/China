import random
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
import os
from selenium.webdriver.chrome.service import Service as ChromeService
from lxml import html
import traceback


class Proxycrawl:
    def __init__(self, UseSelenium=True, Headless=False, ignore_loading=False):
        self.directory = os.path.dirname(os.path.abspath(__file__))
        
        print('유저 에이전트를 불러옵니다')
        with open(f'{self.directory}/UserAgent.txt', 'r') as file:
            self.USER_AGENTS = [line.strip() for line in file.readlines()]
        print('유저 에이전트 불러오기가 완료되었습니다')

        print('프록시 서버를 불러옵니다')
        with open(f'{self.directory}/ProxyServer.txt', 'r') as file:
            self.Proxy_Lists = [line.strip() for line in file.readlines()]
        print('프록시 서버 불러오기가 완료되었습니다')

        if UseSelenium:
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            chrome_options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
          
            if Headless:
                chrome_options.add_argument('--headless')
                self.headless = True
            if ignore_loading:
                chrome_options.page_load_strategy = "eager"
                self.ignore_loading = True
            service = ChromeService(executable_path='/Users/jung-yongjun/Downloads/chromedriver-mac-x64/chromedriver')

            self.driver = webdriver.Chrome(service=service,options=chrome_options)
        
            

    def collect_requests(self, link, headers=None, data=None, cookies=None, method='get'):
        
        while True:
            try:
                #모바일 유저 에이전트 거르기
                while True:
                    agent = random.choice(self.USER_AGENTS)
                    if 'mobile' not in agent.lower():
                        break
                header = {
                    'User-Agent' : agent

                }
                
                if headers != None:
                    header = headers
                    header['User-Agent'] = agent

                proxy = {
                    'http' : 'http://' + random.choice(self.Proxy_Lists),
                    'https' : 'http://' + random.choice(self.Proxy_Lists)
                }

                if method == 'get':
                    e = requests.get(link, headers=header, proxies=proxy, timeout=20, data=data, cookies=cookies)
                    self.soup = BeautifulSoup(e.text, 'html.parser')
                    self.tree = html.fromstring(e.content)
                    self.status_code = e.status_code
                    count = 0

                elif method == 'post':
                    e = requests.post(link, headers=header, proxies=proxy, timeout=20, data=data, cookies=cookies)
                    self.soup = BeautifulSoup(e.text, 'html.parser')
                    self.tree = html.fromstring(e.content)
                    self.status_code = e.status_code
                    count = 0

                else:
                    raise Exception('Invalid method')

                while e.status_code != 200 and count < 11:
                    agent = random.choice(self.USER_AGENTS)
                    header = {
                        'User-Agent' : agent
                    }
                    if headers != None:
                        header = headers
                        header['User-Agent'] = agent

                    proxy = {
                    'http' : 'http://' + random.choice(self.Proxy_Lists),
                    'https' : 'http://' + random.choice(self.Proxy_Lists)
                    }

                    if method == 'get':
                        e = requests.get(link, headers=header, proxies=proxy, timeout=30, data=data, cookies=cookies)
                        self.soup = BeautifulSoup(e.text, 'html.parser')
                        self.tree = html.fromstring(e.content)
                        self.status_code = e.status_code
                        count = 0

                    elif method == 'post':
                        e = requests.post(link, headers=header, proxies=proxy, timeout=30, data=data, cookies=cookies)
                        self.soup = BeautifulSoup(e.text, 'html.parser')
                        self.tree = html.fromstring(e.content)
                        self.status_code = e.status_code
                        count = 0

                if count == 10:
                    raise Exception('failed to connect using random proxy')
                break
 
            except Exception as e:
                pass
        return e


    def collect_selenium(self, link, use_requests=True):

        while True:
            try:
         
                header = {
                'User-Agent' : random.choice(self.USER_AGENTS)
                }

                proxy = {
                'http' : 'http://' + random.choice(self.Proxy_Lists),
                'https' : 'http://' + random.choice(self.Proxy_Lists)
                }
                
                e = 200
                if use_requests:
                    e = requests.get(link,headers=header, proxies=proxy, timeout=30).status_code
                    self.status_code = e

                proxy = random.choice(self.Proxy_Lists),

                webdriver.DesiredCapabilities.CHROME['proxy'] = {
                "httpProxy": str(proxy),
                "proxyType": "MANUAL"
                }
                
                self.driver.set_page_load_timeout(30)
                self.driver.get(link)
                
                count = 0
                while e !=200 and count < 11 :
                    self.driver.quit()
                
                    header = {
                    'User-Agent' : random.choice(self.USER_AGENTS)
                    }

                    proxy = {
                    'http' : 'http://' + random.choice(self.Proxy_Lists),
                    'https' : 'http://' + random.choice(self.Proxy_Lists)
                    }

                    e = 200
                    if use_requests:
                        e = requests.get(link, headers=header, proxies=proxy, timeout=30).status_code
                        self.status_code = e

                    proxy = random.choice(self.Proxy_Lists),

                  
                    chrome_options = webdriver.ChromeOptions()
                    chrome_options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

                    if self.headless:
                        chrome_options.add_argument('--headless')
                    if self.ignore_loading:
                        chrome_options.page_load_strategy = "eager"
        
                    service = ChromeService(executable_path='/Users/jung-yongjun/Downloads/chromedriver-mac-x64/chromedriver')

                    self.driver = webdriver.Chrome(service=service, options=chrome_options)

                    webdriver.DesiredCapabilities.CHROME['proxy'] = {
                    "httpProxy": str(proxy),
                    "proxyType": "MANUAL"
                    }

                    self.driver.set_page_load_timeout(30)
                    self.driver.get(link)
                    count += 1

                if count == 10:
                    raise Exception('failed to connect using random proxy')
                break
            except Exception as e:
                print(e)
                pass