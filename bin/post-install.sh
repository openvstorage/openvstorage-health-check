#!/usr/bin/env bash

cp ../* /opt/OpenvStorage -R
cp ../scripts/system/ovs /usr/bin/ovs
chmod 755 /usr/bin/ovs
wget https://bootstrap.pypa.io/get-pip.py; python get-pip.py
pip install flower
pip install psutil
pip install xmltodict