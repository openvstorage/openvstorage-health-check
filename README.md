# Health check for Open vStorage, Alba & Arakoon

## 1. Description

The health check is classified as a monitoring, detection tool for Open vStorage.

**Note:** You will have to deploy this on every Open vStorage node.

**Note:** Install the health check after the setup of Open vStorage.

## 2. Installation
```
apt-get install openvstorage-health-check
```
 
## 3. Implementing the healthcheck in your system. 

### 3.1. RUN in to-json or unattended mode

```
ovs healthcheck --to-json
```
will display a json structure containing all tests, their status and any messages that were logged during the test.
or 

```
ovs healthcheck --unattended
```
will display all tests and their states
### 3.2. Run specific tests
```
ovs healthcheck --help
```
Will provide a list of all possible options you have. The --to-json and --unattended are also optional arguments you can supply to each individual test

```
ovs healthcheck MODULE
```
Will run all methods for the specified

```
ovs healthcheck MODULE METHOD
```
Will run the method for the specified module
### 3.3. In-code usage

Running Healthcheck tests throughout a Python interface is a little tougher as it is written to be used through the CLI interface
However if you do wish to use the Python interface:
- All tests require a HCResults instance to be passed
```
from ovs.extensions.healthcheck.result import HCResults
from ovs.extensions.healthcheck.suites.arakoon_hc import ArakoonHealthCheck
result = HCResults()
ArakoonHealthCheck.check_collapse(result)
```
If you wish to capture output: a named HCResults must be passed. This way a single result instance can capture all test outputs
```
from ovs.extensions.healthcheck.result import HCResults
from ovs.extensions.healthcheck.suites.arakoon_hc import ArakoonHealthCheck
result = HCResults()
ArakoonHealthCheck.check_collapse(result.HCResultCollector(result=result, test_name='collapse-test'))
# Output
print result.counter
print result.result_dict
```

## 4. Important to know!
* No files in the vPools may be named after: `ovs-healthcheck-test-{storagerouter_id}.xml`
* No volumes in the vPools may be named after: `ovs-healthcheck-test-{storagerouter_id}.raw`

## 5. Branch Info or contributions
* The 'master' branch is marked as the main but unstable branch
* The 'release' branches are the official releases of the HEALTH CHECK Project
* We'd love to have your contributions, read [Community Information](CONTRIBUTION.md) and [Rules of conduct](RULES.md) for notes on how to get started.

## 6. File a bug
Open vStorage and it's automation is quality checked to the highest level.
Unfortunately we might have overlooked some tiny topics here or there.
The Open vStorage HEALTH CHECK Project maintains a [public issue tracker](https://github.com/openvstorage/openvstorage-health-check/issues)
where you can report bugs and request features.
This issue tracker is not a customer support forum but an error, flaw, failure, or fault in the Open vStorage software.

If you want to submit a bug, please read the [Community Information](CONTRIBUTION.md) for notes on how to get started.

# 7. License
The Open vStorage HealthCheck is licensed under the [GNU AFFERO GENERAL PUBLIC LICENSE Version 3](https://www.gnu.org/licenses/agpl.html).

