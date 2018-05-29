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

If you wish to avoid manually passing the results instance, you could opt for the HealthCheckCLIRunner:
```
from ovs.extensions.healthcheck.expose_to_cli import HealthCheckCLIRunner
output = HealthCheckCLIRunner.run_method()  # Same as calling ovs healthcheck
output = HealthCheckCLIRunner.run_method('ovs')  # Same as calling ovs healthcheck ovs
output = HealthCheckCLIRunner.run_method('ovs', 'nginx-ports'test')  # Same as calling ovs healthcheck nginx-ports-test

# Output format:
{'recap': {'EXCEPTION': 0,
  'FAILED': 0,
  'SKIPPED': 11,
  'SUCCESS': 182,
  'WARNING': 0},
 'result': {'alba-backend-test': {'messages': OrderedDict([('error', []), ('exception', []), ('skip', []), ('success', [{'message': 'We found 3 backend(s)!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID t5X9va8aO6bnxifPlRjk7FxIeMFeeUEi succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID ZnIec3oF1c9zaWcmA8X9N4BN1PMZLtEq succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID kxvqKj3DH69tAmVPWwtpBwlgwGTOCYsE succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID R5P6oRaRZrVlnT6bHvW6Jr60PTNqMgBY succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID oqBbYRDrDZUr941YcjBeuDNgwa54x5B8 succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID t15miMiMTXtPAlvBOUIVUXReVKwEcGEK succeeded!', 'code': 'HC000'}, {'message': 'Alba backend mybackend02 should be available for VPool use. All asds are working fine!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID F8q0gti78jBiBtIZMOWubYgXyo5MFhJJ succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID uMeRaJSV4YFzX2KmGGRZL0lInTBvtyAS succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID iNnUDyOb4v1aIDc5kzsf6u7uV6uv50ax succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID YrgPKQlFHvEv3HKikLZ85N0lfLzZbiY2 succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID ixbskq2MUnWpioEHAkkyrLAqOxQuNx30 succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID lg0gR9pGJKY8SZauTU3QjtfhlI6g1ST6 succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID ErDkFxfe28JUMzlHQjZUmVfDO6vhtBlU succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID 70R56wudQYpJixzeQ0vj4pSS0a1KgCDJ succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID RQJkYgrICOflecO5QrD8llYEaZt2CoAT succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID oHaT2TpprxJr7WHfyXSfEAkfbaTjFVfZ succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID 80YRsH75fS9mN8S6t6A3QZ7HqEaDYeKF succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID q8iEivSKPwOfA1rJJL7ShOSkAMiO4uNS succeeded!', 'code': 'HC000'}, {'message': 'Alba backend mybackend should be available for VPool use. All asds are working fine!', 'code': 'HC000'}]), ('warning', [])]),
   'state': 'SUCCESS'},
  'alba-disk-safety-test': {'messages': OrderedDict([('error', []), ('exception', []), ('skip', []), ('success', [{'message': 'All data is safe on backend mybackend02 with 1 namespace(s)', 'code': 'HC000'}, {'message': 'All data is safe on backend mybackend with 1 namespace(s)', 'code': 'HC000'}]), ('warning', [])]),
   'state': 'SUCCESS'},
  ....
```

## 4. Configuration
Certain checks accept arguments to allow tweaking. Checking which tests accept which options can be found using --help option
```
ovs healthcheck alba disk-safety-test --help
Usage: alba alba disk-safety-test [OPTIONS]

  Verifies that namespaces have enough safety

Options:
  -b, --backend TEXT             Backend(s) to check for. Can be provided
                                 multiple times. Ignored if --skip-backend
                                 option is given
  -s, --skip-backend TEXT        Backend(s) to skip checking for. Can be
                                 provided multiple times
  -i, --include-errored-as-dead  OSDs with errors as treated as dead ones
                                 during the calculation
  --help    
```
These options can then be given through the CLI: `ovs healthcheck alba disk-safety-test -s mybackend -s mybackend-global`

## 4.1 Overriding defaults
The Healthcheck works with a number of default arguments for certain tests (in the example above: no backend is skipped by default)
These defaults can be fine tuned for all Healthcheck across the cluster by creating a default-map within Configuration

The key to provide the defaults under: /ovs/healthcheck/default_arguments
Configs are to be set under MODULE : TEST: PARAM NAME PYTHONIFIED
An example:
```
{
    "alba": {
        "disk-safety-test": {
            "include_errored_as_dead": false, 
            "skip_backend": [], 
            "backend": []
        }
}
```
The possible value is dependent on the type of argument to be set. When an option can be specified multiple times: the argument has to be a list. Types like text require a string, float/integer the numeric values, ...

A complete dict of all possible options and their current value can be generated:
```
from ovs.extensions.healthcheck.expose_to_cli import HealthCheckCLIRunner
HealthCheckCLIRunner.generate_configuration_options?
Type:        instancemethod
String form: <bound method type.generate_configuration_options of <class 'ovs.extensions.healthcheck.expose_to_cli.HealthCheckCLIRunner'>>
File:        /opt/OpenvStorage/ovs/extensions/healthcheck/expose_to_cli.py
Definition:  HealthCheckCLIRunner.generate_configuration_options(cls, re_use_current_settings=False)
Docstring:
Generate a complete structure indicating where tweaking is possible together with the default values
:param re_use_current_settings: Re-use the settings currently set. Defaults to False
It will regenerate a complete structure and apply the already set values if set to True
:return: All options available to the healthcheck
:rtype: dict
```

Setting all current possible options before tweaking them:
```
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.healthcheck.expose_to_cli import HealthCheckShared, HealthCheckCLIRunner
Configuration.set(HealthCheckShared.CONTEXT_SETTINGS_KEY, HealthCheckCLIRunner.generate_configuration_options())
```

When new arguments are added: the generation can take your old settings into account by providing `False'

```
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.healthcheck.expose_to_cli import HealthCheckShared, HealthCheckCLIRunner
Configuration.set(HealthCheckShared.CONTEXT_SETTINGS_KEY, HealthCheckCLIRunner.generate_configuration_options(False))
```

## 5. Important to know!
* No files in the vPools may be named after: `ovs-healthcheck-test-{storagerouter_id}.xml`
* No volumes in the vPools may be named after: `ovs-healthcheck-test-{storagerouter_id}.raw`

## 6. Branch Info or contributions
* The 'master' branch is marked as the main but unstable branch
* The 'release' branches are the official releases of the HEALTH CHECK Project
* We'd love to have your contributions, read [Community Information](CONTRIBUTION.md) and [Rules of conduct](RULES.md) for notes on how to get started.

## 7. File a bug
Open vStorage and it's automation is quality checked to the highest level.
Unfortunately we might have overlooked some tiny topics here or there.
The Open vStorage HEALTH CHECK Project maintains a [public issue tracker](https://github.com/openvstorage/openvstorage-health-check/issues)
where you can report bugs and request features.
This issue tracker is not a customer support forum but an error, flaw, failure, or fault in the Open vStorage software.

If you want to submit a bug, please read the [Community Information](CONTRIBUTION.md) for notes on how to get started.

# 8. License
The Open vStorage HealthCheck is licensed under the [GNU AFFERO GENERAL PUBLIC LICENSE Version 3](https://www.gnu.org/licenses/agpl.html).

