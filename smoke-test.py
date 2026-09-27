"""宿主机执行 python3 smoke-test.py；独立浏览器上下文，不修改用户浏览器数据。"""
import json, threading, functools
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent
class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args): pass
server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
results=[]
def check(name,condition):
    assert condition,name
    results.append({'name':name,'status':'passed'})
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
    context=browser.new_context(viewport={'width':1440,'height':1050},accept_downloads=True)
    page=context.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(f'http://127.0.0.1:{server.server_port}/index.html')
    def state(): return page.evaluate('JSON.parse(localStorage.getItem("development-12-inventory-v1"))')
    def quantity(): return next(b['qty'] for b in state()['batches'] if b['id']=='B-1001')
    check('初始化及红黄绿效期提示',len(state()['batches'])==4 and all(page.locator('#table .'+c).count()>0 for c in ['red','yellow','green']))
    page.locator('#scan').fill('990000001');page.locator('#scanform button').click()
    check('条码模拟扫码定位',page.locator('#moveInfo').inner_text().find('B-1001')>=0)
    page.locator('[name=qty]').fill('5');page.locator('#moveForm button.primary').click()
    check('入库 8→13 且生成流水',quantity()==13 and state()['logs'][-1]['before']==8 and state()['logs'][-1]['after']==13)
    page.locator('[data-id="B-1001"][data-act="out"]').click();page.locator('[name=qty]').fill('4');page.locator('#moveForm button.primary').click()
    check('出库 13→9 且触发低库存',quantity()==9 and state()['logs'][-1]['after']==9 and '库存 9 / 阈值 10' in page.locator('#alerts').inner_text())
    before=state();page.locator('[data-id="B-1001"][data-act="out"]').click();page.locator('[name=qty]').fill('99');page.locator('#moveForm button.primary').click()
    check('超库存出库被拒且库存流水不变','超过当前库存' in page.locator('#moveError').inner_text() and state()==before)
    for value in ['-1','0','1.5']:
        page.locator('[name=qty]').fill(value);page.locator('#moveForm button.primary').click()
        check('拒绝非法数量 '+value,state()==before and page.locator('#moveDialog').is_visible())
    page.locator('[data-close=moveDialog]').click()
    page.locator('[data-id="B-1003"][data-act="out"]').click();page.locator('[name=qty]').fill('1');page.locator('#moveForm button.primary').click()
    check('过期批次禁止出库','已过期' in page.locator('#moveError').inner_text() and state()==before)
    page.locator('[data-close=moveDialog]').click();page.reload();check('刷新后库存流水持久化',state()==before)
    page.locator('#add').click()
    values={'name':'某企业耗材 E','id':'B-TEST-01','barcode':'990009999','place':'LAB-09','unit':'盒','expiry':'2099-12-31','min':'2','initial':'3'}
    for k,v in values.items():page.locator('#batchForm [name='+k+']').fill(v)
    page.locator('#batchForm button.primary').click()
    check('新增批次及初始入库流水',len(state()['batches'])==5 and state()['logs'][-1]['batch']=='B-TEST-01')
    page.locator('[data-id="B-TEST-01"][data-act="edit"]').click();page.locator('#batchForm [name=place]').fill('LAB-08');page.locator('#batchForm button.primary').click()
    check('修改资料不改变库存',state()['batches'][-1]['place']=='LAB-08' and state()['batches'][-1]['qty']==3)
    page.locator('#add').click()
    for k,v in values.items():page.locator('#batchForm [name='+k+']').fill(v)
    page.locator('#batchForm button.primary').click();check('重复编号被拒','重复' in page.locator('#batchError').inner_text() and len(state()['batches'])==5)
    page.locator('[data-close=batchDialog]').click();page.locator('#filter').select_option('yellow');check('临期筛选',page.locator('#table tbody tr').count()==1)
    page.locator('#filter').select_option('all');page.locator('#search').fill('B-TEST-01');check('搜索筛选',page.locator('#table tbody tr').count()==1)
    with page.expect_download() as download:page.locator('#export').click()
    data=Path(download.value.path()).read_text(encoding='utf-8-sig');check('库存 CSV 导出遵循筛选','B-TEST-01' in data and 'B-1001' not in data)
    page.locator('#logsTab').click();check('流水筛选',page.locator('#table tbody tr').count()==1)
    with page.expect_download() as download:page.locator('#export').click()
    check('流水 CSV 导出','操作前' in Path(download.value.path()).read_text(encoding='utf-8-sig'))
    page.once('dialog',lambda d:d.dismiss());page.locator('#reset').click();check('取消重置保留数据',len(state()['batches'])==5)
    page.once('dialog',lambda d:d.accept());page.locator('#reset').click();check('确认重置恢复演示数据',len(state()['batches'])==4 and quantity()==8)
    page.locator('#inventoryTab').click();page.screenshot(path=str(ROOT/'evidence-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844});check('手机布局无整页横向溢出',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
    page.locator('#add').click();check('手机可打开登记表单',page.locator('#batchDialog').is_visible());page.locator('[data-close=batchDialog]').click()
    page.screenshot(path=str(ROOT/'evidence-mobile.png'),full_page=True)
    check('无浏览器脚本错误',not errors)
    check('存储键使用项目专属前缀',page.evaluate('Object.keys(localStorage).every(k=>k.startsWith("development-12-"))'))
    browser.close()
server.shutdown()
(ROOT/'test-results.json').write_text(json.dumps({'runtime':'宿主机 / Python Playwright Chromium','tests':results},ensure_ascii=False,indent=2))
print(json.dumps({'passed':len(results),'tests':results},ensure_ascii=False,indent=2))
