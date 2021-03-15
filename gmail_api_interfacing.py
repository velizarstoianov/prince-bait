import pickle
import os
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import email.mime
import classes

def authorize():
    # If modifying these scopes, delete the file token.pickle.
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly','https://www.googleapis.com/auth/gmail.send','https://www.googleapis.com/auth/gmail.modify','https://www.googleapis.com/auth/gmail.settings.basic','https://www.googleapis.com/auth/gmail.settings.sharing']
    CLIENT_SECRET_FILE = 'credentials.json'

    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds
############## get_mailbox_unread function begins #################################################################################
def get_mailbox_unread():
    creds = authorize()
    mailbox = []
    service = build('gmail', 'v1', credentials=creds)
    threads = service.users().threads().list(userId="johntest@thepublicmail.com").execute().get('threads', [])
    for thread in threads:
        temp_thread = classes.Conversation_Thread()
        thread_data = service.users().threads().get(userId="johntest@thepublicmail.com", id=thread['id']).execute()
        messages_in_thread = thread_data["messages"]
        temp_thread.thread_id = thread_data["id"]
        for message_in_thread in messages_in_thread:
            if('UNREAD' not in message_in_thread["labelIds"] or 'INBOX' not in message_in_thread["labelIds"]):
                continue
            ##Fill message object list
            message_obj = classes.Mail()
            message_payload = message_in_thread.get("payload")
            payload_headers = message_payload.get("headers")
            sender=""
            subject=""
            rec_mail=""
            msg_id=""
            for header in payload_headers:
                header_name = str(header.get("name")).lower()
                if (header_name == "from"):
                    sender = header.get("value")
                    continue
                if (header_name == "subject"):
                    subject = header.get("value")
                    continue
                if (header_name == "to"):
                    rec_mail = header.get("value")
                    continue
                if (header_name == "message-id"):
                    msg_id = header.get("value")
                    continue
            message_parts = message_payload.get("parts")
            if(len(message_parts)==2):
                base64_body=message_parts[0].get("body").get("data")
                if(len(base64_body)>=1):
                    mail_body = base64.urlsafe_b64decode(bytes(base64_body,'utf-8'))
        ##--->From
            message_obj.from_address = sender
        ##--->In reply to
        ##--->subject
            message_obj.subject = subject
        ##--->to
            message_obj.to_address = rec_mail
        ##--->thread id
            message_obj.thread_id = str(message_in_thread.get("threadId"))
            message_obj.mail_body = str(mail_body.decode('utf-8'))
            message_obj.msg_id = str(msg_id)

            if (message_obj.from_address not in temp_thread.scammer_acc):
                temp_thread.scammer_acc.append(message_obj.from_address)
            temp_thread.conversation.append(message_obj)
            temp_thread.sender_acc = message_obj.to_address
        mailbox.append(temp_thread)
    return mailbox
############## get_mailbox_unread function ends ###################################################################################

############## get_mailbox_full function begins####################################################################################
def get_mailbox_full():
    creds = authorize()
    mailbox = []
    service = build('gmail', 'v1', credentials=creds)
    threads = service.users().threads().list(userId="johntest@thepublicmail.com").execute().get('threads', [])
    for thread in threads:
        temp_thread = classes.Conversation_Thread()
        thread_data = service.users().threads().get(userId="johntest@thepublicmail.com", id=thread['id']).execute()
        messages_in_thread = thread_data["messages"]
        temp_thread.thread_id = thread_data["id"]
        for message_in_thread in messages_in_thread:
            if('INBOX' not in message_in_thread["labelIds"]):
                continue
            ##Fill message object list
            message_obj = classes.Mail()
            message_payload = message_in_thread.get("payload")
            payload_headers = message_payload.get("headers")
            sender=""
            subject=""
            rec_mail=""
            msg_id=""
            for header in payload_headers:
                header_name = str(header.get("name")).lower()
                if (header_name == "from"):
                    sender = header.get("value")
                    continue
                if (header_name == "subject"):
                    subject = header.get("value")
                    continue
                if (header_name == "to"):
                    rec_mail = header.get("value")
                    continue
                if (header_name == "message-id"):
                    msg_id = header.get("value")
                    continue
            message_parts = message_payload.get("parts")
            if(len(message_parts)==2):
                base64_body=message_parts[0].get("body").get("data")
                if(len(base64_body)>=1):
                    mail_body = base64.urlsafe_b64decode(bytes(base64_body,'utf-8'))
        ##--->From
            message_obj.from_address = sender
        ##--->In reply to
        ##--->subject
            message_obj.subject = subject
        ##--->to
            message_obj.to_address = rec_mail
        ##--->thread id
            message_obj.thread_id = str(message_in_thread.get("threadId"))
            message_obj.mail_body = str(mail_body.decode('utf-8'))
            message_obj.msg_id = str(msg_id)

            if (message_obj.from_address not in temp_thread.scammer_acc):
                temp_thread.scammer_acc.append(message_obj.from_address)
            temp_thread.conversation.append(message_obj)
            temp_thread.sender_acc = message_obj.to_address
        mailbox.append(temp_thread)
    return mailbox
############## get_mailbox_full function ends #####################################################################################

