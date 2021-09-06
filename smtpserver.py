import sys
from twisted.mail import smtp, maildir
from twisted.internet import protocol, reactor
from zope.interface import implementer
import os
from email.header import Header
from twisted.names import client

from twisted.mail import relaymanager

mxCalc = relaymanager.MXCalculator()

def getSMTPServer(domain):
    """
    Imprime el nombre del smpt server del dominio ingresado
    """
    return print(mxCalc.getMX(domain).name)

def printResult(address, hostname):
    """
    Imprime la direccion ip si fue encontrada
    """
    if address:
        sys.stdout.write(address + '\n')
    else:
        sys.stderr.write(
            'ERROR: No IP addresses found for name %r\n' % (hostname,))


@implementer(smtp.IMessage)
class MaildirMessageWriter(object):

    def __init__(self, user):

        if not os.path.exists(userDir):
            os.mkdir(userDir)

        destDir = os.path.join(userDir,str(user.dest))
        if not os.path.exists(destDir):
            os.mkdir(destDir)

        inboxDir = os.path.join(destDir, 'Inbox')
        self.mailbox = maildir.MaildirMailbox(inboxDir)
        self.lines = []

    def lineReceived(self, line):
        """
        Recibe informacion de la comunicacion con el cliente.
        """
        if type(line) != str:
            line = line.decode("utf-8")
        self.lines.append(line)

    def eomReceived(self):
        """
        Guarda el mensaje cuando esta listo.
        """
        self.lines.append('')
        messageData = '\n'.join(self.lines)
        return self.mailbox.appendMessage(bytes(messageData,'utf-8'))

    def connectionLost(self):
        """
        Elimina las lineas guardadas ya que se perdio la conexion.
        """
        del self.lines

@implementer(smtp.IMessageDelivery)
class LocalDelivery(object):

    def __init__ (self, userDir ,validDomains):
        self.validDomains = validDomains
        self.userDir = userDir

    def receivedHeader (self, helo, origin, recipients):
        """
        Recibe los headers del mensaje y los devuelve en el formato especificado.
        """
        client, clientIP= helo
        recipient = recipients[0]
        # this must be our CNAME
        myself= 'localhost'
        value= """from %s [%s] by %s with SMTP for %s; %s""" % (
            client.decode("utf-8"), clientIP.decode("utf-8"), myself, recipient, smtp.rfc822date().decode("utf-8")
            )
        return "Received: %s" % Header(value)

    def validateFrom (self, helo, originAddress):
        """
        Valida el dominio del from.
        """
        self.client = helo
        return originAddress

    def validateTo(self, user):
        """
        Valida el dominio del to.
        """
        if user.dest.domain.decode("utf-8") in self.validDomains:
            print("Domain: %s accepted" % user.dest.domain.decode("utf-8"))
            print()
            print("Server ready.")
            print("Waiting for connections...")
            print()
            return lambda: MaildirMessageWriter(user)
        else:
            '''
            Descomentar para conocer el ip y nombre del server de un dominio no aceptado.
            
            d = client.getHostByName(user.dest.domain.decode("utf-8"))
            d.addCallback(printResult, user.dest.domain.decode("utf-8"))
            
            getSMTPServer(user.dest.domain.decode("utf-8"))
            '''
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
        """
        Prepara el protocolo smpt para la recepcion de correo.
        """
        delivery = LocalDelivery(self.userDir,self.validDomains)
        smtpProtocol = smtp.SMTP(delivery)
        smtpProtocol.factory = self
        return smtpProtocol

#python3 smtpserver.py -d <domains> -s <mail-storage> -p <port>
if __name__=='__main__':
    domains = sys.argv[2].split(',')
    userDir = sys.argv[4]
    port = int(sys.argv[6])
    reactor.listenTCP(port, SMTPFactory(userDir,domains))
    reactor.run()