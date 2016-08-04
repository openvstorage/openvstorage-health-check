# Health check for Open vStorage, Alba & Arakoon

## 1. Description

The health check is classified as a monitoring, detection and healing tool for Open vStorage for `Fargo`.

**Note:** You will have to deploy this on every Open vStorage node.

## 2. Adding the package server
### 2.1 Stable
```
echo "deb http://apt.openvstorage.org fargo main" > /etc/apt/sources.list.d/ovsaptrepo.list
apt-get update
```

### 2.2 Unstable
```
echo "deb http://apt.openvstorage.org unstable main" > /etc/apt/sources.list.d/ovsaptrepo.list
apt-get update
```

## 3. Installation
```
apt-get install openvstorage-health-check
```
 
## 7. Implementing the healthcheck in your system. 

### RUN in silent or unattended mode

Although this is available, we only use this in code 
```
ovs healthcheck silent
```

or 

```
ovs healthcheck unattended
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

