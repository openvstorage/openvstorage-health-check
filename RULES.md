# Rules of conduct

## Description
These set of rules present a guide how to contribute your own code to this repo.

## Rules

* Follow the standard python rules, you can find them [here](https://www.python.org/dev/peps/pep-0008/)

* Modules are defined by the product (e.g. arakoon, openvstorage, swift, ceph, docker, ...)

* Write your code as dynamicly, modular, easy & lightweight as possible, this means:
  * List of items and/or settings are initialized in the constructor (with short explanation)
  * Do not use print statements in the modules (except for the Main) use the the `Utils().logger(..)` instead.
  * Module unrelated stuff is added to the `utils/extension.py` (e.g. logger, system service detector, ...)
  * No unnecessary objects need to be created. If you use it alot, declare it in the initializor / constructor.
  * Testing scripts (in `testing/`) are used as pure educational / testing purpose
  * The directory `conf/` contains all settings and information of the open vstorage health check (in JSON)
  * For monitoring AKA unattended run, don't use spaces between methods in `Main`:
```
if not self.unattended: print ""
```

⋅⋅* Try to use 1 method for every module, except if there are several critical components in a module. (e.g.)
**One critical component:**
```
# Checking Alba
self.utility.logger("Starting Alba Health Check!", self.module, 3, 'starting_alba_hc', False)
self.utility.logger("===========================\n", self.module, 3, 'starting_alba_hc_ul', False)

self.alba.checkAlba()
if not self.unattended: print ""
```

**Multiple critical components:**
```
# Checking Open vStorage
self.utility.logger("Starting Open vStorage Health Check!",self.module, 3, 'starting_ovs_hc', False)
self.utility.logger("====================================\n",self.module, 3, 'starting_ovs_hc_ul', False)

self.ovs.checkOvsProcesses()
if not self.unattended: print ""
self.ovs.checkOvsWorkers()
if not self.unattended: print ""
self.ovs.checkOvsPackages()
if not self.unattended: print ""
```

⋅⋅* Import default and custom packages under:
```
"""
Section: Import package(s)
"""
```

⋅⋅* Write, define or declare classes under:
```
"""
Section: Classes
"""
```

⋅⋅* Define main methods under: (For modules: Only for testing; for Main: Execution of HEALTH CHECK through `python ..`)
```
"""
Section: Main
"""
```

  * Do not redeclare the Utility Class in a module, obtain it through Class creation initializor / constructor: (e.g.)
**Health Check Main Class**
```
class Main:
    def __init__(self, unattended=False):

        self.module = "healthcheck"
        self.unattended = unattended
        self.utility = Utils(self.unattended)
        self.alba = AlbaHealthCheck(self.utility)
```

**Open vStorage Health Check Class**
```
class OpenvStorageHealthCheck:
    def __init__(self, utility=Utils(False)):
        self.module = 'openvstorage'
        self.utility = utility
```

⋅⋅* How to use the Utility Class `logger` function:
**Logger SEVERITY_LEVELS:**
```
failure = 0
success = 1
warning = 2
info = 3
exception = 4
skip = 5
debug = 6
```

**Giving output information to the customer (PATTERN):**
```
Utils().logger(MESSAGE, MODULE_NAME, SEVERITY_LEVEL, MONITORING_NAME, DISPLAY_IN_MONITORING)
```

**Giving output information to the customer (EXAMPLE 1: FAILED):**
```
# Best practice for SEVERITY_LEVEL = FAILED; DISPLAY_IN_MONITORING = TRUE; MONITORING_NAME = NEUTRAL NAME (e.g. IS_AVAILABLE OR IS_OK)

Utils().logger("STATUS of port {0} of service {1} ...".format(port, process_name), self.module, 0, 'port_open_{0}'.format(process_name))
```

**Giving output information to the customer (EXAMPLE 2: SUCCESS):**
```
# Best practice for SEVERITY_LEVEL = SUCCESS; DISPLAY_IN_MONITORING = TRUE; MONITORING_NAME = NEUTRAL NAME (e.g. IS_AVAILABLE OR IS_OK)

Utils().logger("STATUS of port {0} of service {1} ...".format(port, process_name), self.module, 1, 'port_open_{0}'.format(process_name))
```

**Giving output information to the customer (EXAMPLE 3: INFO):**
```
# Best practice for SEVERITY_LEVEL = INFO; DISPLAY_IN_MONITORING = FALSE; MONITORING_NAME = DOESN'T MATTER

Utils().logger("STATUS of port {0} of service {1} ...".format(port, process_name), self.module, 1, 'port_open_{0}'.format(), False)
```

