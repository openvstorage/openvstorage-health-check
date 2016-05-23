# Copyright (C) 2016 iNuron NV
#
# This file is part of Open vStorage Open Source Edition (OSE),
# as available from
#
#      http://www.openvstorage.org and
#      http://www.openvstorage.com.
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)
# as published by the Free Software Foundation, in version 3 as it comes
# in the LICENSE.txt file of the Open vStorage OSE distribution.
#
# Open vStorage is distributed in the hope that it will be useful,

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

