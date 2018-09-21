import pandas as pd
import requests
import os
import subprocess
import logging
import time

from pusher import *
from parser import WebDriver
from utils import load_yml_config
from html_parser import HTMLTableParser


settings = load_yml_config()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)
logger.addHandler(ch)


def kill_chrome():
    cmd = 'sudo pkill -f chromium'
    return_value = subprocess.call(cmd, shell=True)
    return return_value


################################################################################
############################# Monitor Web Posts ################################
################################################################################


class MonitorARA():
    def __init__(self):
        self.target_url = settings.URL_ARA
        self.table_parser = HTMLTableParser()
        self.path_data_ara = settings.PATH_DATA_ARA
        self.p_table = self.get_table() # update with latest post list

    def generate_url(self, index):
        template_url = 'http://ara.kaist.ac.kr/board/Wanted/{}/?page_no=1'
        return template_url.format(index)

    def load_table(self):
        if os.path.isfile(self.path_data_ara):
            table = pd.read_csv(self.path_data_ara)
            table = table.drop(columns=['id.1'])
            table.index = table['id']
        else:
            table = self.get_table()
            self.save_table(table)
        return table

    def save_table(self, table):
        if len(table) > 15:
            table.to_csv(self.path_data_ara)

    def get_table(self):
        while True:
            html_string = requests.get(self.target_url).text
            table = self.table_parser.parse_html(html_string)[0]
            table.index = table['id']
            table = table.drop(columns=['N', '작성자', '말머리'])
            if len(table) > 15:
                return table

    def update_p_table(self, table):
        if len(table) > 15:
            set_old_index = set(self.p_table.index.values)
            for idx in set_old_index:
                try:
                    table = table.drop(index=[idx])
                except:
                    pass
            table = table.append(self.p_table)
            table = table.iloc[:min(len(table), 30)]
            self.p_table = table

    def find_update(self, p_table, c_table):
        set_p_index = set(p_table.index.values)
        set_c_index = set(c_table.index.values)
        set_new_posts = set_c_index - set_p_index
        set_old_posts = set_c_index - set_new_posts

        self.update_p_table(c_table)

        changed_posts = dict()
        finished_posts = dict()
        for id in set_old_posts:
            p_title = p_table.loc[[id]]['제목'].values[0]
            c_title = c_table.loc[[id]]['제목'].values[0]
            self.p_table.loc[id, '제목'] = c_title
            if p_title != c_title:
                if '마감' in c_title or '완료' in c_title:
                    finished_posts[id] = {'title': c_title, 'link': self.generate_url(id)}
                else:
                    changed_posts[id] = {'p_title': p_title, 'c_title': c_title, 'link': self.generate_url(id)}

        new_posts = dict()
        for id in set_new_posts:
            c_title = c_table.loc[[id]]['제목'].values[0]
            if not '카풀' in c_title:
                new_posts[id] = {'title': c_title, 'link': self.generate_url(id)}

        return new_posts, changed_posts, finished_posts



class ParserARA(WebDriver):
    def __init__(self):
        self.target_url = settings.URL_ARA
        self.table_parser = HTMLTableParser()
        WebDriver.__init__(self, target_url=self.target_url)

    def login(self):
        path_id = '//*[@id="miniLoginID"]'
        path_pw = '//*[@id="miniLoginPassword"]'
        path_btn = '//*[@id="loginBox"]/dd/form/ul/li[3]/a[1]'

        input_id = self.driver.find_element_by_xpath(path_id)
        input_id.send_keys(settings.ARA_ID)

        input_pw = self.driver.find_element_by_xpath(path_pw)
        input_pw.send_keys(settings.ARA_KEY)

        # Login to the site
        self.click_btn(path_btn)

    def get_table(self):
        path_table = '//*[@id="board_content"]/table'
        table = self.driver.find_element_by_xpath(path_table)
        html_string = table.get_attribute('innerHTML')
        html_string = self.driver.page_source
        tables = self.table_parser.parse_html(html_string)
        return tables


if __name__ == '__main__':
    # parser = ParserARA()
    # parser.screenshot()
    # parser.login()
    # table = parser.get_table()[0]

    monitor = MonitorARA()
    telegram_pusher = TelegramPusher()

    logger.info("###########################################")
    logger.info("########## Start POST Monitoring ##########")
    logger.info("###########################################")


    with pd.option_context('display.max_rows', None, 'display.max_columns', None):


        cnt = 0
        while True:
            time.sleep(0.3)
            new_table = monitor.get_table()
            new_posts, changed_posts, finished_posts = monitor.find_update(monitor.p_table, new_table)
            # monitor.save_table(new_table)

            for id, data in new_posts.items():
                content = telegram_pusher.generate_content(request=data, mode=NEW)
                telegram_pusher.send_message(content)
                logger.info(data)

                # request = KakaoContentMaker.content_new(data['title'], data['link'])
                # KakaoPusher(request)
                # kill_chrome()


            for id, data in changed_posts.items():
                content = telegram_pusher.generate_content(request=data, mode=UPDATE)
                telegram_pusher.send_message(content)
                logger.info(data)

                # request = KakaoContentMaker.content_changed(data['p_title'], data['c_title'], data['link'])
                # KakaoPusher(request)
                # kill_chrome()

            for id, data in finished_posts.items():
                content = telegram_pusher.generate_content(request=data, mode=FINISHED)
                telegram_pusher.send_message(content)
                logger.info(data)

                # request = KakaoContentMaker.content_finished(data['title'], data['link'])
                # KakaoPusher(request)
                # kill_chrome()

            cnt += 1
            if cnt > settings.LOG_INTERVAL:
                logger.info('{} connection tried'.format(settings.LOG_INTERVAL))
                cnt = 0

