import email
import os
import random
from io import BytesIO
import sys
from zope.interface import implementer
import pickle

from twisted.cred import checkers, portal,credentials
from twisted.internet import protocol, reactor, defer
from twisted.mail import imap4, maildir
from twisted.cred import error as credError

@implementer(imap4.IAccount)
class IMAPUserAccount(object):

    def __init__(self, userDir):
        self.dir = userDir
        self.mailboxCache = {}

    def _getMailbox(self, path, create=False):

        """
        Obtiene el mailbox con la direccion otorgada.
        Crea uno si este no existe.
        """

        pathParts = path.split(".")

        if pathParts[0].lower() == 'inbox':

            pathParts[0] = 'Inbox'

        path = ".".join(pathParts)

        if not path in self.mailboxCache:

            fullPath = os.path.join(self.dir, path)

            if not os.path.exists(fullPath):

                if create:

                    maildir.initializeMaildir(fullPath)

                else:

                    raise KeyError

            self.mailboxCache[path] = IMAPMailbox(fullPath)

        return self.mailboxCache[path]

    def listMailboxes(self, ref, wildcard):
        """
        Lista los mail boxes existentes.
        """
        for box in os.listdir(self.dir):
            yield box, self._getMailbox(box)

    def select(self, path, rw=True):
        """
        Retorna un objeto implementando IMailbox para la direccion otorgada.
        """
        return self._getMailbox(path)

    def create(self, path):
        """
        Crea un mailbox en la direccion otorgada.
        """
        self._getMailbox(path, create=True)

    def delete(self, path):
        """
        Borra un mailbox en la direccion otorgada.
        """
        raise imap4.MailboxException("Permission denied.")

    def rename(self, oldname, newname):
        """
        Renombra un mailbox.
        """

        oldPath = os.path.join(self.dir, oldname)

        newPath = os.path.join(self.dir, newname)

        os.rename(oldPath, newPath)

    def subscribe(self, path):
        """
        Marca un mailbox como suscrito.
        """
        box = self._getMailbox(path)

        box.metadata['subscribed'] = True

        box.saveMetadata()

        return True

    def unsubscribe(self, path):
        """
        Marca un mailbox como no suscrito.
        """

        box = self._getMailbox(path)

        box.metadata['subscribed'] = False

        box.saveMetadata()

        return True

    def isSubscribed(self, path):
        """
        Retorna un booleano con la informacion de si se encuentra suscrito a un mailbox.
        """
        return self._getMailbox(path).metadata.get('subscribed', False)

    def select(self, path, rw=False):
        """
        Retorna el mailbox seleccionado con la direccion otorgada.
        """
        return self._getMailbox(path)

class ExtendedMaildir(maildir.MaildirMailbox):
    def __iter__(self):
        return iter(self.list)

    def __len__(self):
        return len(self.list)

    def __getitem__(self, i):
        return self.list[i]


