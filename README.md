# Health check for Open vStorage, Alba & Arakoon

## 1. Description

The health check is classified as a monitoring, detection and healing tool for Open vStorage.

## 2. Pulling this repository
```
sudo apt-get install -y git
git clone -b ovs-impl https://github.com/openvstorage/openvstorage-health-check.git
```

## 3. Installation (BY POST-INSTALL SCRIPT)
```
cd openvstorage-health-check/; bash /bin/post-install.sh
```

## 4. Installation (MANUAL)

### Required packages for Health Check
```
wget https://bootstrap.pypa.io/get-pip.py; python get-pip.py
pip install flower
pip install psutil
pip install xmltodict
```

### Add following code to Health Check Open vStorage commands

```
vim /usr/bin/ovs
```

```
elif [ "$1" = "healthcheck" ] ; then
    cd /opt/OpenvStorage/ovs/lib
    if [ "$2" = "unattended" ] ; then
        # launch unattended healthcheck
        python -c "from healthcheck import HealthCheckController; HealthCheckController().check_unattended()"
    elif [ "$2" = "silent" ] ; then
	    # launch silent healthcheck
	    python -c "from healthcheck import HealthCheckController; HealthCheckController().check_silent()"
    else
        # launch healthcheck
        python -c "from healthcheck import HealthCheckController; HealthCheckController().check_attended()"
    fi
```

## 5. Execution by hand in ATTENDED MODUS

```
ovs healthcheck
```

## 6. Monitoring with CheckMK or other server-deamon monitoring systems

**Recommended:** Run on 30 min. - hourly base (on every node), to check the health of your Open vStorage.

### RUN for CheckMK or other monitoring systems

```
ovs healthcheck unattended
```

### Execute by CRON.hourly *(will only generate logs)*

```
* *   * * *  root  /usr/bin/ovs healthcheck unattended
```
 
## 7. Implementing the healthcheck in your system. 

### RUN in silent mode

Although this is available, we only use this in code 
```
ovs healthcheck silent
```

### In-code usage

```
In [1]: from ovs.lib.healthcheck import HealthCheckController

In [2]: HealthCheckController.check_silent()
Out[2]: 
{'recap': {'EXCEPTION': 0,
  'FAILED': 2,
  'SKIPPED': 2,
  'SUCCESSFULL': 114,
  'WARNING': 1},
 'result': {'alba_backend_be-backend': 'SUCCESS',
  'alba_backends_found': 'SUCCESS',
  'alba_proxy': 'SUCCESS',
  'albaproxy_bepool_preset_bepreset_create_namespace': 'SUCCESS',
  'albaproxy_bepool_preset_bepreset_create_object': 'SUCCESS',
  'albaproxy_bepool_preset_default_create_namespace': 'SUCCESS',
  'albaproxy_bepool_preset_default_create_object': 'SUCCESS',
  'arakoon_integrity': 'SUCCESS',

  ...
```
 
## 8. Important to know!
* No files in the vPools may be named after: `ovs-healthcheck-test-{storagerouter_id}.xml`
* No volumes in the vPools may be named after: `ovs-healthcheck-test-{storagerouter_id}.raw`

## 9. Branch Info or contributions
* The 'master' branch is marked as the main but unstable branch
* The 'release' branches are the official releases of the HEALTH CHECK Project
* We'd love to have your contributions, read [Community Information](CONTRIBUTION.md) and [Rules of conduct](RULES.md) for notes on how to get started.

## 10. File a bug
Open vStorage and it's automation is quality checked to the highest level.
Unfortunately we might have overlooked some tiny topics here or there.
The Open vStorage HEALTH CHECK Project maintains a [public issue tracker](https://github.com/openvstorage/openvstorage-health-check/issues)
where you can report bugs and request features.
This issue tracker is not a customer support forum but an error, flaw, failure, or fault in the Open vStorage software.

If you want to submit a bug, please read the [Community Information](CONTRIBUTION.md) for notes on how to get started.

# 11. License
The Open vStorage HealthCheck is licensed under the [GNU AFFERO GENERAL PUBLIC LICENSE Version 3](https://www.gnu.org/licenses/agpl.html).

