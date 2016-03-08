# Health check for Open vStorage, Alba & Arakoon

## Description

The health check is classified as a monitoring, detection and healing tool for Open vStorage.

## Required packages for Health Check
```
wget https://bootstrap.pypa.io/get-pip.py; python get-pip.py
pip install flower
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
    cd /opt/OpenvStorage/ovs/lib
    if [ "$2" = "unattended" ] ; then
        # launch unattended healthcheck
        python -c "from healthcheck import HealthCheckController; HealthCheckController(unattended_run=True).check_all()"
    elif [ "$2" = "silent" ] ; then
	# launch silent healthcheck
	python -c "from healthcheck import HealthCheckController; HealthCheckController(silent_run=True).check_all()"
    else
        # launch healthcheck
        python healthcheck.py
    fi
```

### Execution by hand

```
# via Open vStorage commands
ovs healthcheck

# native python execution
cd /opt/OpenvStorage/ovs/lib

python healthcheck.py
```

## Monitoring with CheckMK or other server-deamon monitoring systems

### RUN for CheckMK or other monitoring systems

```
ovs healthcheck unattended
```

### Execute by CRON.hourly *(will only generate logs)*

```
* *   * * *  root  /usr/bin/ovs healthcheck unattended
```
 
## Implementing the healthcheck in your system. 

### RUN for coding purposes

```
ovs healthcheck silent
```

### In-code usage

```
from healthcheck import HealthCheckController

# running in silent mode
hc = HealthCheckController(silent_run=True)

# checking all components and getting the results
results = hc.check_all()

# checking all desired components and getting the results
hc.check_openvstorage()

hc.check_arakoon()

hc.check_alba()

results = hc.get_results()
```
 
# Important to know!
* No files in the vPools may be named after: `ovs-healthcheck-test-{storagerouter_id}.xml`
* No volumes in the vPools may be named after: `ovs-healthcheck-test-{storagerouter_id}.raw`

## Branch Info or contributions
* The 'master' branch is marked as the main but unstable branch
* The 'release' branches are the official releases of the HEALTH CHECK Project
* We'd love to have your contributions, read [Community Information](CONTRIBUTION.md) and [Rules of conduct](RULES.md) for notes on how to get started.

## File a bug
Open vStorage and it's automation is quality checked to the highest level.
Unfortunately we might have overlooked some tiny topics here or there.
The Open vStorage HEALTH CHECK Project maintains a [public issue tracker](https://github.com/openvstorage/openvstorage-health-check/issues)
where you can report bugs and request features.
This issue tracker is not a customer support forum but an error, flaw, failure, or fault in the Open vStorage software.

If you want to submit a bug, please read the [Community Information](CONTRIBUTION.md) for notes on how to get started.

# License
The Open vStorage Healthcheck is released under the [Apache 2 license](http://www.apache.org/licenses/LICENSE-2.0).
