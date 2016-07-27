#!/usr/bin/env bash

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
# but WITHOUT ANY WARRANTY of any kind.

cp ../* /opt/OpenvStorage -R
cp ../scripts/system/ovs /usr/bin/ovs
chmod 755 /usr/bin/ovs
wget https://bootstrap.pypa.io/get-pip.py; python get-pip.py
#pip install flower
pip install psutil
pip install xmltodict
pip install timeout-decorator