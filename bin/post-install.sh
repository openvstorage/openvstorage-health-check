#!/usr/bin/env bash

cp ../* /opt/OpenvStorage -R
cp ../scripts/system/ovs /usr/bin/ovs
chmod 755 /usr/bin/ovs
wget https://bootstrap.pypa.io/get-pip.py; python get-pip.py
pip install flower
pip install psutil
pip install xmltodict

chown root:shadow /etc/shadow
chown root:shadow /etc/gshadow
useradd -g man man
chown man:root /var/cache/man
