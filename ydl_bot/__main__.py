from twisted.internet import reactor

# should be handled by start.py script:
# 1) copying from example config
# 2) setting current workdir for importing
from config import global_config as cfg
from ydl_bot.telegram import TelegramBot

BASE_DIR = cfg['work_dir']

if __name__ == '__main__':
    tgbot = TelegramBot(BASE_DIR / 'telegram', cfg['telegram']['token'])

    if 'webhook' in cfg['telegram']:
        wh = cfg['telegram']['webhook']
        tgbot.set_webhook(wh['host'], wh['port'])
    else:
        reactor.addSystemEventTrigger('before', 'shutdown', lambda: tgbot.stop_polling())
        reactor.callInThread(lambda: tgbot.polling())

    reactor.suggestThreadPoolSize(10)
    reactor.run()
