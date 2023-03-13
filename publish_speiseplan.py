# -*- coding: utf-8 -*-
"""
Created on Tue Aug 30 09:13:03 2022

Publish the Speiseplan of our cafeteria to RocketChat

@author: Simon Kern
"""
import os
import re
import requests
import bs4
import tabulate
import tabula # pip install tabula-py
import camelot # pip install camelot-py
from io import BytesIO
import pandas as pd
import numpy as np
import datetime
from pprint import pprint
from rocketchat_API.rocketchat import RocketChat
from functools import cache

try:
    from env import *
except:
    INTRA_URL = os.environ['INTRA_URL']
    INTRA_USER = os.environ['INTRA_USER']
    INTRA_PASS = os.environ['INTRA_PASS']

    ROCKETCHAT_URL = os.environ.get('ROCKETCHAT_URL')
    ROCKETCHAT_ID = os.environ.get('ROCKETCHAT_ID')
    ROCKETCHAT_TOKEN = os.environ.get('ROCKETCHAT_TOKEN')

def parse_date(string):
    formats = ['%d.%m.%Y', '%d.%m.%y']
    for fmt in formats:
        try:
            return datetime.datetime.strptime(string, fmt)
        except:
            print(f'{string} did not match {fmt}')
    raise ValueError(f'{string} did not match any formats: {formats}')

