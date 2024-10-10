import random
import http.client
from Proxycrawl.Proxycrawl import Proxycrawl
from http.cookies import SimpleCookie
import json
import sys
import jwt
from datetime import datetime, timedelta
import requests
import traceback

p = Proxycrawl(UseSelenium=False)
sellerid = 'twobase14'
sellerpw = '!Password1!'
bus_account = '투베이스14'

def refresh_token_ESM():
    try:
        headers = {
        'Content-Type' : 'application/x-www-form-urlencoded', 
        'User-Agent' : random.choice(p.USER_AGENTS),
        }
        
        data = f'Password={sellerpw}&Type=S&ReturnUrl=&SiteType=GMKT&Id={sellerid}&RememberMe=false'
        
        conn = http.client.HTTPSConnection('www.esmplus.com')

        res = p.collect_requests('https://www.esmplus.com/SignIn/Authenticate', headers=headers, data=data, method='post')
        conn.request("POST", "/SignIn/Authenticate", headers=headers, body=data)

        response = conn.getresponse()

        print("Status:", response.status, response.reason)

        headers = response.getheaders()

        cookies_dict = {}
        for header in headers:
            if 'Set-Cookie' in header:
                cookie = SimpleCookie(header[1])
                for key, morsel in cookie.items():
                    cookies_dict[key] = morsel.value

        cookies_dict['ESM_REQUEST_AUTH_PC'] = res.cookies['ESM_REQUEST_AUTH_PC']

        with open(f'datas/Auth/ESM_AUTH_{bus_account}.json', 'w', encoding='utf-8') as file:
            json.dump(cookies_dict, file, ensure_ascii=False, indent=4)

        return cookies_dict
    
    except:
        print('계정정보 오류')
        traceback.print_exc()
        sys.exit()

def resell_AC():
    for _ in range(15):
        try:
            with open(f'datas/Auth/ESM_AUTH_{bus_account}.json', 'r', encoding='utf-8') as file:
                cookies_dict = json.load(file)
        except:
            cookies_dict = refresh_token_ESM()

        decoded_token = jwt.decode(cookies_dict['ESM_TOKEN'], algorithms='HS512', options={"verify_signature": False})
        exp = decoded_token['iat']
        expiration_date = datetime.fromtimestamp(exp) + timedelta(hours=2)

        if datetime.utcnow() + timedelta(hours=9) > expiration_date:
            cookies_dict = refresh_token_ESM()
        
        headers = {
            'Content-Type' : 'application/x-www-form-urlencoded; charset=UTF-8',
            'Referer' : 'https://www.esmplus.com/Sell/Items/ItemsMng?menuCode=TDM100'
        }

        data = 'paramsData={"Keyword":"","SiteId":"1","SellType":0,"CategoryCode":"","CustCategoryCode":0,"TransPolicyNo":0,"StatusCode":"21","SearchDateType":0,"StartDate":"","EndDate":"","SellerId":"","StockQty":-1,"SellPeriod":0,"DeliveryFeeApplyType":0,"OptAddDeliveryType":0,"SellMinPrice":0,"SellMaxPrice":0,"OptSelUseIs":-1,"PremiumEnd":0,"PremiumPlusEnd":0,"FocusEnd":0,"FocusPlusEnd":0,"GoodsIds":"","SellMngCode":"","OrderByType":6,"NotiItemReg":-1,"EpinMatch":-1,"UserEvaluate":"","ShopCateReg":-1,"IsTPLUse":"","GoodsName":"","SdBrandId":0,"SdBrandName":"","IsGiftUse":""}&page=1&start=0&limit=500'
        res = requests.post('https://www.esmplus.com/Sell/Items/GetItemMngList?_dc=1697436810143', cookies=cookies_dict, data=data, headers=headers)

        pd_data = res.json()['data']

        headers = {
            'Content-Type' : 'application/json;charset=UTF-8',
            'Accept-Encoding' : 'gzip, deflate, br, zstd',
            'Accept' : 'application/json, text/javascript, */*; q=0.01',
            'Referer' : 'https://www.esmplus.com/Sell/Popup/ModifyResult'
        }
        data = {
            'data' : [],
            'period':'90'
        }

        for element in pd_data:
            data['data'].append(
                {
                    'SiteId' : '1',
                    'SiteGoodsNo' : element['SiteGoodsNo'],
                    'SellerCustNo' : element['SellerCustNo'],
                    'SellerId' : element['SellerId'],
                    'GoodsNo' : element['GoodsNo'],
                    'SellType' : element['SellType'],
                    'ItemName' : element['GoodsName'],
                    'SellPrice' : element['SellPrice'],
                    'StockQty' : element['StockQty'],
                    'DispEndDate' : element['DispEndDate'],
                    'ItemSiteType' : element['SellType'],
                    "IacBusinessSellerIs":True,
                    "GmktBusinessSellerIs":True,
                    "IsOneSeller":1,
                    "SiteCategoryCode":"03870700",
                    "DistrType":"NL",
                    "DisplayLimitYn":"N"
                }
            )
        data = json.dumps(data)
        res = requests.post('https://www.esmplus.com/Sell/Popup/SetPeriodExtend', headers=headers, cookies=cookies_dict, data=data)
        print(res.text)

