import smtplib

gmail_user = 'gpt2.testingai@gmail.com'
gmail_password = 'fraudbait'


server = smtplib.SMTP('gmail.com:587')
server.ehlo()
server.login(gmail_user, gmail_password)
print('Something went wrong...')