const { app, BrowserWindow } = require('electron')
const { ipcMain } = require('electron');
const XLSX = require('xlsx')
const fs = require('fs')
const path = require('path');



function createWindow () {
    let api = new bgAPI;
    let idx = 0;

    let win = new BrowserWindow({
      width: 1440,
      height: 900,
      webPreferences: {
        nodeIntegration: false,
        contextIsolation:true,
        preload: path.join(__dirname, 'preload.js')
      }
    })

    function load (result, idx){
      
      win.webContents.removeAllListeners('did-finish-load');
      
      win.loadURL(result[1][idx])
      .then(
        win.webContents.on('did-finish-load', ()=>{
          ipcMain.removeAllListeners('go-next-link');
          ipcMain.removeAllListeners('write-file');
          ipcMain.removeAllListeners('set-category-page')
          ipcMain.removeAllListeners('set-keyword-page')

          win.webContents.executeJavaScript(result[2])
          
          //수집제한 목록 이벤트 리스너
          ipcMain.on('write-file', async (event, arg) => {
            try {
              let all_collected = result[0].concat(arg)
              await fs.promises.writeFile('수집제한목록.json', JSON.stringify(all_collected));

              result[0] = all_collected
              // 작성 성공 시 'success' 문자열과 함께 응답 전송 
              event.reply('write-file-reply', 'success');
            } catch(err) {
              // 에러 발생 시 에러 객체와 함께 응답 전송 
              event.reply('write-file-reply', err);
            }
          });

          //다음 링크로 가는 이벤트 리스너
          ipcMain.on('go-next-link', async(event, arg)=>{

            for (let [index, value] of result[1].entries()) {
              if (arg == value) {
                idx = index
                break
              }
            };
            
            try{
              load(result, idx+1)}
            catch(err){
              event.reply('last-link')
            }

          });
          
          //카테고리 설정 창 이벤트 리스너
          ipcMain.on('set-category-page', async(event, arg)=>{
            ipcMain.removeAllListeners('load-matched-category')
            ipcMain.removeAllListeners('set-category')
            
            async function category_window () {
              const win2 = new BrowserWindow({
                width: 320,
                height: 600,
                resizable: false,
                webPreferences: {
                  nodeIntegration: false,
                  contextIsolation:true,
                  preload: path.join(__dirname, 'preload.js')
                }
              })
              win2.loadFile('category_url.html')
              return win2
            };
            
            //카테고리 매핑과 각 요소 별 카테고리 코드 전부 로드
            function load_category_file(){
              const workbook2 = XLSX.readFile('카테고리북.xlsx')
              const sheetNames2 = workbook2.SheetNames;
              const sheetIndex2 = 0;
              
              const worksheet2 = workbook2.Sheets[sheetNames2[sheetIndex2]];
              const RAWCODES_NAVER = workbook2.Sheets[sheetNames2[1]];
              const RAWCODES_GMKT = workbook2.Sheets[sheetNames2[2]];
              const RAWCODES_AC = workbook2.Sheets[sheetNames2[3]];
              const RAWCODES_11ST = workbook2.Sheets[sheetNames2[4]];
              
              var jsonData2 = XLSX.utils.sheet_to_json(worksheet2, { defval: "" });
              var codes_naver = XLSX.utils.sheet_to_json(RAWCODES_NAVER, { defval: "" });
              var codes_gmkt = XLSX.utils.sheet_to_json(RAWCODES_GMKT, { defval: "" });
              var codes_ac = XLSX.utils.sheet_to_json(RAWCODES_AC, { defval: "" });
              var codes_11st = XLSX.utils.sheet_to_json(RAWCODES_11ST, { defval: "" });

              return [jsonData2, codes_naver, codes_gmkt, codes_ac, codes_11st]
            };
            
            var raw_data = load_category_file()
            var data = raw_data[0]
            var codes_naver = raw_data[1]
            var codes_gmkt = raw_data[2]
            var codes_ac = raw_data[3]
            var codes_11st = raw_data[4]
            
            category_window()
            
            //매칭된 카테고리 찾는 이벤트 리스너
            ipcMain.on('load-matched-category', async (event, arg)=>{
              var results = []
              for (var obj of data) {
                if (obj['쿠팡'].includes(arg)){
                  results.push(obj['쿠팡'])
                }
              }
              if (results.length == 0) {
                results.push('검색결과 없음')
              }
              event.reply('complete', results)
              
            })
            
            //카테고리 설정 이벤트 리스너
            ipcMain.on('set-category', async(event, arg) => {
              await new Promise(resolve => {for(var obj of data){
                if(obj['쿠팡'].includes(arg)){
                  break
                }
              }
              //카테고리를 코드로 변환
              function get_category_num (market, codes){
                var hashed_category = obj[market].split('>')
                if(hashed_category.length == 3){
                  hashed_category.push('')
                }
                
                for(var element of codes){
                  if (element['대분류'] == hashed_category[0] &&
                  element['중분류'] == hashed_category[1] &&
                  element['소분류'] == hashed_category[2] &&
                  element['세분류'] == hashed_category[3]) 
                  {
                    var category_num = element['카테고리코드']
                    return category_num
                  };
                }; 
              };
            
            //선택된 카테고리의 코드 
            var selected_num_naver = get_category_num('스스', codes_naver)
            var selected_num_gmkt = get_category_num('지마켓', codes_gmkt)
            var selected_num_ac = get_category_num('옥션', codes_ac)
            var selected_num_11st = get_category_num('11번가', codes_11st)

              //현재 창의 링크 순회
              for(var obj2 of result[3]){
                if(obj2['PageLink'].includes(result[1][idx])){
                  obj2['category_Coupang'] = '',
                  obj2['category_Naver'] = selected_num_naver,
                  obj2['category_AC'] = selected_num_ac,
                  obj2['category_GMKT'] = selected_num_gmkt,
                  obj2['category_11st'] = selected_num_11st,
                  obj2['수집여부'] = 'Completed'
                };
              };

              api.write_excel(result[3])
              resolve()
            });
              event.reply('close-window')
            })
          });

          //키워드 설정 창 이벤트 리스너
          ipcMain.on('set-keyword-page', async(event, arg)=>{
            ipcMain.removeAllListeners('set-keyword')

            async function keyword_window () {
              const win3 = new BrowserWindow({
                width: 320,
                height: 420,
                resizable: false,
                webPreferences: {
                  nodeIntegration: false,
                  contextIsolation:true,
                  preload: path.join(__dirname, 'preload.js')
                }
              })
              win3.loadFile('keyword_url.html')
              return win3
            };
            
            keyword_window()
            ipcMain.on('set-keyword', async(event, arg) => {

              await new Promise(resolve => {
                var keyword1 = arg[0]
                var keyword2 =  arg[1]
                var keyword3 = arg[2]
                

                for(var obj2 of result[3]){
                  if(obj2['PageLink'].includes(result[1][idx])){
                    obj2['TitleKeyword1'] = keyword1
                    obj2['TitleKeyword2'] = keyword2
                    obj2['TitleKeyword3'] = keyword3
                    obj2['수집여부'] = 'Completed'
                  };
                };
              
                api.write_excel(result[3])
                resolve()
              })
              event.reply('keyword-done')
            })
          });      
        })
      )
    }
    api.init().then(result => {load(result, idx)})
}

