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

from ovs.extensions.healthcheck.openvstorage.openvstoragecluster_health_check import OpenvStorageHealthCheck
from ovs.extensions.healthcheck.arakoon.arakooncluster_health_check import ArakoonHealthCheck
from ovs.extensions.healthcheck.alba.alba_health_check import AlbaHealthCheck
from ovs.log.healthcheck_logHandler import HCLogHandler


class HealthCheckController:

    def __init__(self, unattended_run=False, silent_run=False):
        """
        Controller for the Open vStorage healthcheck

        @param unattended_run: determines the attended modus you are running
            * unattended run (for monitoring)
            * attended run (for user)
        @param silent_run: determines if you are running in silent mode
            * silent run (to use in-code)

        @type unattended_run: bool
        @type silent_run: bool

        @raises KeyboardInterrupt
        @raises Exception
        """

        self.module = "healthcheck"

        self.unattended = unattended_run
        self.silent_mode = silent_run
        self.LOGGER = HCLogHandler(self.unattended, self.silent_mode)
        self.alba = AlbaHealthCheck(self.LOGGER)
        self.arakoon = ArakoonHealthCheck(self.LOGGER)
        self.ovs = OpenvStorageHealthCheck(self.LOGGER)

        # determine platform on startup of healthcheck
        self.platform = 0

    @celery.task(name='ovs.healthcheck.check_all')
    def check_all(self):
        """
        Executes all available checks for the chosen platform
            * Vanilla (Open vStorage + Arakoon + Alba) = 0
            * Swift (Open vStorage + Arakoon + Swift) = 1
            * Ceph (Open vStorage + Arakoon + Ceph) = 2
            * Distributed FS (Open vStorage + Arakoon + Distributed FS) = 3
            * S3 (Open vStorage + Arakoon + S3) = 4

        @return: results of the healthcheck

        @rtype: dict

        @raises: Exception (When platform is not supported)
        """

        if self.platform == 0:
            self.check_openvstorage()
            self.check_arakoon()
            self.check_alba()
        else:
            raise Exception("Platform '{0}' is CURRENTLY NOT supported".format(platform))

        return self.get_results()

    @celery.task(name='ovs.healthcheck.check_openvstorage')
    def check_openvstorage(self):
        """
        Checks all critical components of Open vStorage
        """

        self.LOGGER.logger("Starting Open vStorage Health Check!", self.module, 3, 'starting_ovs_hc', False)
        self.LOGGER.logger("====================================\n", self.module, 3, 'starting_ovs_hc_ul', False)

        self.ovs.get_local_settings()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.check_ovs_processes()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.check_ovs_workers()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.check_ovs_packages()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.check_required_ports()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.get_zombied_and_dead_processes()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.check_required_dirs()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.check_hypervisor_management_information()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.check_size_of_log_files()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.check_if_dns_resolves()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.check_model_consistency()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.check_for_halted_volumes()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.check_filedrivers()
        if not self.unattended and not self.silent_mode:
            print ""
        self.ovs.check_volumedrivers()
        if not self.unattended and not self.silent_mode:
            print ""

    @celery.task(name='ovs.healthcheck.check_arakoon')
    def check_arakoon(self):
        """
        Checks all critical components of Arakoon
        """

        self.LOGGER.logger("Starting Arakoon Health Check!", self.module, 3, 'starting_arakoon_hc', False)
        self.LOGGER.logger("==============================\n", self.module, 3, 'starting_arakoon_hc_ul', False)

        self.arakoon.check_arakoons()
        if not self.unattended and not self.silent_mode:
            print ""

    @celery.task(name='ovs.healthcheck.check_alba')
    def check_alba(self):
        """
        Checks all critical components of Alba
        """

        self.LOGGER.logger("Starting Alba Health Check!", self.module, 3, 'starting_alba_hc', False)
        self.LOGGER.logger("===========================\n", self.module, 3, 'starting_alba_hc_ul', False)

        self.alba.check_alba()
        if not self.unattended and not self.silent_mode:
            print ""

    @celery.task(name='ovs.healthcheck.get_results')
    def get_results(self):
        """
        Gets the result of the Open vStorage healthcheck

        @return: results & recap

        @rtype: dict with nested dicts
        """

        self.LOGGER.logger("Recap of Health Check!", self.module, 3, 'starting_recap_hc', False)
        self.LOGGER.logger("======================\n", self.module, 3, 'starting_recap_hc_ul', False)

        self.LOGGER.logger("SUCCESSFULL={0} FAILED={1} SKIPPED={2} WARNING={3} EXCEPTION={4}"
                           .format(self.LOGGER.success, self.LOGGER.failure, self.LOGGER.skip, self.LOGGER.warning,
                                   self.LOGGER.exception), self.module, 1, 'exception_occured')

        if self.silent_mode or self.unattended:
            # returns dict with minimal and detailed information
            return {'result': self.LOGGER.healthcheck_dict, 'recap': {'SUCCESSFULL': self.LOGGER.success,
                                                                      'FAILED': self.LOGGER.failure,
                                                                      'SKIPPED': self.LOGGER.skip,
                                                                      'WARNING': self.LOGGER.warning,
                                                                      'EXCEPTION': self.LOGGER.exception}
                    }
        else:
            return None

if __name__ == '__main__':
    """
    Makes the healthcheck executable like so: "python healthcheck.py"
    """

    unattended = False
    silent_mode = False
    module = "healthcheck_controller"

    try:
        main = HealthCheckController(unattended, silent_mode)
        main.check_openvstorage()
        main.check_arakoon()
        main.check_alba()
        main.get_results()

    except KeyboardInterrupt as e:
        LOGGER = HCLogHandler(unattended, silent_mode)

        print ""
        LOGGER.logger("Recap of Health Check!", module, 3, 'starting_recap_hc', False)
        LOGGER.logger("======================\n", module, 3, 'starting_recap_hc_ul', False)
        LOGGER.logger("Open vStorage Health Check - Ended by USER through Keyboard", module,
                      4, 'exception_occured')
