# This directory contains the health checks for OVS, Alba & Arakoon

See `http://jira.cloudfounders.com/browse/OPS-5` for progress

# Required packages for Health Check
```
wget https://bootstrap.pypa.io/get-pip.py; python get-pip.py
pip install psutil
pip install xmltodict
```

# Important to know!
* No files in the vPools may be named after: `ovs-healthcheck-test.xml`
* No volumes in the vPools may be named after: `ovs-healthcheck-test.raw`


