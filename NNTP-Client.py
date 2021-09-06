from twisted.news import nntp

from twisted.internet import protocol, defer

import time, email
import os

articles = 1

class NNTPGroupDownloadProtocol(nntp.NNTPClient):

 def connectionMade(self):

    nntp.NNTPClient.connectionMade(self)

    self.fetchGroup(self.factory.newsgroup)



 def gotGroup(self, groupInfo):

    articleCount, first, last, groupName, typ ,state = groupInfo

    first = int(first)

    last = int(last)

    start = max(first, last-self.factory.articleCount)

    self.articlesToFetch = range(start+1, last+1)

    self.articleCount = len(self.articlesToFetch)

    print(str(self.articleCount) + " Articles Found.\n")

    value = raw_input("Would you like to download them? y,n \n")
    if value == "y":
        self.fetchNextArticle()
    else:
        print("Exiting...")
        reactor.stop()


 def fetchNextArticle(self):

     if self.articlesToFetch:

         nextArticleIdx = self.articlesToFetch.pop(0)

         print("Fetching article %i of %i..." % (

         self.articleCount-len(self.articlesToFetch),

         self.articleCount),

         self.fetchArticle(nextArticleIdx))

     else:

         self.quit( )

         self.factory.deferred.callback(0)



 def gotArticle(self, article):

     print("OK")

     self.factory.handleArticle(article)

     self.fetchNextArticle()



 def getArticleFailed(self, errorMessage):

     print(errorMessage)

     self.fetchNextArticle( )



 def getGroupFailed(self, errorMessage):

     self.factory.deferred.errback(Exception(errorMessage))

     self.quit( )

     self.transport.loseConnection( )



 def connectionLost(self, error):

    if not self.factory.deferred.called:
        self.factory.deferred.errback(error)



class NNTPGroupDownloadFactory(protocol.ClientFactory):

 protocol = NNTPGroupDownloadProtocol



 def __init__(self, newsgroup, articleCount=10):

     self.newsgroup = newsgroup

     self.articleCount = articleCount

     if not os.path.exists(output_storage):
         os.mkdir(output_storage)

     self.deferred = defer.Deferred()



 def handleArticle(self, articleData):
     global articles
     parsedMessage = email.message_from_string(articleData)
     output = os.path.join(output_storage, "Article "+ str(articles))
     articles+=1
     out_file = file(output, 'w+b')
     out_file.write(parsedMessage.as_string(unixfrom=True))
     out_file.write('')



if __name__ == "__main__":

 from twisted.internet import reactor

 import sys



 def handleError(error):

     print >> sys.stderr, error.getErrorMessage( )

     reactor.stop( )



 if len(sys.argv) != 4:

     print >> sys.stderr, "Usage: %s nntpserver newsgroup outputfile"

     sys.exit(1)

 server, newsgroup, output_storage = sys.argv[1:4]

 factory = NNTPGroupDownloadFactory(newsgroup)

 factory.deferred.addCallback(lambda _: reactor.stop( )).addErrback(handleError)

 reactor.connectTCP(server, 1199, factory)

 reactor.run( )