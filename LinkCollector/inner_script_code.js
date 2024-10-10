

async function load_content(){
    
    await new Promise(resolve => setTimeout(() => {
        window.scrollTo(0, document.body.scrollHeight / 4);
        resolve();
    }, 200));

    await new Promise(resolve => setTimeout(() => {
        window.scrollTo(0, document.body.scrollHeight / 4 *2);
        resolve();
    }, 200));


    await new Promise(resolve => setTimeout(() => {
        window.scrollTo(0, document.body.scrollHeight / 4 *3);
        resolve();
    }, 200));

    await new Promise(resolve => setTimeout(() => {
        window.scrollTo(0, document.body.scrollHeight);
        resolve();
    }, 200));

    await new Promise(resolve => setTimeout(() => {
        window.scrollTo(0, 0);
        resolve();
    }, 200));
};

function setbutton(){

    var elements = document.getElementsByClassName('search-card-item');
    var elements = Array.from(elements)
    elements.forEach(function(element) {
        element.addEventListener('contextmenu', function input (event){
            
            event.preventDefault();
            if (element.classList.contains('selected_linker')) {
                console.log('ㅌ')
                // 이미 선택된 요소인 경우 초기화
                element.style.backgroundColor = '';
                element.classList.remove('selected_linker');
                
            } else {
                // 선택되지 않은 요소인 경우 선택 처리
                console.log('d')
                element.style.backgroundColor = '#808080';
                element.classList.add('selected_linker');
            };
        });
    });

};

function setmenu() {
    var container = document.body
    var excludedElements = document.getElementsByClassName('search-card-item');
    let current_url = location.href;

    
    // 메뉴 요소 설정
    container.addEventListener('contextmenu', (e)=>{
        var oldMenu = document.getElementById('customMenu');

        e.preventDefault();
        for (let excludedElement of excludedElements){
            if (e.target === excludedElement || excludedElement.contains(e.target)) {
                // 제외된 요소 또는 그 자식요소에서 발생한 클릭이라면 아무 것도 하지 않음
                return;
            }
        };

        if(!oldMenu) {
            var customMenu = document.createElement('div')
            var button1 = document.createElement('button');
            button1.style.width = '200px';
            button1.style.height = '30px';
            button1.style.lineHeight = '30px';
            button1.innerText = '선택한 상품 링크 수집';
            
            // 이벤트 리스너 등록
            button1.addEventListener('click', button_clicked1);

            // 두 번째 버튼
            var button2 = document.createElement('button');
            button2.style.width = '200px';
            button2.style.height = '30px';
            button2.style.lineHeight ='30px';
            button2.innerText ='다음 링크로 이동';

            button2.addEventListener('click', ()=>{
                button_clicked2(current_url)
            });
            
            var button3 = document.createElement('button');
            button3.style.width = '200px';
            button3.style.height = '30px';
            button3.style.lineHeight = '30px';
            button3.innerText = '카테고리 설정';
            button3.addEventListener('click', button_clicked3);

            var button4 = document.createElement('button');
            button4.style.width = '200px';
            button4.style.height = '30px';
            button4.style.lineHeight = '30px';
            button4.innerText = '키워드 설정';
            button4.addEventListener('click', button_clicked4);

            // 이벤트 리스너 등록
            customMenu.appendChild(button1);
            customMenu.appendChild(button2);
            customMenu.appendChild(button3);
            customMenu.appendChild(button4);

            customMenu.id = 'customMenu'; // id를 추가해서 나중에 찾을 수 있게 함
            customMenu.style.boxShadow = '3px 3px 3px grey';
            customMenu.style.background = '#FFFFFF';
            customMenu.style.display = 'flex';
            customMenu.style.flexDirection = 'column';

            document.body.appendChild(customMenu);
            customMenu.style.position = 'absolute';
            
            // 마우스 위치에 따라 메뉴 위치 조정
            customMenu.style.left = e.pageX + 'px'; 
            customMenu.style.top 	= e.pageY + 'px';
        } else {
            oldMenu.remove()
        }

    },false);
    

    container.addEventListener('click', (e) =>{
        var oldMenu = document.getElementById('customMenu');
        if(oldMenu) {
            oldMenu.remove();
        }
    });
};


function button_clicked1() {
    function complete_message() {
        let completeMessage = new Image()
        completeMessage.src = 'https://i.ibb.co/x8px8XM/complete.png'

        var style = document.createElement('style');
        style.textContent = `
            @keyframes fadeIn {
                0%   { opacity: 0; }
                25%  { opacity: 1; }
                75%  { opacity: 1; }
                100% { opacity: 0; }
            }
    
            .fadeIn {
                animation-name: fadeIn;
                animation-duration: 4s;
            }`;
    
        document.head.appendChild(style);
        
        completeMessage.className = 'fadeIn'; 
        completeMessage.addEventListener('animationend',() => {
            document.body.removeChild(completeMessage);
        });
    
        completeMessage.style.position = 'fixed'; 
        completeMessage.style.top = '30%'; 
        completeMessage.style.left = '50%';
        completeMessage.style.transform = 'translate(-50%, -50%)';
    
    
        document.body.appendChild(completeMessage);
    
    };

    var selected_link_lists = []
    var elements = document.getElementsByClassName('selected_linker')

    Array.from(elements).forEach((element) => {
        var link = element.href.split('spm=')[0]
        selected_link_lists.push(link)
    });

    window.electron.send('write-file', selected_link_lists);

    window.electron.on('write-file-reply', (event, arg) => {
        if(arg === 'success') {
          complete_message();
        } else {
          console.error(arg); // 에러 출력
        }
      });

};


function button_clicked2(current_url) {
    window.electron.send('go-next-link', current_url);
    
};

function button_clicked3(){
    window.electron.send('set-category-page')
};

function button_clicked4(){
    window.electron.send('set-keyword-page')
};

async function main() {
    setmenu()
    load_content().then(setbutton)
    window.electron.on('last-link',(event, arg)=>{
        window.alert('마지막 링크입니다')
    })
};

main();