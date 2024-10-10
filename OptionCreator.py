from bs4 import BeautifulSoup
import sys
import json
import argparse
import traceback

parser = argparse.ArgumentParser(description="OptionCreator by twobasestore")

parser.add_argument('-l', '--list', nargs='+')

args = parser.parse_args()


img_list = json.loads(args.list[0])
option_texts = json.loads(args.list[1])
product_info = json.loads(args.list[2])


with open('datas/settings/OptionContainer.html', 'r') as file:
    option_container = file.read()

with open('datas/settings/OptionText.html', 'r') as file:
    option_text = file.read()

with open('datas/settings/OptionImg.html', 'r') as file:
    option_image = file.read()

with open('datas/settings/product_info.html', 'r') as file:
    product_info_html = file.read()

with open('datas/settings/product_info_title.html', 'r') as file:
    product_info_title = file.read()

with open('datas/settings/product_info_content.html', 'r') as file:
    product_info_content = file.read()

#상품 옵션 사진 만들기\

count = 0

for img, txt in zip(img_list, option_texts):
    if count % 2 == 0:
        soup = BeautifulSoup(option_container, 'html.parser')
        body = soup.select_one('tbody')
        
        tr_img = soup.new_tag('tr', class_='se-tr')
        tr_txt = soup.new_tag('tr', class_='se-tr')

    image = option_image.replace('src=""', f'src="{img}"')
    soup_image = BeautifulSoup(image, 'html.parser')
    tr_img.append(soup_image)

    text = option_text.replace('MYTEXT', txt)
    soup_text = BeautifulSoup(text, 'html.parser')
    tr_txt.append(soup_text)    
    
    if count % 2 == 0:
        body.append(tr_img)
        body.append(tr_txt)
    
    if count % 2 == 1 or (count == len(img_list) - 1):
        print(str(soup))

    count += 1


#상품정보고시 제작 알리 / 타오바오
soup = BeautifulSoup(product_info_html, 'html.parser')
body = soup.select_one('tbody')

for content in product_info:
    tr = soup.new_tag('tr', class_='se-tr')

    title = product_info_title.replace('write_title', content['attrName'])
    info = product_info_content.replace('write_content',content['attrValue'] )

    soup_title = BeautifulSoup(title, 'html.parser')
    soup_content = BeautifulSoup(info, 'html.parser')

    tr.append(soup_title)
    tr.append(soup_content)

    body.append(tr)

print(str(soup))


