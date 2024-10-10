
import js2py
import requests
from bs4 import BeautifulSoup

for _ in range(5):
    res = requests.get('''
https://www.aliexpress.com/w/wholesale-.html?&sortType=total_tranpro_desc&maxPrice=100000&SearchText=자동차 카메라
''')

    soup = BeautifulSoup(res.content, 'html.parser')
    e = soup.select('.search-card-item')
    f = soup.select('.lazy-load')

    count = len(e) + len(f)
    if count != 0:
        break

scripts = soup.select('script')
product_url = []

#상품 정보를 담고 있는 js실행
for script in scripts :
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
            product_url.append('https://ko.aliexpress.com/item/'+code['productId']+'.html?')
            print('https://ko.aliexpress.com/item/'+code['productId']+'.html?')
            print(code['title']['displayTitle'])
        break

print(len(product_url))       