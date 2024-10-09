import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

download_folder = os.path.join(os.getcwd(), 'input')
rss_feed_url_source = os.path.join(download_folder, 'config.txt')

def read_feed_url(file_path, key):
    try:
        with open(file_path, 'r') as f:
            for line in f:
                if line.strip():
                    k, v = line.strip().split('=', 1)
                    if k == key:
                        return v.strip()
        print(f'Error: Key "{key}" not found in {file_path}.')
        return None
    except FileNotFoundError:
        print(f'Error: {file_path} does not exist.')
        return None

def format_filename(pub_date_str):
    dt = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %z')
    return dt.strftime('%d %b %H') + '.mp3'

def is_downloaded(filename):
    return os.path.isfile(os.path.join(download_folder, filename))

def download_file(url, filename):
    response = requests.get(url, stream=True)
    response.raise_for_status()
    filepath = os.path.join(download_folder, filename)
    with open(filepath, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f'Downloaded: {filename}')

def parse_feed(url):
    response = requests.get(url)
    response.raise_for_status()
    content = response.content.decode('utf-8', errors='replace')
    context = ET.iterparse(iter([content]), events=('end',))
    for event, elem in context:
        if elem.tag.endswith('item'):
            pub_date = elem.find('./pubDate')
            media_content = None
            for media in elem.findall('./{http://search.yahoo.com/mrss/}content'):
                if media.get('type') == 'audio/mpeg':
                    media_content = media.get('url')
                    break
            if pub_date is not None and media_content:
                pub_date_str = pub_date.text
                filename = format_filename(pub_date_str)
                if not is_downloaded(filename):
                    download_file(media_content, filename)
                else:
                    print(f'Already downloaded: {filename}')
            break

def main():
    feed_url = read_feed_url(rss_feed_url_source)
    if feed_url:
        parse_feed(feed_url)

if __name__ == '__main__':
    main()

