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
from twisted.python import filepath
from twisted.python import log

@implementer(imap4.IAccount)
class IMAPUserAccount(object):

    def __init__(self, userDir):
        self.dir = userDir
        self.mailboxCache = {}

    def _getMailbox(self, path, create=False):

        """

        Helper function to get a mailbox object at the given

        path, optionally creating it if it doesn't already exist.

        """

        # According to the IMAP spec, Inbox is case-insensitive

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
        for box in os.listdir(self.dir):
            yield box, self._getMailbox(box)

    def select(self, path, rw=True):

        "return an object implementing IMailbox for the given path"

        return self._getMailbox(path)

    def create(self, path):

        "create a mailbox at path and return it"

        self._getMailbox(path, create=True)

    def delete(self, path):

        "delete the mailbox at path"

        raise imap4.MailboxException("Permission denied.")

    def rename(self, oldname, newname):

        "rename a mailbox"

        oldPath = os.path.join(self.dir, oldname)

        newPath = os.path.join(self.dir, newname)

        os.rename(oldPath, newPath)

    def subscribe(self, path):

        "mark a mailbox as subscribed"

        box = self._getMailbox(path)

        box.metadata['subscribed'] = True

        box.saveMetadata()

        return True

    def unsubscribe(self, path):

        "mark a mailbox as unsubscribed"

        box = self._getMailbox(path)

        box.metadata['subscribed'] = False

        box.saveMetadata()

        return True

    def isSubscribed(self, path):

        "return a true value if user is subscribed to the mailbox"

        return self._getMailbox(path).metadata.get('subscribed', False)

    def select(self, path, rw=False):
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

        if not 'flags' in self.metadata:

            self.metadata['flags'] = {}  # dict of message IDs to flags

        if not 'uidvalidity' in self.metadata:

            # create a unique integer ID to identify this version of

            # the mailbox, so the client could tell if it was deleted

            # and replaced by a different mailbox with the same name

            self.metadata['uidvalidity'] = random.randint(1000000, 9999999)

        if not 'uids' in self.metadata:

            self.metadata['uids'] = {}

        if not 'uidnext' in self.metadata:

            self.metadata['uidnext'] = 1  # next UID to be assigned

    def saveMetadata(self):

        pickle.dump(self.metadata, open(self.metadataFile, 'w+b'))

    def _assignUIDs(self):

        # make sure every message has a uid

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

        take a MessageSet object containing UIDs, and return

        a dictionary mapping sequence numbers to filenames

        """

        # if messageSet.last is None, it means 'the end', and needs to

        # be set to a sane high number before attempting to iterate

        # through the MessageSet

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

                # the message set covers a span of UIDs. not all of them

                # will necessarily exist, so check each one for validity

                if uid in allUIDs:

                    sequence = allUIDs.index(uid) + 1

                    seqMap[sequence] = self.maildir[sequence - 1]

            return seqMap


    def fetch(self, messages, uid):
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

    def expunge(self):

        "remove all messages marked for deletion"

        removed = []

        for filename in self.maildir:

            uid = self.metadata['uids'].get(os.path.basename(filename))

            if r"Deleted" in self.metadata['flags'].get(uid, []):

                self.maildir.deleteMessage(filename)

                # you could also throw away the metadata here

                removed.append(uid)

        return removed

    def destroy(self):

        "complete remove the mailbox and all its contents"

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

        "passwords: a dict-like object mapping usernames to passwords"

        self.passwords = passwords


    def requestAvatarId(self, credentials):

        """

        check to see if the supplied credentials authenticate.

        if so, return an 'avatar id', in this case the name of

        the IMAP user.

        The supplied credentials will implement one of the classes

        in self.credentialInterfaces. In this case both

        IUsernamePassword and IUsernameHashedPassword have a

        checkPassword method that takes the real password and checks

        it against the supplied password.

        """

        username = credentials.username

        if username in self.passwords:

             realPassword = self.passwords[username]

             checking = defer.maybeDeferred(credentials.checkPassword, realPassword)

             # pass result of checkPassword, and the username that was

             # being authenticated, to self._checkedPassword

             checking.addCallback(self._checkedPassword, username)

             return checking

        else:
            raise credError.UnauthorizedLogin("No such user")



    def _checkedPassword(self, matched, username):

        if matched:
            # password was correct
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


dataDir = sys.argv[1]

portal = portal.Portal(MailUserRealm(dataDir))

passwordFile = os.path.join(dataDir, 'passwords.txt')

passwords = passwordFileToDict(passwordFile)

passwordChecker = CredentialsChecker(passwords)

portal.registerChecker(passwordChecker)
reactor.listenTCP(1433, IMAPFactory(portal))
reactor .run()