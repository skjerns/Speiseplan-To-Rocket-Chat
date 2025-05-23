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
from io import BytesIO
import numpy as np
import datetime
import imgbbpy
import socket
import time
import subprocess
from pprint import pprint
from rocketchat_API.rocketchat import RocketChat
from functools import cache
from PIL import Image
from subprocess import check_output, STDOUT, CalledProcessError

try:
    from env import INTRA_URL, ROCKETCHAT_URL, ROCKETCHAT_ID, ROCKETCHAT_TOKEN
    from env import GITHUB_TOKEN
except:
    INTRA_URL = os.environ['INTRA_URL']
    ROCKETCHAT_URL = os.environ['ROCKETCHAT_URL']
    ROCKETCHAT_ID = os.environ['ROCKETCHAT_ID']
    ROCKETCHAT_TOKEN = os.environ['ROCKETCHAT_TOKEN']

    # IMGBB_KEY = os.environ['IMGBB_KEY']
    GITHUB_TOKEN = os.environ['GITHUB_TOKEN']



def parse_date(string):
    formats = ['%d.%m.%Y', '%d.%m.%y']
    for fmt in formats:
        try:
            return datetime.datetime.strptime(string, fmt)
        except:
            print(f'{string} did not match {fmt}')
    raise ValueError(f'{string} did not match any formats: {formats}')

glob = {}

@cache
def get_current_speiseplan_url():

    headers = {
            'authority': INTRA_URL,
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-GB,en;q=0.9,de;q=0.8',
            'cache-control': 'max-age=0',
            'content-type': 'application/x-www-form-urlencoded',
            # 'cookie': 'PHPSESSID=fs1ktkpjq3uhrqrs4mda7rf6uf',
            'dnt': '1',
                'origin': f'https://{INTRA_URL}',
                'referer': f'https://{INTRA_URL}/',
            'sec-ch-ua': '"Not.A/Brand";v="8", "Chromium";v="114", "Google Chrome";v="114", "Vivaldi";v="6.1"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
        }


    # retrieve current speiseplan
    speiseplan_response = requests.get(f'https://{INTRA_URL}/zi/cafeteria',
                                       headers=headers)
    assert speiseplan_response.ok

    # extract link to PDF of current speiseplan
    html = speiseplan_response.content.decode()
    soup = bs4.BeautifulSoup(html)
    # first item is for wards, second one is for cafeteria
    links = soup.findAll(href=True)
    pdfs = [link.attrs['href'] for link in links if link.attrs['href'].endswith('pdf')]
    pdfs = [pdf for pdf in pdfs if 'caf' in pdf.lower()]
    pdfs = [pdf for pdf in pdfs if not '/preisliste' in pdf.lower()]
    pdfs = [pdf for pdf in pdfs if not 'wichtigsten-bestuhlungsarten' in pdf.lower()]

    assert len(pdfs), 'no cafeteria speiseplaene found'
    pdfs_cafeteria = sorted(pdfs, key=lambda x: 'speiseplan' in x.lower())

    finddate = lambda x: re.findall(r'\d+[.]\d+[.]\d+', x, re.IGNORECASE)
    startingdates = [finddate(pdf.split('/')[-1]) for pdf in pdfs_cafeteria]
    startingdates = [['01.06.2000', '06.06.2000'] if dates==[] else dates for dates in startingdates ]
    startingdates = [parse_date(date[0]) for date in startingdates]

    weeks = [date.isocalendar().week for date in startingdates]
    thisweek = datetime.datetime.now().isocalendar().week

    if thisweek in weeks:
        pdf_url = pdfs_cafeteria[weeks.index(thisweek)]
    else:
        try:
            pdf_url = pdfs_cafeteria[-1].attrs['href']
        except AttributeError:
            pdf_url = pdfs_cafeteria[-1]

    # download PDF
    thisweek_url = f'https://{INTRA_URL}/{pdf_url}'
    return thisweek_url


def extract_table_camelot(thisweek_url):
    import camelot # pip install camelot-py
    table = camelot.read_pdf(thisweek_url)[0]
    rows = [x for _,x in table.df.iterrows()]

    wochentage = iter(['Mo', 'Di', 'Mi', 'Do', 'Fr'])

    speiseplan = {}
    for i, row in enumerate(rows):
        row = [x for x in row]
        if row_is_empty(row):
            print(i, row)
            continue
        else:
            print(i, row)
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


def extract_image(thisweek_url):
    response = requests.get(thisweek_url)
    assert response.ok
    import fitz # pip install pymupdf
    f = BytesIO(response.content)
    doc = fitz.open(stream=f)
    page = doc.load_page(0)  # number of page
    pix = page.get_pixmap()
    os.makedirs('speiseplaene', exist_ok=True)
    filename = datetime.datetime.now().strftime('./speiseplaene/%Y-%m-%d.png')
    pix.save(filename)
    doc.close()
    return filename

def crop_image(png_file):
    image = Image.open(png_file)
    week = image.crop([180, 125, 340, 150])
    cropped = image.crop([35, 223, 557, 775])
    cropped.paste(week, box=[150, 0])
    cropped.save(png_file)

def extract_table_tabula(thisweek_url):
    import tabula # pip install tabula-py
    response = requests.get(thisweek_url)
    assert response.ok
    import pandas as pd

    # dont save PDF, just put into memory
    f = BytesIO(response.content)

    # extract table with menu from the PDF using tabula
    df = tabula.read_pdf(f, pages='1', multiple_tables=True)

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


