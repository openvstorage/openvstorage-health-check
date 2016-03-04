#!/usr/bin/python

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

"""
Module for HealthCheckController
"""

# general packages
import sys
import os

# import health check utilities
from openvstorage.openvstoragecluster_health_check import OpenvStorageHealthCheck
from arakoon.arakooncluster_health_check import ArakoonHealthCheck
from alba.alba_health_check import AlbaHealthCheck
from utils.extension import Utils


class Main:

    def __init__(self, unattended_run=False, silent_run=False):

        self.module = "healthcheck"

        self.unattended = unattended_run
        self.silent_mode = silent_run
        self.utility = Utils(self.unattended, self.silent_mode)
        self.alba = AlbaHealthCheck(self.utility)
        self.arakoon = ArakoonHealthCheck(self.utility)
        self.ovs = OpenvStorageHealthCheck(self.utility)

    def check_openvstorage(self):
        """
        Checks all critical components of Open vStorage
        """

        self.utility.logger("Starting Open vStorage Health Check!", self.module, 3, 'starting_ovs_hc', False)
        self.utility.logger("====================================\n", self.module, 3, 'starting_ovs_hc_ul', False)

        self.ovs.getLocalSettings()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.checkOvsProcesses()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.checkOvsWorkers()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.checkOvsPackages()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.checkRequiredPorts()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.findZombieAndDeadProcesses()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.checkRequiredDirs()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.checkHypervisorManagementInformation()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.checkSizeOfLogFiles()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.checkIfDNSResolves()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.checkModelConsistency()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.checkForHaltedVolumes()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.checkFileDriver()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.checkVolumeDriver()
        if not self.unattended and not self.silent_mode:
            print ""

    def check_arakoon(self):
        """
        Checks all critical components of Arakoon
        """

        self.utility.logger("Starting Arakoon Health Check!", self.module, 3, 'starting_arakoon_hc', False)
        self.utility.logger("==============================\n", self.module, 3, 'starting_arakoon_hc_ul', False)

        self.arakoon.checkArakoons()
        if not self.unattended and not self.silent_mode:
            print ""

    def check_alba(self):
        """
        Checks all critical components of Alba
        """

        self.utility.logger("Starting Alba Health Check!", self.module, 3, 'starting_alba_hc', False)
        self.utility.logger("===========================\n", self.module, 3, 'starting_alba_hc_ul', False)

        self.alba.checkAlba()
        if not self.unattended and not self.silent_mode:
            print ""

    def get_results(self):
        """
        Gets the result of the healthcheck
        """

        self.utility.logger("Recap of Health Check!", self.module, 3, 'starting_recap_hc', False)
        self.utility.logger("======================\n", self.module, 3, 'starting_recap_hc_ul', False)

        self.utility.logger("SUCCESSFULL={0} FAILED={1} SKIPPED={2} WARNING={3} EXCEPTION={4}"
                            .format(self.utility.success, self.utility.failure, self.utility.skip, self.utility.warning,
                                    self.utility.exception), self.module, 1, 'exception_occured')

        if self.silent_mode or self.unattended:
            # returns dict with minimal and detailed information
            return {'result': self.utility.healthcheck_dict, 'recap': {'SUCCESSFULL': self.utility.success,
                                                                       'FAILED': self.utility.failure,
                                                                       'SKIPPED': self.utility.skip,
                                                                       'WARNING': self.utility.warning,
                                                                       'EXCEPTION': self.utility.exception}
                    }
        else:
            return None

if __name__ == '__main__':

    unattended = False
    silent_mode = False
    module = "healthcheck"

    try:
        main = Main(unattended, silent_mode)
        main.check_openvstorage()
        main.check_arakoon()
        main.check_alba()
        main.get_results()

    except KeyboardInterrupt as e:
        utility = Utils(unattended)

        print ""
        utility.logger("Recap of Health Check!", module, 3, 'starting_recap_hc', False)
        utility.logger("======================\n", module, 3, 'starting_recap_hc_ul', False)
        Utils(unattended).logger("Open vStorage Health Check - Ended by USER through Keyboard", module,
                                 4, 'exception_occured')

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        utility = Utils(unattended)

        print ""
        utility.logger("Recap of Health Check!", module, 3, 'starting_recap_hc', False)
        utility.logger("======================\n", module, 3, 'starting_recap_hc_ul', False)
        Utils(unattended).logger("Open vStorage Health Check - EXCEPTION - {0}: {1}, in file {2}, on line number: {3}"
                                 .format(sys.exc_info()[0].__name__, e, fname, exc_tb.tb_lineno), module, 4,
                                 'exception_occured')
