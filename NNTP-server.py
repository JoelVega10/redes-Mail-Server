from twisted.internet import reactor

from twisted.news import database, news, nntp

GROUPS = ['local.Inbox']

SMTP_SERVER = 'localhost'

STORAGE_DIR = 'mail_storage'

newsStorage = database.NewsShelf(SMTP_SERVER, STORAGE_DIR)

for group in GROUPS:

    newsStorage.addGroup(group, [])

factory = news.NNTPFactory(newsStorage)

reactor.listenTCP(1199, factory)

reactor.run()