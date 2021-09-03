import sys
from twisted.mail import smtp, maildir
from twisted.internet import protocol, reactor
from zope.interface import implementer
import os
from email.header import Header



@implementer(smtp.IMessage)
class MaildirMessageWriter(object):
    """
    handles the local delivery to a maildir inbox
    """
    def __init__(self, user):

        if not os.path.exists(userDir):
            os.mkdir(userDir)
        # we create a directory for this user
        destDir = os.path.join(userDir,str(user.dest))
        if not os.path.exists(destDir):
            os.mkdir(destDir)

        inboxDir = os.path.join(destDir, 'Inbox')
        self.mailbox = maildir.MaildirMailbox(inboxDir)
        self.lines = []

    def lineReceived(self, line):
        if type(line) != str:
            line = line.decode("utf-8")
        self.lines.append(line)

    def eomReceived(self):
        # message is complete, store it
        self.lines.append('')
        messageData = '\n'.join(self.lines)
        return self.mailbox.appendMessage(bytes(messageData,'utf-8'))

    def connectionLost(self):
        # unexpected loss of connectio, don't save
        del self.lines

@implementer(smtp.IMessageDelivery)
class LocalDelivery(object):

    def __init__ (self, userDir ,validDomains):
        self.validDomains = validDomains
        self.userDir = userDir

    def receivedHeader (self, helo, origin, recipients):
        # client is how the client ident'ed itself
        # clientIP is the ip of the client side's end
        # we could do a reverse DNS lookup and check if it's true
        # also check on RBL's and such
        client, clientIP= helo
        recipient = recipients[0]
        # this must be our CNAME
        myself= 'localhost'
        value= """from %s [%s] by %s with SMTP for %s; %s""" % (
            client.decode("utf-8"), clientIP.decode("utf-8"), myself, recipient, smtp.rfc822date().decode("utf-8")
            )
        print("Server ready.")
        print("Waiting for connections...")
        print()
        return "Received: %s" % Header(value)

    def validateFrom (self, helo, originAddress):
        self.client = helo
        # originAddress is a twisted.mail.smtp.Address
        # if the from is invalid, we should
        # raise smtp.SMTPBadSender
        return originAddress

    def validateTo(self, user):
        if user.dest.domain.decode("utf-8") in self.validDomains:
            print("Domain: %s accepted" % user.dest.domain.decode("utf-8"))
            print()
            return lambda: MaildirMessageWriter(user)
        else:
            print("Domain: %s not listed" % user.dest.domain.decode("utf-8"))
            print("Domains available:")
            print(self.validDomains)
            print()
            print("Server ready.")
            print("Waiting for connections...")
            print()
            raise smtp.SMTPBadRcpt(user)

class SMTPFactory (protocol.ServerFactory):
    def __init__(self, userDir ,validDomains):
        print("Server ready.")
        print("Waiting for connections...")
        print()
        self.validDomains = validDomains
        self.userDir = userDir

    def buildProtocol(self, addr):
        delivery = LocalDelivery(self.userDir,self.validDomains)
        smtpProtocol = smtp.SMTP(delivery)
        smtpProtocol.factory = self
        return smtpProtocol

if __name__=='__main__':
    userDir = sys.argv[1]
    domains = sys.argv[2].split(',')
    reactor.listenTCP(2525, SMTPFactory(userDir,domains))
    reactor.run()