@implementer(imap4.IMailbox)
class IMAPMailbox(object):

    def __init__(self, path):
        self.maildir = ExtendedMaildir(path)
        self.listeners = []
        self.uniqueValidityIdentifier = random.randint(1000000, 9999999)
        self.metadataFile = os.path.join(path, '.imap-metadata.pickle')

        if os.path.exists(self.metadataFile):
            self.metadata = pickle.load(open(self.metadataFile, 'r+b'))
        else:
            self.metadata = {}

            self.initMetadata()

            self.listeners = []

            self._assignUIDs()

    def initMetadata(self):
        """
        Inicia el metadata utilizado para realizar el fetch con la secuencia de user ids de los mensajes.
        """

        if not 'flags' in self.metadata:

            self.metadata['flags'] = {}

        if not 'uidvalidity' in self.metadata:


            self.metadata['uidvalidity'] = random.randint(1000000, 9999999)

        if not 'uids' in self.metadata:

            self.metadata['uids'] = {}

        if not 'uidnext' in self.metadata:

            self.metadata['uidnext'] = 1

    def saveMetadata(self):
        """
        Guarda la informacion del metadata en un archivo utilizando pickle.
        """
        pickle.dump(self.metadata, open(self.metadataFile, 'w+b'))

    def _assignUIDs(self):

        """
        Verifica que cada uno de los mensajes tenga id , este asignado y este en las estructuras que los maneja.
        """
        for messagePath in self.maildir:

            messageFile = os.path.basename(messagePath)

            if not messageFile in self.metadata['uids']:

                self.metadata['uids'][messageFile] = self.metadata['uidnext']

                self.metadata['uidnext'] += 1

                self.saveMetadata()

    def getHierarchicalDelimiter(self):
        return "."

    def getFlags(self):
        return [r'Seen', r'Unseen', r'Deleted', r'Flagged', r'Answered', r'Recent']

    def getUnseenCount(self):
        def messageIsUnseen(filename):

            filename = os.path.basename(filename)

            uid = self.metadata['uids'].get(filename)

            flags = self.metadata['flags'].get(uid, [])

            if not r'Seen' in flags:
                return True

        return len(filter(messageIsUnseen, self.maildir))

    def getMessageCount(self):
        return len(self.maildir)

    def getRecentCount(self):
        return 0

    def isWriteable(self):
        return False

    def getUIDValidity(self):
        return self.metadata['uidvalidity']

    def getUID(self, messageNum):
        filename = os.path.basename(self.maildir[messageNum - 1])
        if not filename in self.metadata['uids']:
            self._assignUIDs()
        return self.metadata['uids'][filename]

    def getUIDNext(self):
        return self.folder.metadata['uidnext']

    def _seqMessageSetToSeqDict(self, messageSet):
        if not messageSet.last:
            messageSet.last = self.getMessageCount()

        seqMap = {}
        for messageNum in messageSet:
            if messageNum >= 0 and messageNum <= self.getMessageCount():
                seqMap[messageNum] = self.maildir[messageNum - 1]
        return seqMap


    def _uidMessageSetToSeqDict(self, messageSet):

        """
        Obtiene un set de mensajes que contienen user ids y retorna un diccionario en secuencia de numeros para el
        nombre de los archivos.
        """

        if not messageSet.last:

            messageSet.last = self.metadata['uidnext']

            self._assignUIDs()

            allUIDs = []

            for filename in self.maildir:
                shortFilename = os.path.basename(filename)
                allUIDs.append(self.metadata['uids'][shortFilename])


            allUIDs.sort()

            seqMap = {}

            for uid in messageSet:

                if uid in allUIDs:

                    sequence = allUIDs.index(uid) + 1

                    seqMap[sequence] = self.maildir[sequence - 1]
            return seqMap


    def fetch(self, messages, uid):
        """
        Realiza el fetch de la carpeta de mensajes del smpt al cliente del imap utilizado.
        """
        if uid:
            messagesToFetch = self._uidMessageSetToSeqDict(messages)
        else:
            messagesToFetch = self._seqMessageSetToSeqDict(messages)
        for seq, filename in messagesToFetch.items():
            uid = self.getUID(seq)
            flags = self.metadata['flags'].get(uid, [])
            yield seq, MaildirMessage(filename,flags,uid)

    def addListener(self, listener):
        self.listeners.append(listener)

    def removeListener(self, listener):
        self.listeners.remove(listener)

    def requestStatus(self, path):
        return imap4.statusRequestHelper(self, path)

    def store(self, messageSet, flags, mode, uid):
        """
        Guarda los mensajes de la carpeta de mensajes del smpt al cliente del imap utilizado.
        """
        if uid:

            messages = self._uidMessageSetToSeqDict(messageSet)

        else:

            messages = self._seqMessageSetToSeqDict(messageSet)

            setFlags = {}

            for seq, filename in messages.items():

                uid = self.getUID(seq)

                if mode == 0:

                    messageFlags = self.metadata['flags'][uid] = flags

                else:

                    messageFlags = self.metadata['flags'].setdefault(uid, [])

            for flag in flags:

                if mode == 1 and not messageFlags.count(flag):

                    messageFlags.append(flag)

                elif mode == -1 and messageFlags.count(flag):

                    messageFlags.remove(flag)

                    setFlags[seq] = messageFlags

                    self.saveMetadata()
            return setFlags

    def expunge(self):

        """
        Elimina todos los mensajes marcados para eliminar.
        """

        removed = []

        for filename in self.maildir:

            uid = self.metadata['uids'].get(os.path.basename(filename))

            if r"Deleted" in self.metadata['flags'].get(uid, []):

                self.maildir.deleteMessage(filename)

                removed.append(uid)

        return removed

    def destroy(self):

        """
        Remueve el mailbox y sus contenidos.
        """

        raise imap4.MailboxException("Permission denied.")


