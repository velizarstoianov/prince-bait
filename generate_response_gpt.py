import gpt_2_simple as gpt2
import tensorflow as tf
import os
import requests
import random

def generate_response(in_text,model_size="1558M"):
    if(in_text ==  None):
        return ""
    if(len(in_text) < 1 ):
        return ""
    len_of_sample = random.randint(1999,2000)
    model_name = model_size
    config = tf.compat.v1.ConfigProto(device_count={"GPU": 0})
    session = tf.compat.v1.Session(config=config)
    session.run(tf.compat.v1.global_variables_initializer())
    gpt2.load_gpt2(session)
#    generated_response = gpt2.generate(session,model_name=model_name,model_dir="/home/velizar/Project/gpt-2/models",prefix=in_text,length=len_of_sample,nsamples=1,truncate="<|endoftext|>",top_k=40,return_as_list=True)
    generated_response = gpt2.generate(session,model_name=model_name,model_dir="/home/velizar/Project/gpt-2/models",prefix=in_text,nsamples=1,truncate="<|endoftext|>",top_k=40,return_as_list=True) 
    print(generated_response[0])
    return generated_response[0].replace(in_text,"")
    session.reset()
############ Generate to file#####################
def generate_response_file(in_text,out_filename,model_size="1558M"):
    if(in_text ==  None):
        return ""
    if(len(in_text) < 1 ):
        return ""
    if(out_filename == None):
        return
    if(len(out_filename) < 1):
        return
    model_name = model_size
    len_of_sample = random.randint(900,1000)
    config = tf.compat.v1.ConfigProto(device_count={"GPU": 0})
    session = tf.compat.v1.Session(config=config)
    session.run(tf.compat.v1.global_variables_initializer())
    gpt2.load_gpt2(session)
    gpt2.generate_to_file(session,model_name=model_name,model_dir="/home/velizar/Project/gpt-2/models",prefix=read_mail,length=len_of_sample,destination_path=out_filename,truncate="<|endoftext|>")
    session.reset()
############### Generate partial reply #########################
def generate_response_partial(in_text,model_size="1558M",sentence_count=1):
    if(in_text ==  None):
        return ""
    if(len(in_text) < 1 ):
        return ""
    len_of_sample = 400
    model_name = model_size
    config = tf.compat.v1.ConfigProto(device_count={"GPU": 0})
    session = tf.compat.v1.Session(config=config)
    session.run(tf.compat.v1.global_variables_initializer())
    gpt2.load_gpt2(session)
    generated_response = gpt2.generate(session,model_name=model_name,model_dir="/home/velizar/Project/gpt-2/models",prefix=in_text,length=500)
    split_response = str(generate_response).split(".")
    i=0
    response_to_return = ""
    for sentence in split_response:
        if(i>sentence_count):
            break
        response_to_return += sentence
    session.reset()
    return response_to_return

        
