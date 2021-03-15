import hashlib
from base64 import b64encode, b64decode


class Identity:
    def __init__(self,name="",phone_number="",email="",age="",country="",username="",password="",address="",birth="",gender="",card_num="",card_date="",company="",verification_num=0):
        self.name = name
        self.phone_number = phone_number
        self.email = email
        self.age = age
        self.country = country
        self.username = username
        self.address = address
        self.birth = birth
        self.gender = gender
        #self.password = b64encode(hashlib.md5(str(password)).digest)
        self.password = password
        self.verification_num = 0
        self.company = company
        self.card_num = card_num
        self.card_date = card_date

class Mail:
    def __init__(self,from_address="",to_address="",identity_o=Identity(),subject='',mail_body='',thread_id='',msg_id=''):
        self.from_address = from_address
        self.identity = identity_o
        self.to_address = to_address
        self.subject = subject
        self.mail_body = mail_body
        self.thread_id = thread_id
        self.msg_id =msg_id


class Conversation_Thread:
    def __init__(self,sender_acc="",scammer_acc=[],thread_id="",conversation=[Mail()],scammer_id="",scam_level="",account_history=""):
        self.sender_acc = sender_acc
        self.scammer_acc = scammer_acc
        self.conversation = conversation
        self.scammer_id = scammer_id
        self.scam_level = scam_level
        self.account_history = account_history
        self.thread_id = thread_id
