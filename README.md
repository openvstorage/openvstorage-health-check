# Health check for Open vStorage, Alba & Arakoon

## Description

The health check is classified as a monitoring, detection and healing tool for Open vStorage.

## Required packages for Health Check
```
wget https://bootstrap.pypa.io/get-pip.py; python get-pip.py
pip install psutil
pip install xmltodict
```

## Installation

**Recommended:** Run on 30 min. - hourly base (on every node), to check the health of your Open vStorage.

### Add following code to Health Check Open vStorage commands

```
vim /usr/bin/ovs
```

```
elif [ "$1" = "healthcheck" ] ; then
    cd /opt/OpenvStorage-healthcheck
    if [ "$2" = "unattended" ] ; then
        # launch unattended install
        python -c "from ovs_health_check.main import Main; Main(True)"
    else
        # launch attended install
        python ovs_health_check/main.py
    fi
```

### Execution by hand

```
# via Open vStorage commands
ovs healthcheck

# native python execution
cd /opt/OpenvStorage-healthcheck/

python ovs_health_check/main.py
```

## Monitoring with CheckMK or other server-deamon monitoring systems

### OUTPUT for CheckMK or other monitoring systems

```
ovs healthcheck unattended
```

### Execute by CRON.hourly *(will only generate logs)*

```
* *   * * *  root  /usr/bin/ovs healthcheck unattended
```

# Important to know!
* No files in the vPools may be named after: `ovs-healthcheck-test.xml`
* No volumes in the vPools may be named after: `ovs-healthcheck-test.raw`

## Branch Info or contributions
* The 'master' branch is marked as the main but unstable branch
* The 'release' branches are the official releases of the HEALTH CHECK Project
* We'd love to have your contributions, read [Community Information](CONTRIBUTION.md) for notes on how to get started.

## File a bug
Open vStorage and it's automation is quality checked to the highest level.
Unfortunately we might have overlooked some tiny topics here or there.
The Open vStorage HEALTH CHECK Project maintains a [public issue tracker](https://github.com/openvstorage/openvstorage-health-check/issues)
where you can report bugs and request features.
This issue tracker is not a customer support forum but an error, flaw, failure, or fault in the Open vStorage software.

If you want to submit a bug, please read the [Community Information](CONTRIBUTING.md) for notes on how to get started.

# License

```
# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Modified Apache License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
```


