import json
import logging
from typing import Tuple, List, Dict
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from pathlib import Path
from telebot import TeleBot
from telebot.types import Message, Update
from twisted.internet import reactor, ssl
from twisted.web.resource import Resource, ErrorPage
from twisted.web.server import Site
from youtube_dl import YoutubeDL
from youtube_dl.postprocessor.common import PostProcessor
from youtube_dl.utils import UnsupportedError, DownloadError
from ydl_bot.utils import get_or_create_root_cert
logger = logging.getLogger(__name__)


def get_options_audio(path: Path):
    return {
        'format': 'bestaudio',
        'max_filesize': 50*1024*1024,
        'noplaylist': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
        }],
        'outtmpl': str(path / f'%(title)s-{uuid4()}.%(ext)s')
    }


def get_rate_limit() -> Tuple[int, int]:  # X requests per Y minutes
    return 5, 5


class UploadHandler(PostProcessor):
    def __init__(self, bot, msg_id, chat_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot  # type: TeleBot
        self.msg_id = msg_id
        self.chat_id = chat_id

    def run(self, information):
        self.bot.edit_message_text('Uploading', message_id=self.msg_id, chat_id=self.chat_id)
        with open(information['filepath'], 'rb') as f:
            self.bot.send_audio(self.chat_id, f, reply_to_message_id=self.msg_id, title=information['title'])
        return [information['filepath']], information


class TelegramBot:
    def __init__(self, work_dir: Path, token: str):
        self.last_requests = {}  # type: Dict[int, List[datetime]]
        self.work_dir = work_dir
        self.work_dir.mkdir(0o755, parents=True, exist_ok=True)
        self.token = token
        self.bot = TeleBot(token)
        self.bot.add_message_handler({
            'function': self.process_link,
            'filters': {
                'regexp': r'https?:\/\/.+\..+'
            }
        })
        self.bot.add_message_handler({
            'function': self.process_message,
            'filters': {
                'func': lambda _: True
            }
        })

    def process_link(self, message: Message):
        user_id = message.from_user.id
        if user_id not in self.last_requests:
            self.last_requests[user_id] = []
        limit_req, limit_min = get_rate_limit()
        now = datetime.now(tz=timezone.utc)
        last_requests = []
        for dt in self.last_requests[user_id]:
            time_passed = now - dt
            if time_passed.min < timedelta(minutes=limit_min):
                last_requests.append(dt)
        self.last_requests[user_id] = last_requests

        if len(self.last_requests[user_id]) > limit_req:
            next_available = self.last_requests[user_id][0] + timedelta(minutes=limit_min) - now
            self.bot.reply_to(message, f'Rate limited. Try again in {next_available.seconds} seconds')
            return
        else:
            self.last_requests[user_id].append(now)
        msg = self.bot.reply_to(message, "Link detected, processing")

        # detach from telebot update thread
        def download():
            try:
                with YoutubeDL({'noplaylist': True}) as ydl:
                    info = ydl.extract_info(message.text, download=False)
                    if info['duration'] > 900:
                        self.bot.edit_message_text('Source too long', message_id=msg.id, chat_id=msg.chat.id)
                        return
                with YoutubeDL(get_options_audio(self.work_dir)) as ydl:
                    ydl.add_post_processor(UploadHandler(self.bot, msg.id, msg.chat.id))
                    self.bot.edit_message_text('Downloading', message_id=msg.id, chat_id=msg.chat.id)
                    ydl.download([message.text])
            except UnsupportedError:
                self.bot.edit_message_text('Unsupported URL', message_id=msg.id, chat_id=msg.chat.id)
            except DownloadError:
                self.bot.edit_message_text('Download error', message_id=msg.id, chat_id=msg.chat.id)
            except Exception as e:
                self.bot.edit_message_text('Unknown error', message_id=msg.id, chat_id=msg.chat.id)
                logger.error('Unknown error', exc_info=e)
        reactor.callInThread(lambda: download())

    def process_message(self, message: Message):
        self.bot.reply_to(message, 'Send me a link')

    def polling(self):
        self.bot.delete_webhook()
        self.bot.polling(long_polling_timeout=5)

    def stop_polling(self):
        self.bot.stop_polling()

    def set_webhook(self, host: str, port: int):
        cert_path, pkey_path = get_or_create_root_cert(self.work_dir, host)
        self.bot.remove_webhook()
        self.bot.set_webhook(url=f'https://{host}:{port}/{self.token}/', certificate=open(cert_path, 'r'))
        bot = self.bot

        class WebhookHandler(Resource):
            isLeaf = True

            def render_POST(self, request):
                request_body_dict = json.load(request.content)
                update = Update.de_json(request_body_dict)
                reactor.callInThread(lambda: bot.process_new_updates([update]))
                return b''

        root = ErrorPage(403, 'Forbidden', '')
        root.putChild(self.token.encode(), WebhookHandler())
        site = Site(root)
        sslcontext = ssl.DefaultOpenSSLContextFactory(str(pkey_path), str(cert_path))
        reactor.listenSSL(port, site, sslcontext)
