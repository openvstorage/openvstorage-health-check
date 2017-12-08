# Health check for Open vStorage, Alba & Arakoon

## 1. Description

The health check is classified as a monitoring, detection tool for Open vStorage.

**Note:** You will have to deploy this on every Open vStorage node.
**Note:** Install the health check after the setup of Open vStorage.

## 3. Installation
```
apt-get install openvstorage-health-check
```
 
## 4. Implementing the healthcheck in your system. 

### 4.1. RUN in to-json or unattended mode

```
ovs healthcheck --to-json
```
will display a json structure containing all tests, their status and any messages that were logged during the test.
or 

```
ovs healthcheck --unattended
```
will display all tests and their states
### 4.2. Run specific tests
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
### 4.3. In-code usage

All code is currently handled by the HealthCheckCLIRunner. This way we kept our testing flexible and expandable.
```
In [1]: from ovs.extensions.healthcheck.expose_to_cli import HealthCheckCLIRunner

In [2]: HealthCheckCLIRunner.run_method()
Out[2]: 
{'recap': {'EXCEPTION': 0,
  'FAILED': 0,
  'SKIPPED': 11,
  'SUCCESS': 182,
  'WARNING': 0},
 'result': {'alba-backend-test': {'messages': OrderedDict([('error', []), ('exception', []), ('skip', []), ('success', [{'message': 'We found 3 backend(s)!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID t5X9va8aO6bnxifPlRjk7FxIeMFeeUEi succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID ZnIec3oF1c9zaWcmA8X9N4BN1PMZLtEq succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID kxvqKj3DH69tAmVPWwtpBwlgwGTOCYsE succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID R5P6oRaRZrVlnT6bHvW6Jr60PTNqMgBY succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID oqBbYRDrDZUr941YcjBeuDNgwa54x5B8 succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID t15miMiMTXtPAlvBOUIVUXReVKwEcGEK succeeded!', 'code': 'HC000'}, {'message': 'Alba backend mybackend02 should be available for VPool use. All asds are working fine!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID F8q0gti78jBiBtIZMOWubYgXyo5MFhJJ succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID uMeRaJSV4YFzX2KmGGRZL0lInTBvtyAS succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID iNnUDyOb4v1aIDc5kzsf6u7uV6uv50ax succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID YrgPKQlFHvEv3HKikLZ85N0lfLzZbiY2 succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID ixbskq2MUnWpioEHAkkyrLAqOxQuNx30 succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID lg0gR9pGJKY8SZauTU3QjtfhlI6g1ST6 succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID ErDkFxfe28JUMzlHQjZUmVfDO6vhtBlU succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID 70R56wudQYpJixzeQ0vj4pSS0a1KgCDJ succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID RQJkYgrICOflecO5QrD8llYEaZt2CoAT succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID oHaT2TpprxJr7WHfyXSfEAkfbaTjFVfZ succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID 80YRsH75fS9mN8S6t6A3QZ7HqEaDYeKF succeeded!', 'code': 'HC000'}, {'message': 'ASD test with DISK_ID q8iEivSKPwOfA1rJJL7ShOSkAMiO4uNS succeeded!', 'code': 'HC000'}, {'message': 'Alba backend mybackend should be available for VPool use. All asds are working fine!', 'code': 'HC000'}]), ('warning', [])]),
   'state': 'SUCCESS'},
  'alba-disk-safety-test': {'messages': OrderedDict([('error', []), ('exception', []), ('skip', []), ('success', [{'message': 'All data is safe on backend mybackend02 with 1 namespace(s)', 'code': 'HC000'}, {'message': 'All data is safe on backend mybackend with 1 namespace(s)', 'code': 'HC000'}]), ('warning', [])]),
   'state': 'SUCCESS'},


  ...
```
All the checks will still log by printing but the return value can be captured in a value.

## 5. Important to know!
* No files in the vPools may be named after: `ovs-healthcheck-test-{storagerouter_id}.xml`
* No volumes in the vPools may be named after: `ovs-healthcheck-test-{storagerouter_id}.raw`

## 6. Branch Info or contributions
* The 'master' branch is marked as the main but unstable branch
* The 'release' branches are the official releases of the HEALTH CHECK Project
* We'd love to have your contributions, read [Community Information](CONTRIBUTION.md) and [Rules of conduct](RULES.md) for notes on how to get started.

## 7. File a bug
Open vStorage and its automation is quality checked to the highest level.
Unfortunately we might have overlooked some tiny topics here or there.
The Open vStorage HEALTH CHECK Project maintains a [public issue tracker](https://github.com/openvstorage/openvstorage-health-check/issues)
where you can report bugs and request features.
This issue tracker is not a customer support forum but an error, flaw, failure, or fault in the Open vStorage software.

If you want to submit a bug, please read the [Community Information](CONTRIBUTION.md) for notes on how to get started.

# 8. License
The Open vStorage HealthCheck is licensed under the [GNU AFFERO GENERAL PUBLIC LICENSE Version 3](https://www.gnu.org/licenses/agpl.html).