@cache
def get_current_speiseplan():
    # default header from Chrome
    headers = {
        'authority': INTRA_URL,
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'accept-language': 'en-GB,en;q=0.9',
        'cache-control': 'max-age=0',
        'dnt': '1',
        'origin': f'https://{INTRA_URL}',
        'referer': f'https://{INTRA_URL}/',
        'sec-ch-ua': '"Chromium";v="108", "Not?A_Brand";v="8"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    }

    logindata = {
        'user': INTRA_USER,
        'pass': INTRA_PASS,
        'submit': 'Anmelden',
        'logintype': 'login',
        'pid': '2@f21d4061d06b7761f48ff3d692a191ed496bb068',
        'redirect_url': '',
        'tx_felogin_pi1[noredirect]': '0',
    }

    print('url_intra is', INTRA_URL)

    login_response = requests.post(f'https://{INTRA_URL}/', headers=headers,
                                   data=logindata)

    # login successful? keep cookies to show we are logged in
    assert login_response.ok
    cookies = login_response.cookies

    # retrieve current speiseplan
    speiseplan_response = requests.get(f'https://{INTRA_URL}/zi/cafeteria/wochenspeiseplan',
                            cookies=cookies, headers=headers, data=logindata)
    assert speiseplan_response.ok

    # extract link to PDF of current speiseplan
    html = speiseplan_response.content.decode()
    soup = bs4.BeautifulSoup(html)
    # first item is for wards, second one is for cafeteria
    pdfs = soup.findAll('a', text='Mittagessen')
    pdfs_cafeteria = [pdf for pdf in pdfs if not 'station' in pdf.attrs['href'].lower()]
    assert len(pdfs_cafeteria)>0, 'no cafeteria speiseplaene found'

    finddate = lambda x: re.findall(r'\d+[.]\d+[.]\d+', x, re.IGNORECASE)
    startingdates = [finddate(pdf['href'].split('/')[-1]) for pdf in pdfs_cafeteria]
    startingdates = [['01.06.2000', '06.06.2000'] if dates==[] else dates for dates in startingdates ]
    startingdates = [parse_date(date[0]) for date in startingdates]

    weeks = [date.isocalendar().week for date in startingdates]
    thisweek = datetime.datetime.now().isocalendar().week

    if thisweek in weeks:
        pdf_url = pdfs_cafeteria[weeks.index(thisweek)].attrs['href']
    else:
        pdf_url = pdfs_cafeteria[-1].attrs['href']

    # download PDF
    thisweek_url = f'https://{INTRA_URL}/{pdf_url}'

    try:
        speiseplan = extract_table_camelot(thisweek_url)
    except:
        speiseplan = extract_table_tabula(thisweek_url)
    return speiseplan


def extract_table_camelot(thisweek_url):
    table = camelot.read_pdf(thisweek_url)[0]
    rows = [x for _,x in table.df.iterrows()]

    wochentage = iter(['Mo', 'Di', 'Mi', 'Do', 'Fr'])

    speiseplan = {}
    for i, row in enumerate(rows):
        row = [x for x in row]
        if row_is_empty(row):
            continue
        else:
            ncol = len(row)
            meat = row[ncol-2]
            vegg = row[ncol-1]

            meat = strip(meat)
            vegg = strip(vegg)

            meat = meat.replace('Heute hausgemacht!', '')
            vegg = vegg.replace('Heute hausgemacht!', '')

            meat = ' '.join([clean(w) for w in meat.split(' ')])
            vegg = ' '.join([clean(w) for w in vegg.split(' ')])

            while '  ' in meat: meat = meat.replace('  ', ' ')
            while '  ' in vegg: vegg = vegg.replace('  ', ' ')

            # day = next(wochentage)
            day = next(wochentage)
            speiseplan[day] = [meat.split(' '), vegg.split(' ')]

    return speiseplan


def extract_table_tabula(thisweek_url):
    response = requests.get(thisweek_url)
    assert response.ok

    # dont save PDF, just put into memory
    f = BytesIO(response.content)

    # extract table with menu from the PDF using tabula
    df = tabula.read_pdf(f, pages='1', multiple_tables=False)[0]

    # some cleanup
    rows = list([[y.replace('□', '') if isinstance(y, str) else y for y in x] for _,x in df.iterrows()])
    rows = [r for r in rows if not (('hausgemacht' in str(r[0])) or ('hausgemacht' in str(r[min(len(r),0)])))]
    colname = [c for c in df.columns if c.startswith('W')][0]
    # see which table rows have the days

    daypos = np.where(~df[colname].isna())[0]

    # lambda function if row is empty
    isempty =  lambda l: all([x in (np.nan, False, '') or pd.isna(x) for x in l])

    # extract meat and veggy option from the table
    na2str = lambda x: '' if pd.isna(x) else str(x)

    wochentage = iter(['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag'])

    days = {}
    for pos in daypos:

        if len(rows[pos])>2:
            col1 = 1
            day = rows[pos][0]
        else:
            col1 = 0
            day = next(wochentage)

        days[day] = [[], []]

        # find beginning. sometimes the extraction doesnt work correctly
        # and the day is one row below the start of the menu, so search
        # from day position upwards for an empty row
        while pos>1 and not isempty(rows[pos-1]):
            pos -= 1

        # extract meat options and vegg options for that specific day
        while True:
            if pos>=len(rows):
                break
            if any(pd.isna(rows[pos][col1:col1+1])):
                meat = np.nan
            else:
                meat = [na2str(x) for x in rows[pos][col1:col1+1]]
            veg = rows[pos][-1]
            if pd.isna(meat) and pd.isna(veg):
                break
            if not pd.isna(meat):
                days[day][0].append(meat)
            if not pd.isna(veg):
                days[day][1].append(veg)
            pos += 1
    pprint(days)  # print for debugging
    return days

def strip(string, tostrip = ['\n', '(', ')', ',', ';', '   ', *range(10)]):
    for x in tostrip:
        string = string.replace(str(x), ' ')
    string = ''.join([x for x in string if x.isascii() or x.lower() in 'äüöß'])
    string = string.replace('  ', ' ')
    return string


def row_is_empty(row):
    """"""
    text = ' '.join(row)
    text = ''.join([x for x in text if x.isascii()])
    text = ''.join([x for x in text if x.isalpha()])
    text = text.lower().replace('hausgemacht', '')
    text = text.lower().replace('heute', '')
    if len(text)>5: return False
    return True


def clean(word):
    """remove all words that are all upper or numbers.

    these are used for indicating allergenes, we want to filter them out
    """
    tmp = word.replace(',', '')
    tmp = word.replace(';', '')
    if tmp.isupper() or tmp.isnumeric(): return ''
    return word

#%%
def post_speiseplan_to_rocket_chat(speiseplan):
    assert ROCKETCHAT_URL, 'ROCKETCHAT_URL missing'
    assert ROCKETCHAT_ID and ROCKETCHAT_TOKEN, 'ID or TOKEN missing'
    # login to the rocket chat server
    rocket = RocketChat(user_id=ROCKETCHAT_ID,
                        auth_token=ROCKETCHAT_TOKEN,
                        server_url=f'https://{ROCKETCHAT_URL}')

    now = datetime.datetime.now()
    monday = now - datetime.timedelta(days = now.weekday())
    weekstart = monday.strftime('%d.%m')

    # clean up and put in a nice format
    rows = []
    for i, (day, (meat, veg)) in enumerate(speiseplan.items()):
        # try:
        #     day = datetime.datetime.strptime(day, '%d.%m.%Y')
        #     day = day.strftime('%a\n%d.%m')[:2]
        # except:
        #     pass
        day_fmt = (monday + datetime.timedelta(days=i)).strftime(f'{day}\n%d.')
        meat = ' '.join(meat)
        veg = ' '.join(veg)

        meat = ' '.join([clean(w) for w in meat.split(' ')]).replace('  ', ' ')
        veg = ' '.join([clean(w) for w in veg.split(' ')]).replace('  ', ' ')
        meat = ''.join([x for x in meat if x.isprintable()])
        veg = ''.join([x for x in veg if x.isprintable()])

        rows += [[day_fmt + '\n', meat], ['' , veg]]

    # max. 23 chars long, should fit most smartphone screens
    table = tabulate.tabulate(rows, headers = [datetime.datetime.now().strftime('%b'), 'Choices'],
                              tablefmt="fancy_grid", maxcolwidths=[3, 22])
    table = '\n'.join([x[:5] + x[9:] for x in table.split('\n')])

    res = rocket.chat_post_message(f'```\n{table}\n```', channel='Speiseplan')
    print(f'posting to rocket.chat: {res}\n\n{res.content.decode()}')
    return table




if __name__=='__main__':

    speiseplan = get_current_speiseplan()
    table = post_speiseplan_to_rocket_chat(speiseplan)
    print(table)