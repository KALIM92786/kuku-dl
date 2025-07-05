import argparse
import json
import os
import re
import requests
from mutagen.mp4 import MP4, MP4Cover
from urllib.parse import urlparse
import yt_dlp
from http.cookiejar import MozillaCookieJar

TITLE = "\r\n /$$   /$$           /$$                               /$$ /$$\r\n| $$  /$$/          | $$                              | $$| $$\r\n| $$ /$$/  /$$   /$$| $$   /$$ /$$   /$$          /$$$$$$$| $$\r\n| $$$$$/  | $$  | $$| $$  /$$/| $$  | $$ /$$$$$$ /$$__  $$| $$\r\n| $$  $$  | $$  | $$| $$$$$$/ | $$  | $$|______/| $$  | $$| $$\r\n| $$\\  $$ | $$  | $$| $$_  $$ | $$  | $$        | $$  | $$| $$\r\n| $$ \\  $$|  $$$$$$/| $$ \\  $$|  $$$$$$/        |  $$$$$$$| $$\r\n|__/  \\__/ \\______/ |__/  \\__/ \\______/          \\_______/|__/\r\n                      --by @bunnykek"

HEADERS = {
    'accept': '*/*',
    'accept-language': 'en-GB,en;q=0.9',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
}

class KuKu:
    def __init__(self, url: str) -> None:
        self.showID = urlparse(url).path.split('/')[-1]
        self.session = requests.Session()
        cookie_jar = MozillaCookieJar('cookies.txt')
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
        self.session.headers.update(HEADERS)
        self.session.cookies.update(cookie_jar)

        response = self.session.get(f"https://kukufm.com/api/v2.3/channels/{self.showID}/episodes/?page=1")
        data = response.json()

        show = data['show']
        self.metadata = {
            'title': KuKu.sanitiseName(show['title'].strip()),
            'image': show['original_image'],
            'date': show['published_on'],
            'fictional': show['is_fictional'],
            'nEpisodes': show['n_episodes'],
            'author': show['author']['name'].strip(),
            'lang': show['language'].capitalize().strip(),
            'type': ' '.join(show['content_type']['slug'].strip().split('-')).capitalize(),
            'ageRating': show.get('meta_data', {}).get('age_rating', None),
            'credits': {},
            'hasVideoEps': "video_thumbnail" in show["other_images"]
        }

        print(f"""
Album info:
  Name       : {self.metadata['title']}
  Author     : {self.metadata['author']}
  Language   : {self.metadata['lang']}
  Date       : {self.metadata['date']}
  Age rating : {self.metadata['ageRating']}
  Episodes   : {self.metadata['nEpisodes']}
  Video Eps  : {self.metadata['hasVideoEps']}
""")

        for credit in show['credits'].keys():
            self.metadata['credits'][credit] = ', '.join(
                [person['full_name'] for person in show['credits'][credit]]
            )

    @staticmethod
    def sanitiseName(name) -> str:
        return re.sub(r'[:]', ' - ', re.sub(r'[\\/*?"<>|$]', '', re.sub(r'[ \t]+$', '', str(name).rstrip())))

    def downloadAndTag(self, episodeMetadata: dict, path: str, srtPath: str, coverPath: str) -> None:
        print(f"▶ Downloading: {episodeMetadata['title']}", flush=True)
        if os.path.exists(path):
            print(f"✔ Already exists, skipping.")
            return

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': path,
            'http_headers': HEADERS,
            'quiet': True,
            'no_warnings': True,
            'cookiefile': "cookies.txt",
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([episodeMetadata['url']])
        except Exception as e:
            print(f"✖ Download failed: {e}")
            return

        hasLyrics = bool(episodeMetadata['srt'])
        if hasLyrics:
            srt_response = self.session.get(episodeMetadata['srt'])
            with open(srtPath, 'w', encoding='utf-8') as f:
                f.write(srt_response.text)

        tag = MP4(path)
        tag['\xa9alb'] = [self.metadata['title']]
        tag['\xa9ART'] = [self.metadata['author']]
        tag['aART'] = [self.metadata['author']]
        tag['\xa9day'] = [episodeMetadata['date'][0:10]]
        tag['trkn'] = [(int(episodeMetadata['epNo']), int(self.metadata['nEpisodes']))]
        tag['stik'] = [2]
        tag['\xa9nam'] = [episodeMetadata['title']]
        tag.pop("©too", None)

        tag['----:com.apple.iTunes:Fictional'] = str(self.metadata["fictional"]).encode('utf-8')
        tag['----:com.apple.iTunes:Author'] = self.metadata["author"].encode('utf-8')
        tag['----:com.apple.iTunes:Language'] = self.metadata["lang"].encode('utf-8')
        tag['----:com.apple.iTunes:Type'] = self.metadata["type"].encode('utf-8')
        tag['----:com.apple.iTunes:Season'] = str(episodeMetadata["seasonNo"]).encode('utf-8')
        if self.metadata["ageRating"]:
            tag['----:com.apple.iTunes:Age rating'] = str(self.metadata["ageRating"]).encode('utf-8')

        for cat in self.metadata['credits'].keys():
            credit = cat.replace('_', ' ').capitalize()
            tag[f'----:com.apple.iTunes:{credit}'] = self.metadata['credits'][cat].encode('utf-8')

        with open(coverPath, 'rb') as f:
            pic = MP4Cover(f.read())
            tag['covr'] = [pic]

        tag.save()

    def downAlbum(self) -> None:
        folderName = f"{self.metadata['title']} "
        folderName += f"({self.metadata['date'][:4]}) " if self.metadata.get('date') else ''
        folderName += f"[{self.metadata['lang']}]"

        albumPath = os.path.join(os.getcwd(), 'Downloads', self.metadata['lang'], self.metadata['type'], self.sanitiseName(folderName))
        os.makedirs(albumPath, exist_ok=True)

        with open(os.path.join(albumPath, 'cover.png'), 'wb') as f:
            f.write(self.session.get(self.metadata['image']).content)

        episodes = []
        page = 1
        while True:
            response = self.session.get(f'https://kukufm.com/api/v2.3/channels/{self.showID}/episodes/?page={page}')
            data = response.json()
            episodes.extend(data["episodes"])
            if not data["has_more"]:
                break
            page += 1

        for ep in episodes:
            hls_url = ep['content'].get('hls_url', '').strip()
            if not hls_url:
                print(f"✖ Skipping '{ep['title']}' — no valid URL.")
                continue

            epMeta = {
                'title': self.sanitiseName(ep["title"].strip()),
                'url': hls_url,
                'srt': ep['content'].get('subtitle_url', "").strip(),
                'epNo': ep['index'],
                'seasonNo': ep['season_no'],
                'date': str(ep.get('published_on')).strip(),
            }

            file_ext = 'mp4' if self.metadata['hasVideoEps'] else 'm4a'
            trackPath = os.path.join(albumPath, f"{str(ep['index']).zfill(2)}. {epMeta['title']}.{file_ext}")
            srtPath = os.path.join(albumPath, f"{str(ep['index']).zfill(2)}. {epMeta['title']}.srt")

            self.downloadAndTag(epMeta, trackPath, srtPath, os.path.join(albumPath, 'cover.png'))


if __name__ == '__main__':
    print(TITLE)
    parser = argparse.ArgumentParser(prog='kuku-dl', description='KuKu FM Downloader!')
    parser.add_argument('url', help="Show Url")
    args = parser.parse_args()
    KuKu(args.url).downAlbum()