############## get_last_mails_unread begins ######################################################################################
def get_last_mails_unread():
    creds = authorize()
    last_mails = []
    service = build('gmail', 'v1', credentials=creds)
    threads = service.users().threads().list(userId="johntest@thepublicmail.com").execute().get('threads', [])
    for thread in threads:
        thread_data = service.users().threads().get(userId="johntest@thepublicmail.com", id=thread['id']).execute()
        messages_in_thread = thread_data["messages"]
        #for message_in_thread in messages_in_thread:
        message_in_thread = messages_in_thread[-1]
        if(('UNREAD' not in message_in_thread["labelIds"]) or ('INBOX' not in message_in_thread["labelIds"])):
            continue
        ##Fill message object list
        message_obj = classes.Mail()
        message_payload = message_in_thread.get("payload")
        payload_headers = message_payload.get("headers")
        sender=""
        subject=""
        rec_mail=""
        msg_id=""
        for header in payload_headers:
            header_name = str(header.get("name")).lower()
            if (header_name == "from"):
                sender = header.get("value")
                continue
            if (header_name == "subject"):
                subject = header.get("value")
                continue
            if (header_name == "to"):
                rec_mail = header.get("value")
                continue
            if (header_name == "message-id"):
                msg_id = header.get("value")
                continue
        message_parts = message_payload.get("parts")
        if(len(message_parts)==2):
            base64_body=message_parts[0].get("body").get("data")
            if(len(base64_body)>=1):
                mail_body = base64.urlsafe_b64decode(bytes(base64_body,'utf-8'))
    ##--->From
        message_obj.from_address = sender
    ##--->In reply to
    ##--->subject
        message_obj.subject = subject
    ##--->to
        message_obj.to_address = rec_mail
    ##--->thread id
        message_obj.thread_id = str(message_in_thread.get("threadId"))
        message_obj.mail_body = str(mail_body.decode('utf-8'))
        message_obj.msg_id = str(msg_id)

       
        last_mails.append(message_obj)
    return last_mails
############## get_last_mails_unread ends ########################################################################################

############## get_last_mails begins #############################################################################################
def get_last_mails():
    creds = authorize()
    last_mails = []
    service = build('gmail', 'v1', credentials=creds)
    threads = service.users().threads().list(userId="johntest@thepublicmail.com").execute().get('threads', [])
    for thread in threads:
        thread_data = service.users().threads().get(userId="johntest@thepublicmail.com", id=thread['id']).execute()
        messages_in_thread = thread_data["messages"]
        #for message_in_thread in messages_in_thread:
        message_in_thread = messages_in_thread[-1]
        if('INBOX' not in message_in_thread["labelIds"]):
            continue
        ##Fill message object list
        message_obj = classes.Mail()
        message_payload = message_in_thread.get("payload")
        payload_headers = message_payload.get("headers")
        sender=""
        subject=""
        rec_mail=""
        msg_id=""
        for header in payload_headers:
            header_name = str(header.get("name")).lower()
            if (header_name == "from"):
                sender = header.get("value")
                continue
            if (header_name == "subject"):
                subject = header.get("value")
                continue
            if (header_name == "to"):
                rec_mail = header.get("value")
                continue
            if (header_name == "message-id"):
                msg_id = header.get("value")
                continue
        message_parts = message_payload.get("parts")
        if(len(message_parts)==2):
            base64_body=message_parts[0].get("body").get("data")
            if(len(base64_body)>=1):
                mail_body = base64.urlsafe_b64decode(bytes(base64_body,'utf-8'))
    ##--->From
        message_obj.from_address = sender
    ##--->In reply to
    ##--->subject
        message_obj.subject = subject
    ##--->to
        message_obj.to_address = rec_mail
    ##--->thread id
        message_obj.thread_id = str(message_in_thread.get("threadId"))
        message_obj.mail_body = str(mail_body.decode('utf-8'))
        message_obj.msg_id = str(msg_id)

       
        last_mails.append(message_obj)
    return last_mails
############# get_last_mails ends ################################################################################################

############# reply_to_mail begins###############################################################################################
def reply_to_mail(reply_text, mail_to_reply = classes.Mail()):
    message = MIMEMultipart()
    creds = authorize()
    service = build('gmail', 'v1', credentials=creds)
    message['to'] = mail_to_reply.from_address
    message['From'] = mail_to_reply.to_address
    message['from'] = mail_to_reply.to_address
    message['sendAsEmail'] = mail_to_reply.to_address
    message['In-Reply-To'] = mail_to_reply.from_address
    message['Subject'] = "Re:"+mail_to_reply.subject
    message["Message-ID"] = mail_to_reply.msg_id
    msg = MIMEText(reply_text, 'html')
    message.attach(msg)
    message['ThreadId'] = mail_to_reply.thread_id
    message['thread-id'] = mail_to_reply.thread_id
    msg_to_send = {'raw': base64.urlsafe_b64encode(message.as_string().encode()).decode(), 'threadID':str(mail_to_reply.thread_id)}
    service.users().messages().send(userId='me',body=msg_to_send).execute()
#    service.users().settings().sendAs().patch(userId='me',sendAsEmail='doglover <doglover45@thepublicmail.com>',body=msg_to_send).execute()



#    service.users().messages().send(userId=mail_to_reply.to_address,body=msg_to_send).execute()
############# reply_to_mail ends ################################################################################################
############# remove_mail_lable ##########addd trycatch#######################################################################################
def remove_mail_label(thread_id="",remove="UNREAD",user_id=""):
    if(remove!='UNREAD' ):
        if(remove!='READ'):
            return
    creds = authorize()
    service = build('gmail', 'v1', credentials=creds)
    service.users().messages().modify(userId=user_id, id=thread_id, body={'removeLabelIds': [str(remove)]}).execute()
############ remove_mail_label ends #############################################################################################
############ add_mail_label begins ##############################################################################################
def add_mail_label(thread_id="",add="READ",user_id=""):
    if(remove!='UNREAD' ):
        if(remove!='READ'):
            return
    creds = gmail_api_interfacing.authorize()
    service = build('gmail', 'v1', credentials=creds)
    service.users().messages().modify(userId=user_id, id=thread_id, body={'removeLabelIds': [str(add)]}).execute()
    ############ add_mail_label ends ##############################################################################################
