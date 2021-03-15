import requests
from classes import *
import json
api_endpoint = "https://api.namefake.com/"

def get_details():
    personlaity_obj = Identity()
    def exit0():
        personlaity_obj.verification_num = 0
        return personlaity_obj
    def exit1():
        personlaity_obj.verification_num = 1
        return personlaity_obj
    generated_raw_personality = requests.get(api_endpoint)
    if(generated_raw_personality.status_code != 200):
        personlaity_obj.verification_num = 0
        return personlaity_obj
    else:
        try:  
            response_dict = json.loads(generated_raw_personality.content)
        except json.JSONDecodeError:
            print("An Error Occured while decoding the following json:"+str(generated_raw_personality.content))
            response_dict = {}
            exit0()
    if(len(response_dict)<=0):
        exit0()
    else:
        if("name" in response_dict):
            personlaity_obj.name = response_dict['name']
        else:
            exit0()
        if("address" in response_dict):
            personlaity_obj.address = response_dict["address"]
        else:
            exit0()
        if("birth_data" in response_dict):
            personlaity_obj.birth = response_dict["birth_data"]
        else:
            exit0()
        if("phone_h" in response_dict):
            personlaity_obj.phone_number = response_dict["phone_h"]
        else:
            exit1()
        if("plasticcard" in  response_dict):
            personlaity_obj.card_num = response_dict["plasticcard"]
        else:
            exit0()
#        if("cardexpir" in response_dict):
#            personlaity_obj = response_dict["cardexpir"]
#        else:
#            exit0()
#        if("company" in response_dict):
#            personlaity_obj = response_dict["company"]
#        else:
#            exit0()

def get_raw_response_content():
    generated_raw_personality = requests.get(api_endpoint)
    if(generated_raw_personality.status_code != 200):
        return generated_raw_personality.content