def post_speiseplan_ascii_to_rocket_chat(speiseplan):
    import tabulate
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

def upload_to_imagebb(speiseplan_png):
    imgbb_client = imgbbpy.SyncClient(IMGBB_KEY)
    upload = imgbb_client.upload(file=speiseplan_png, expiration=60*60*24*31)
    return upload.url


def send_cmd(cmd, sock):
    sock.send(cmd.encode() + b'\r\n')
    response = sock.recv(4096).decode()
    return response

def upload_to_github(png_file):
    "git config --global user.name 'github-actions[bot]'".split()
    "git config --global user.email 'github-actions[bot]@users.noreply.github.com'".split()

    output = subprocess.check_output(['git', 'config', '--global', 'user.name', "'github-actions[bot]'"])
    print('\n\ngit config name', output.decode())

    output = subprocess.check_output(['git', 'config', '--global', 'user.email', "'github-actions[bot]@users.noreply.github.com'"])
    print('\n\ngit config email', output.decode())

    # add token to url
    output = subprocess.check_output(['git', 'remote', 'set-url', '--push', 'origin', f'https://{GITHUB_TOKEN}@github.com/skjerns/Speiseplan-To-Rocket-Chat'])
    print('\n\ngit remote', output.decode())

    # Add files to git
    output = subprocess.check_output(['git', 'add', './speiseplaene/*'])
    print('\n\ngit add', output.decode())

    # Commit changes
    try:
        output = subprocess.check_output(['git', 'commit', '-m', 'Add recent speiseplan'], stderr=STDOUT)
    except subprocess.CalledProcessError as e:
        msg = e.output.decode()
        print(msg)
        if not 'Changes not staged for commit' in msg and not 'Your branch is up to date with' in msg:
            raise e

    # Push changes
    subprocess.run(['git', 'push'], check=True)

    # give time to github to sort everything out
    time.sleep(1)

    base_url = 'https://raw.githubusercontent.com/skjerns/Speiseplan-To-Rocket-Chat/main/speiseplaene'
    return f'{base_url}/{os.path.basename(png_file)}'

def upload_file_ftp(speiseplan_png):
    # Connect to FTP server
    with socket.create_connection((FTP_URL, 21)) as sock:
        response = sock.recv(4096).decode()
        print(response)

        # Send username
        response = send_cmd("USER " + FTP_USER, sock)
        print(response)

        # Send password
        response = send_cmd("PASS " + FTP_PASS, sock)
        print(response)

        # Set passive mode
        response = send_cmd("PASV", sock)
        print(response)

        # Extract passive mode connection details
        parts = response.split(',')
        host = '.'.join(parts[-4:-1])
        port = (int(parts[-2]) << 8) + int(parts[-1])

        # Connect to passive mode data socket
        with socket.create_connection((host, port)) as data_sock:
            # Send STOR command
            response = send_cmd("STOR " + os.path.basename(speiseplan_png), sock)
            print(response)

            # Open the local file in binary mode
            with open(speiseplan_png, 'rb') as file:
                # Read and send file data
                data = file.read(4096)
                while data:
                    data_sock.send(data)
                    data = file.read(4096)

            # Close data socket
            data_sock.close()

        # Close control socket
        sock.close()

    print("File uploaded successfully.")
    return f'https://{FTP_URL}/speiseplan/{speiseplan_png}'

def upload_file_ftp_sh(local_file_path):
    import subprocess
    # Check if the local file path is provided
    if not local_file_path:
        print("Error: Local file path is missing.")
        return

    # Call the shell script with the local file path as an argument
    try:
        script = os.path.dirname(__file__) + '/upload_file_ftp.sh'
        print(subprocess.check_output([script, local_file_path]))
        print("File uploaded successfully.")
    except subprocess.CalledProcessError as e:
        print("Error:", e)
    return  f'https://{FTP_URL}/speiseplan/{local_file_path}'

def post_speiseplan_image_to_rocket_chat(url):
    assert ROCKETCHAT_URL, 'ROCKETCHAT_URL missing'
    assert ROCKETCHAT_ID and ROCKETCHAT_TOKEN, 'ID or TOKEN missing'
    rocket = RocketChat(user_id=ROCKETCHAT_ID,
                        auth_token=ROCKETCHAT_TOKEN,
                        server_url=f'https://{ROCKETCHAT_URL}')

    now = datetime.datetime.now().strftime('%d. %b %Y')
    res = rocket.chat_post_message(f'Week start: {now}.\n{url}',
                                   channel='Speiseplan',
                                   emoji='robot'
                                   # alias='SpeiseplanBot',
                                    # previewUrls=[url]
                         )
    print(f'posting to rocket.chat: {res}\n\n{res.content.decode()}')


# def test_ftp():
#     # first check public ftp
#     ftp = ftplib.FTP_TLS('test.rebex.net')
#     ftp.login('demo', 'password')
#     ftp.quit()

#     # then check our own works
#     ftp = ftplib.FTP_TLS(FTP_URL)
#     ftp.login(FTP_USER, FTP_PASS)
#     ftp.quit()
#%% main
if __name__=='__main__':
    # test_ftp()

    thisweek_url = get_current_speiseplan_url()
    png_file = extract_image(thisweek_url)
    # crop_image(png_file)
    url = upload_to_github(png_file)
    # url = upload_to_imagebb(png_file)
    # url = upload_file_ftp_sh(png_file)
    # url = upload_file_ftp(png_file)
    post_speiseplan_image_to_rocket_chat(url)