@implementer(imap4.IMessage)
class MaildirMessage(object):

    def __init__(self, messageData,flags,uid):
        self.flags = flags
        self.uid = uid
        with open(messageData, 'r') as file:
            data = file.read()
        self.data = data
        self.message = email.message_from_string(data)

    def getHeaders(self, negate, *names):
        if not names:
            names = self.message.keys()
        headers = {}
        if negate:
            for header in self.message.keys():
                if header.upper() not in names:
                    if type(header) != str:
                        header = header.decode("utf-8")
                    headers[header.lower()] = self.message.get(header, '')
        else:
            for name in names:
                if type(name) != str:
                    name = name.decode("utf-8")
                headers[name.lower()] = self.message.get(name, '')
        return headers

    def getInternalDate(self):
        return self.message.get('Date', '')

    def getBodyFile(self):
        bodyData = self.message.get_payload()
        return BytesIO(bodyData.encode())

    def isMultipart(self):
        return self.message.is_multipart()

    def getFlags(self):
        return self.flags

    def getUID(self):
        return self.uid

    def getSize(self):
        return len(self.data)

@implementer(portal.IRealm)
class MailUserRealm(object):

    def __init__(self, baseDir):
        self.baseDir = baseDir

    def requestAvatar(self, avatarId, mind, *interfaces):
        if imap4.IAccount not in interfaces:
            raise NotImplementedError(
                "This realm only supports the imap4.IAccount interface.")

        userDir = os.path.join(self.baseDir, avatarId.decode("utf-8"))
        avatar = IMAPUserAccount(userDir)
        print(avatar)
        return imap4.IAccount, avatar, lambda: None

def passwordFileToDict(filename):
    """
    Convierte el archivo de credenciales permitidos en un diccionario para su manejo.
    """
    passwords = {}

    file = open(filename, 'r')
    for line in file:

        if line and line.count(':'):

            username, password = line.strip().split(':')

            passwords[bytes(username,"utf-8")] = bytes(password,"utf-8")

    return passwords

@implementer(checkers.ICredentialsChecker)
class CredentialsChecker(object):

    credentialInterfaces = (credentials.IUsernamePassword,credentials.IUsernameHashedPassword)

    def __init__(self, passwords):

        self.passwords = passwords


    def requestAvatarId(self, credentials):

        """
        Verifica si las credenciales otorgadas son validas.
        """

        username = credentials.username

        if username in self.passwords:

             realPassword = self.passwords[username]

             checking = defer.maybeDeferred(credentials.checkPassword, realPassword)

             checking.addCallback(self._checkedPassword, username)

             return checking

        else:
            raise credError.UnauthorizedLogin("No such user")



    def _checkedPassword(self, matched, username):

        if matched:
            return username

        else:

            raise credError.UnauthorizedLogin("Bad password")

class IMAPServerProtocol(imap4.IMAP4Server):
  def lineReceived(self, line):
      print("CLIENT:", line)
      imap4.IMAP4Server.lineReceived(self, line)

  def sendLine(self, line):
      imap4.IMAP4Server.sendLine(self, line)
      print("SERVER:", line)

class IMAPFactory(protocol.Factory):
    def __init__(self, portal):
        self.portal = portal

    def buildProtocol(self, addr):
        proto = IMAPServerProtocol()
        proto.portal = portal
        return proto

#python3 IMAPserver.py -s <mail-storage> -p <port>
if __name__=='__main__':
    dataDir = sys.argv[2]

    port = int(sys.argv[4])

    portal = portal.Portal(MailUserRealm(dataDir))

    passwordFile = os.path.join(dataDir, 'passwords.txt')

    passwords = passwordFileToDict(passwordFile)

    passwordChecker = CredentialsChecker(passwords)

    portal.registerChecker(passwordChecker)
    reactor.listenTCP(port, IMAPFactory(portal))
    reactor.run()