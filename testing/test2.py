import threading
import time

def thread(args1, name):
    print "starting thread"
    time.sleep(10)

try:
    t = threading.Thread(target=thread, args=(1, 'deamon'))
    t.daemon = True
    t.start()

    time.sleep(5)
    if not t.isAlive():
        print "OK"
    else:
        print "NOK"

except Exception as e:
    print "action took to long, bye!"