class bgAPI {
  async init () {
    let link_lists;
    let target_links;
    let inner_script;

    try {
      const data = await fs.promises.readFile('수집제한목록.json', 'utf8');
      link_lists = JSON.parse(data)
    } catch (err) {
      link_lists = []; 
    }

    try {
      const data1 = await fs.promises.readFile('inner_script_code.js', 'utf8');
      inner_script = data1
    } catch (err) {
      console.error(err); 
      inner_script = null; 
    }

    const workbook = XLSX.readFile('/Users/jung-yongjun/Desktop/china/수집목록.xlsx')
    const sheetNames = workbook.SheetNames;
    const sheetIndex = 0;
    const worksheet = workbook.Sheets[sheetNames[sheetIndex]];
    var jsonData = XLSX.utils.sheet_to_json(worksheet);
    target_links = jsonData.reduce((links, row) => {
        if (row['수집여부'] === 'Y') {
            links.push(row['PageLink']);
        }
        return links;
    }, []);
    
    return [link_lists, target_links, inner_script, jsonData]
  }

  async write_excel(data){
    var headers = {
      header:[
        'PageLink',
        'PageAmount_START',
        'PageAmount_FINISH',
        'TitleKeyword1',
        'TitleKeyword2',
        'TitleKeyword3',
        'category_Naver',
        'category_GMKT',
        'category_AC',
        'category_11st',
        'category_Coupang',
        '수집여부'
      ]
    };

    const LinkWS = XLSX.utils.json_to_sheet(data, headers);
    const LinkWB = XLSX.utils.book_new();

    XLSX.utils.book_append_sheet(LinkWB, LinkWS, 'sheet1')
    XLSX.writeFile(LinkWB, '/Users/jung-yongjun/Desktop/china/수집목록.xlsx')
  }
};

app.whenReady().then(createWindow)
