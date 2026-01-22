from bit_api import *
import time
import asyncio
from playwright.async_api import async_playwright, Playwright



async def run(playwright: Playwright):

  # /browser/open 接口会返回 selenium使用的http地址，以及webdriver的path，直接使用即可
  browser_id = "1ce676a2ae0a41bcaf73c6934d8ff230" # 窗口ID从窗口配置界面中复制，或者api创建后返回
  res = openBrowser(browser_id)
  ws = res['data']['ws']
  print("ws address ==>>> ", ws)

  chromium = playwright.chromium
  browser = await chromium.connect_over_cdp(ws)
  default_context = browser.contexts[0]

  print('new page and goto baidu')

  page = await default_context.new_page()
  await page.goto('https://baidu.com')

  time.sleep(2)

  print('clsoe page and browser')
  await page.close()

  time.sleep(2)
  closeBrowser(browser_id)

async def main():
    async with async_playwright() as playwright:
      await run(playwright)

asyncio.run(main())