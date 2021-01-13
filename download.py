#!/usr/bin/env python3
# Sat 17 Oct 2020 02:58:42 PM CST
# 
# Example usage:
# jaccount name: nidemingze
# jaccount password: nidemima
# Captcha: haha
# book url: http://jcft.lib.sjtu.edu.cn:9088/front/reader/goRead?ssno=14668597&channel=100&jpgread=1

import re
import io
import imghdr
import tempfile
import itertools
from pathlib import Path
from typing import List, Iterator, Tuple
from concurrent import futures

import requests
from PIL import Image
from selenium import webdriver


class JSession:
    def __init__(self, username: str = None, password: str = None):
        self.session = requests.Session()
        self.driver = webdriver.Chrome()
        self._login(username, password)

    def _init_session(self):
        self.session.headers['User-Agent'] = self.driver.execute_script(
            'return navigator.userAgent')

    def _sync_with_session(self):
        self.session.headers['Referer'] = self.driver.current_url
        self.session.headers['Host'] = self.driver.execute_script(
            'return location.host')
        for cookie in self.driver.get_cookies():
            self.session.cookies.set(cookie['name'], cookie['value'])

    def _login(self, username: str = None, password: str = None):
        login_url = 'https://jaccount.sjtu.edu.cn/profile/'
        self.driver.get(login_url)
        self.driver.implicitly_wait(5)
        self.driver.find_element_by_css_selector('#user').send_keys(USERNAME)
        self.driver.find_element_by_css_selector('#pass').send_keys(PASSWORD)

        captcha_str = input('Captcha: ')

        self.driver.find_element_by_css_selector('#captcha').send_keys(
            captcha_str)
        self.driver.find_element_by_css_selector('#submit-button').click()

        self._sync_with_session()

    def driver_get(self, url: str):
        self.driver.get(url)
        self._sync_with_session()

    def session_get(self, url: str) -> requests.Response:
        return self.session.get(url)

    def close_driver(self):
        self.driver.close()


def get_book_resources(jaccount: JSession,
                       book_url: str,
                       skip_pages: List[int] = []) -> Iterator[bytes]:
    jaccount.driver_get(book_url)

    # really lazy parsing of the javascript source code
    jpg_path = re.search(r'jpgPath: "(.+?)"',
                         jaccount.driver.page_source).groups()[0]

    page_strs = jaccount.driver.execute_script(
        '''
    let jpgPath = arguments[0];
    let pageStrs = jQuery('.readerPager').toArray().map(pager => $(pager).data('pagerInfo')['pageStr']);
    return pageStrs;
    ''', jpg_path)

    jaccount.session.headers['Cookie'] = '; '.join(
        f'{key}={jaccount.session.cookies.get_dict()[key]}'
        for key in ['JSESSIONID', 'jiagong'])

    jaccount.close_driver()

    def get_raw_image(data: Tuple[int, str]) -> Tuple[int, bytes]:
        book_page, page_str = data
        if book_page in skip_pages:
            return (book_page, None)

        url_left = 'http://10.119.2.12:9088/jpath/'
        url_middle = f'{jpg_path}{page_str}'
        url_right = '?zoom=0'
        url = url_left + url_middle + url_right

        # retry 3 times
        counter = itertools.count()
        while next(counter) <= 3:
            try:
                res = jaccount.session.get(url)
                break

            except requests.ConnectionError as e:
                print(e)

        return (book_page, res.content)

    with futures.ThreadPoolExecutor(max_workers=5) as executor:
        yield from executor.map(get_raw_image, enumerate(page_strs))


SAVEDIR = Path('./SJTU-book-download')
SAVEDIR.mkdir(exist_ok=True)

USERNAME = input('jaccount name: ')
PASSWORD = input('jaccount password: ')
jaccount = JSession(USERNAME, PASSWORD)
book_url = input('book url: ')
skip_pages = [int(Path(file).stem) for file in SAVEDIR.glob('*')]
for page, raw_book_image in get_book_resources(jaccount, book_url, skip_pages):
    # skipped page
    if raw_book_image is None:
        continue

    extension = imghdr.what(None, raw_book_image)
    save_path = (SAVEDIR / str(page)).with_suffix(f'.{extension}')
    with open(save_path, 'wb') as f:
        f.write(raw_book_image)
        print(save_path)
