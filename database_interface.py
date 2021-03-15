import MySQLdb
from custom_exceptions import *
def create_cursor():
    db = MySQLdb.connect(host="localhost",
                        user="baiter",    
                        passwd="baiter_pass",
                        db="production")     

    cur = db.cursor()
    return cur,db
def insert_row_in_emails_adressbook(email):
    cursor,database = create_cursor()
    number_of_dupe_rows = cursor.execute("SELECT * FROM emails_adressbook WHERE email = '"+email+"';")
    if(number_of_dupe_rows==0):
        cursor.execute("INSERT INTO emails_adressbook (email) VALUES ('"+email+"');")
        database.commit()
        cursor.close()
        database.close()
##
def insert_row_in_scammer_adressbook(email):
    cursor,database = create_cursor()
    number_of_dupe_rows = cursor.execute("SELECT * FROM scammers_adressbook WHERE scammer_email = '"+email+"';")
    if(number_of_dupe_rows==0):
        cursor.execute("INSERT INTO scammers_adressbook (scammer_email) VALUES ('"+email+"');")
        database.commit()
        cursor.close()
        database.close()
        
##
def insert_row_in_threads(thread_id,scammer_email,email):
    cursor,database = create_cursor()
    ###################################Check scammer adressbook#########################################
    scammer_email_count = cursor.execute("SELECT id FROM scammers_adressbook WHERE scammer_email = '"+scammer_email+"';")
    if(scammer_email_count == 0):
        insert_row_in_scammer_adressbook(scammer_email)
        cursor.close()
        database.close()
        cursor,database = create_cursor()
        scammer_email_count = cursor.execute("SELECT id FROM scammers_adressbook WHERE scammer_email = '"+scammer_email+"';")
    if(scammer_email_count != 1):
        raise Exception
    all_rows = cursor.fetchall()
    id_scammer_email = all_rows[0][0]
    email_count = cursor.execute("SELECT id FROM emails_adressbook WHERE email = '"+email+"';")

    if(email_count == 0):
        insert_row_in_emails_adressbook(email)
        cursor.close()
        database.close()
        cursor,database = create_cursor()
        email_count = cursor.execute("SELECT id FROM emails_adressbook WHERE email = '"+email+"';")
    if(email_count != 1):
        raise Exception
    all_rows = cursor.fetchall()
    id_email = all_rows[0][0]
    row_exists = cursor.execute("SELECT * FROM threads WHERE thread_id = '"+thread_id+"';")
    if(row_exists>0):
        raise DuplicateRows
    cursor.execute("INSERT INTO threads(scammer_mail,thread_id,email) VALUES ("+str(id_scammer_email)+",'"+thread_id+"',"+str(id_email)+");")
    database.commit()
    cursor.close()
    database.close()

def insert_row_in_message_table(thread_id,message):
    cursor,database = create_cursor()
    ###################################Check scammer adressbook#########################################
    threads_id_count = cursor.execute("SELECT id FROM threads WHERE thread_id = '"+thread_id+"';")
    if(threads_id_count != 1):
        raise DuplicateRows
    all_rows = cursor.fetchall()
    id_thread = all_rows[0][0]
    row_exists = cursor.execute("SELECT * FROM message WHERE message= '"+message+"' AND thread_id="+str(id_thread)+";")
    if(row_exists>0):
        raise DuplicateRows
    cursor.execute("INSERT INTO message(thread_id,message) VALUES ("+str(id_thread)+",'"+message+"');")
    database.commit()
    cursor.close()
    database.close()

###

#####IDENTITY TO DO
def insert_row_in_identity_table(name,phone_number,email,age,country,username,adress,birth,gender,company,card_num,card_date,thread_id):
    cursor,database = create_cursor()
    email_count = cursor.execute("SELECT id FROM emails_adressbook WHERE email = '"+email+"';")
    ##############################Check emails adressbook#################################################
    if(email_count == 0):
        insert_row_in_emails_adressbook(email)
        cursor.close()
        database.close()
        cursor,database = create_cursor()
        email_count = cursor.execute("SELECT id FROM emails_adressbook WHERE email = '"+email+"';")
    if(email_count != 1):
        raise Exception
    all_rows = cursor.fetchall()
    id_email = all_rows[0][0]
    ###################################Check check threads#########################################
    threads_id_count = cursor.execute("SELECT id FROM threads WHERE thread_id = '"+thread_id+"';")
    if(threads_id_count != 1):
        raise DuplicateRows
    all_rows = cursor.fetchall()
    id_thread = all_rows[0][0]
    row_exists = cursor.execute("SELECT * FROM message WHERE message= '"+message+"';")
    if(row_exists>0):
        raise DuplicateRows
    cursor.execute("INSERT INTO message(name,phone_number,email,age,country,username,adress,birth,gender,company,card_num,card_date) VALUES ("+str(name)+","+str(phone_number)+","+str(id_thread)+","+str(age)+",'"+country+"','"+username+"','"+adress+"','"+birth+"','"+gender+"','"+company+"','"+card_num+"','"+card_date+"',"+str(id_thread)+");")
    database.commit()
    cursor.close()
    database.close()
