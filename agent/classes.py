class Identity:
    def __init__(self, name="", phone_number="", email="", age="", country="",
                 username="", password="", address="", birth="", gender="",
                 card_num="", card_date="", company="", iban="", verification_num=0,
                 ssn="", city="", state="", post_code="", first_name="", last_name="",
                 job_title="", swift_bic="", bank_account="", card_cvv=""):
        self.name = name
        self.phone_number = phone_number
        self.email = email
        self.age = age
        self.country = country
        self.username = username
        self.address = address
        self.birth = birth
        self.gender = gender
        self.password = password
        self.verification_num = verification_num
        self.company = company
        self.card_num = card_num
        self.card_date = card_date
        self.iban = iban
        # Extended fields (generate-random.org)
        self.ssn = ssn
        self.city = city
        self.state = state
        self.post_code = post_code
        self.first_name = first_name
        self.last_name = last_name
        self.job_title = job_title
        self.swift_bic = swift_bic
        self.bank_account = bank_account
        self.card_cvv = card_cvv


class Mail:
    def __init__(self, from_address="", to_address="", identity_o=None,
                 subject="", mail_body="", thread_id="", msg_id="",
                 uid="", folder="INBOX"):
        self.from_address = from_address
        self.identity = identity_o if identity_o is not None else Identity()
        self.to_address = to_address
        self.subject = subject
        self.mail_body = mail_body
        self.thread_id = thread_id
        self.msg_id = msg_id
        # IMAP fields (unused by the Gmail API path; defaults keep it backward-compatible)
        self.uid = uid
        self.folder = folder


class Conversation_Thread:
    def __init__(self, sender_acc="", scammer_acc=None, thread_id="",
                 conversation=None, scammer_id="", scam_level="", account_history=""):
        self.sender_acc = sender_acc
        self.scammer_acc = scammer_acc if scammer_acc is not None else []
        self.conversation = conversation if conversation is not None else []
        self.scammer_id = scammer_id
        self.scam_level = scam_level
        self.account_history = account_history
        self.thread_id = thread_id
