import re
import time
import requests
import datetime
import configparser
from itertools import repeat
from functools import reduce
from bs4 import BeautifulSoup
from multiprocessing import Pool
from flask import Flask, request, abort

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
)

app = Flask(__name__)
config = configparser.ConfigParser()
config.read("config.ini")

line_bot_api = LineBotApi(config['line_bot_token']['Channel_Access_Token'])
handler = WebhookHandler(config['line_bot_token']['Channel_Secret'])

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(submit(event.message.text)))


def get_web_page(url):
    response = requests.get(url)
    if response.status_code != 200:
        print('[error]Invalid url: ' + url)
        return None
    return response.text


def get_page_number(url):
    return int(re.findall(r'page=(.*?)&', url)[0])


def get_ptt_movie_urls(keyword):
    page = get_web_page('https://www.ptt.cc/bbs/movie/search?q={}'.format(keyword))
    soup = BeautifulSoup(page, 'html.parser')
    last_page_url = soup.find_all('a', 'btn wide')[0]['href']
    last_page_number = get_page_number(last_page_url)
    urls = []
    for page_number in range(1, last_page_number):
        urls.append('https://www.ptt.cc/bbs/movie/search?page={}&q={}'.format(page_number, keyword))
    return urls


def crawl_criticism(url):
    soup = BeautifulSoup(get_web_page(url), 'html.parser')
    criticisms = []
    for div in soup.find_all('div', 'r-ent'):
        title = div.find('div', 'title').text.strip()
        if ('Re:' not in title):
            matched_title = re.findall(r'\[([^[]+)雷\]', title)
            if matched_title:
                criticism = matched_title[0]
                if ('有' not in criticism) and ('無' not in criticism):
                    criticisms.append(criticism.strip() + '雷')
    return criticisms


def combine_multiple_array_to_single_one(criticism_array):
    result = []
    for criticisms in criticism_array:
        if criticisms:
            for criticism in criticisms:
                result.append(criticism)
    return result


def analyze(criticisms):
    criticism_dic = {
        '好評': {},
        '負評': {},
        '普通': {},
        '其它': {}
    }

    up = {}
    down = {}
    average = {}
    others = {}

    for word in set(criticisms):
        if '好' in word:
            up[word] = criticisms.count(word)
            criticism_dic['好評'] = up
        elif '負' in word:
            down[word] = criticisms.count(word)
            criticism_dic['負評'] = down
        elif '普' in word:
            average[word] = criticisms.count(word)
            criticism_dic['普通'] = average
        else:
            others[word] = criticisms.count(word)
            criticism_dic['其它'] = others

    return criticism_dic, len(criticisms)


def parse_response_message(criticism_dic, total_count):
    response = ''

    for category, criticisms in criticism_dic.items():
        each_category_count = reduce(lambda x, y: x + y, criticisms.values(), 0)
        response += '【{}: {:.1%}】\n'.format(category, (each_category_count/total_count))
        for criticism, count in criticisms.items():
            response += criticism + ': ' + str(count) + ' 篇\n'
        response += '\n'

    response += '總共 {} 篇評論'.format(total_count)
    return response


def submit(keyword):
    pool = Pool(processes=20)
    results = pool.map(crawl_criticism, get_ptt_movie_urls(keyword))
    pool.close()

    criticisms = combine_multiple_array_to_single_one(results)
    criticism_dic, total_count = analyze(criticisms)
    return parse_response_message(criticism_dic, total_count)


if __name__ == "__main__":
    app.run()