def resell_GMKT():
    for _ in range(300):
        try:
            with open(f'datas/Auth/ESM_AUTH_{bus_account}.json', 'r', encoding='utf-8') as file:
                cookies_dict = json.load(file)
        except:
            cookies_dict = refresh_token_ESM()

        decoded_token = jwt.decode(cookies_dict['ESM_TOKEN'], algorithms='HS512', options={"verify_signature": False})
        exp = decoded_token['iat']
        expiration_date = datetime.fromtimestamp(exp) + timedelta(hours=2)

        if datetime.utcnow() + timedelta(hours=9) > expiration_date:
            cookies_dict = refresh_token_ESM()
        
        headers = {
            'Content-Type' : 'application/x-www-form-urlencoded; charset=UTF-8',
            'Referer' : 'https://www.esmplus.com/Sell/Items/ItemsMng?menuCode=TDM100'
        }

        data = 'paramsData={"Keyword":"","SiteId":"2","SellType":0,"CategoryCode":"","CustCategoryCode":0,"TransPolicyNo":0,"StatusCode":"21","SearchDateType":0,"StartDate":"","EndDate":"","SellerId":"","StockQty":-1,"SellPeriod":0,"DeliveryFeeApplyType":0,"OptAddDeliveryType":0,"SellMinPrice":0,"SellMaxPrice":0,"OptSelUseIs":-1,"PremiumEnd":0,"PremiumPlusEnd":0,"FocusEnd":0,"FocusPlusEnd":0,"GoodsIds":"","SellMngCode":"","OrderByType":6,"NotiItemReg":-1,"EpinMatch":-1,"UserEvaluate":"","ShopCateReg":-1,"IsTPLUse":"","GoodsName":"","SdBrandId":0,"SdBrandName":"","IsGiftUse":""}&page=1&start=0&limit=20'
        res = requests.post('https://www.esmplus.com/Sell/Items/GetItemMngList?_dc=1697436810143', cookies=cookies_dict, data=data, headers=headers)

        pd_data = res.json()['data']

        sellMoney = 0
        for num in pd_data:
            sellMoney += int(num['SellPrice'])
        
        sellMoney = int(sellMoney / 20)
        headers = {
            'Content-Type' : 'application/json;charset=UTF-8',
            'Accept-Encoding' : 'gzip, deflate, br, zstd',
            'Accept' : 'application/json, text/javascript, */*; q=0.01',
            'Referer' : 'https://www.esmplus.com/Sell/Popup/ModifyResult'

        }
        data = {
            'data' : [],
            "sellMoney":sellMoney,
            "stockQty":"99999",
            "sellPeriod":"90"
        }

        for element in pd_data:
            data['data'].append(
                {
                    'SiteId' : '2',
                    'SiteGoodsNo' : element['SiteGoodsNo'],
                    'SellerCustNo' : element['SellerCustNo'],
                    'SellerId' : element['SellerId'],
                    'GoodsNo' : element['GoodsNo'],
                    'SellType' : element['SellType'],
                    'ItemName' : element['GoodsName'],
                    'SellPrice' : element['SellPrice'],
                    'StockQty' : element['StockQty'],
                    'DispEndDate' : element['DispEndDate'],
                    'ItemSiteType' : 2,
                    "IacBusinessSellerIs":True,
                    "GmktBusinessSellerIs":True,
                    "IsOneSeller":1,
                    "SiteCategoryCode":"03870700",
                    "DistrType":"NL",
                    "DisplayLimitYn":"N"
                }
            )
        data = json.dumps(data)
        res = requests.post('https://www.esmplus.com/Sell/Popup/SetGmarketOrderSetting', headers=headers, cookies=cookies_dict, data=data)
        print(res.text)

resell_AC()
resell_GMKT()