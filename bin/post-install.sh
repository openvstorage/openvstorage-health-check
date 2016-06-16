#!/usr/bin/env bash

wget https://bootstrap.pypa.io/get-pip.py; python get-pip.py
pip install flower
pip install psutil
pip install xmltodict

mkdir -p /opt/OpenvStorage-healthcheck;
cp -r * /opt/OpenvStorage-healthcheck

cp scripts/ovs /usr/bin/ovs
chmod 755 /usr/bin/ovs
