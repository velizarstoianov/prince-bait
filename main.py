from fake_personality import *
from random import *
import generate_response_gpt
import gmail_api_interfacing
from database_interface import *  
from custom_exceptions import *
from gensim.models import Word2Vec
from gensim.models import KeyedVectors
from json import *
import requests

url = "https://api.meaningcloud.com/topics-2.0"
list_of_intent = ["bank", "acccount", "details", "banking","iban","number", "social", "security"]
model = KeyedVectors.load_word2vec_format(fname="/home/velizar/Project/PythonPlayground/GoogleNews-vectors-negative300.bin", binary=True)


cur,database = create_cursor()
emails = gmail_api_interfacing.get_last_mails_unread()
for email in emails:
    text_overhead = "From: "+email.to_address+"\r\n To: "+email.from_address+"\r\n Subject: "+email.subject+"\r\n"
    thread_exists = cur.execute("SELECT * FROM threads WHERE thread_id = '"+email.thread_id.strip()+"';")
    if (thread_exists<=0):
        insert_row_in_threads(email.thread_id,email.from_address,email.to_address)
    insert_row_in_message_table(email.thread_id,email.mail_body)
    text_in_response = generate_response_gpt.generate_response(text_overhead+email.mail_body)
    payload={
    'key': 'cbe6f02b4ccbe8a35c3dc76bacaf91b3',
    'txt': email.mail_body,
    'lang': 'en',  
    'tt': 'a'                      
    }
    similarity_index = 0
    response = requests.post(url, data=payload)
    resp_des = loads(response.content.decode("utf-8"))
    for concept in resp_des["concept_list"]:
        for item in list_of_intent:
            if(" " in str(concept['form']).strip()):
                continue
            try:
                similarity = model.similarity(concept["form"],item)
            except Exception:
                continue
            similarity_index += float(similarity)
    if(similarity_index>2):
        header_sentence_count = randint(2,5)
        trail_sentence_count = randint(0,2)
        personality = get_details()
        text_in_response = generate_response_gpt.generate_response_partial(text_overhead+email.mail_body,sentence_count=header_sentence_count)
        text_in_response += "this is my iban:"+ personality.card_num
        text_in_response += generate_response_gpt.generate_response_partial(text_overhead+email.mail_body,sentence_count=trail_sentence_count)
    gmail_api_interfacing.reply_to_mail(str(text_in_response),email)
    gmail_api_interfacing.add_mail_label(email.thread_id,user_id="me")
    try:
        insert_row_in_message_table(email.thread_id,"")
    except DuplicateRows:
        print("Warning: Duplicate rows in messages with thread id:"+email.thread_id)
    except Exception:
        print("Error: An exception was thrown:")
