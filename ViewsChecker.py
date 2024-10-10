import time
import concurrent.futures
import os
import os
import pandas as pd
import pymongo
import threading
import json
import datetime
import requests

client = pymongo.MongoClient('mongodb+srv://twobasestore:djawnstlr@twobasestore.znc2ay2.mongodb.net/')
db = client['twobasestore']
lock = threading.Lock()

direc = 'datas/logging/view_logs'
date = '2023-01-10'
st = time.time()
lock = threading.Lock()

def download_log(log):
    try:
        download_url = log.strip().replace('gs://', 'https://storage.googleapis.com/')
        res = requests.get(download_url)
        with open(direc+'/'+log.strip().replace('gs://logginggggg/', '')+'.csv' , 'wb') as file:
            file.write(res.content)
    except:
        pass

command = 'gsutil ls -l gs://logginggggg/ | awk \'$2 > "' + date + '" {print $3}\''
logging_list = os.popen(command).readlines()

futures = []
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as exe:
    for log in logging_list:
        future = exe.submit(download_log, log)
        futures.append(future)

for future in futures:
    future.result()

files = os.listdir(direc)
files = [file for file in files if 'storage' not in file]

command = 'head -n 1 ' + direc+'/'+files[0] + ' > '  + direc+'/'+'all_logs.csv'
os.system(command)
os.system(f'''
for file in {direc+'/twobasestore_usage'}*.csv
do
    tail -n +2 $file >> {direc+'/all_logs'}.csv
done
''')

#정렬

df = pd.read_csv(direc+'/all_logs.csv')
url = []
def run(img, id, idx):

    e = db['view'].find_one({'requestId' : id})
    if e == None:
        with lock:
            url.append(img)
    print(idx)

futures = []
st = time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(max_workers=50) as exe:
    for img, id, idx, method in zip(df['cs_uri'], df['s_request_id'], range(len(df['cs_uri'].to_list())), df['cs_method']):
        if method == 'GET':
            futures.append(exe.submit(run, img, id, idx))

print(time.perf_counter()-st)
e = db['_tracker'].find({ '$and' : [
        {'tracker' : {'$in' : url}},
    ]
})

for element in e:
    db['view'].update_one(
        {'id' : element['id'] },
        {
            '$inc' : {'views' : 1},
            '$set' : {
                'lastUpdate' : str(datetime.datetime.utcnow() + datetime.timedelta(hours=9)),
            },
            '$push' : {
                    'requestId' : id
            }
        },
        upsert=True
    )

data = db['view'].find({})

for i in data:
    id = i['id']
    d = db['complete_data'].find_one({'고유상품코드' : id})

    if d != None:
        link = d['상품링크']
        name = d['상품명']
        db['view'].update_one({'id' : id}, {'$set' : {'link' : link, 'name' : name}}, upsert=True)
    
    else:
        db['view'].update_one({'id' : id}, {'$set' : {'link' : '', 'name' : ''}})


for file in files:
    file_path = os.path.join(direc, file)
    os.unlink(file_path)

