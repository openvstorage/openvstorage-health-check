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

from ovs.celery_run import celery
from ovs.extensions.healthcheck.openvstorage.openvstoragecluster_health_check import OpenvStorageHealthCheck
from ovs.extensions.healthcheck.arakoon.arakooncluster_health_check import ArakoonHealthCheck
from ovs.extensions.healthcheck.alba.alba_health_check import AlbaHealthCheck
from ovs.log.healthcheck_logHandler import HCLogHandler

module = "healthcheck"
platform = 0
unattended = False
silent_mode = False
LOGGER = HCLogHandler(unattended, silent_mode)

class HealthCheckController:

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_unattended')
    def check_unattended():
        """
        Executes the healthcheck in UNATTENDED mode

        @return: results of the healthcheck

        @rtype: dict

        @raises: Exception (When platform is not supported)
        """

        # initialize variables as global
        global LOGGER
        global unattended
        global silent_mode

        # initialize modus variables
        unattended = True
        silent_mode = False
        LOGGER = HCLogHandler(unattended, silent_mode)

        # execute the check
        return HealthCheckController.execute_check()

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_attended')
    def check_attended():
        """
        Executes the healthcheck in ATTENDED mode

        @return: results of the healthcheck

        @rtype: dict

        @raises: Exception (When platform is not supported)
        """

        # initialize variables as global
        global LOGGER
        global unattended
        global silent_mode

        # initialize modus variables
        unattended = False
        silent_mode = False
        LOGGER = HCLogHandler(unattended, silent_mode)

        # execute the check
        return HealthCheckController.execute_check()

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_silent')
    def check_silent():
        """
        Executes the healthcheck in SILENT mode

        @return: results of the healthcheck

        @rtype: dict

        @raises: Exception (When platform is not supported)
        """

        # initialize variables as global
        global LOGGER
        global unattended
        global silent_mode

        # initialize modus variables
        unattended = False
        silent_mode = True
        LOGGER = HCLogHandler(unattended, silent_mode)

        # execute the check
        return HealthCheckController.execute_check()

    @staticmethod
    @celery.task(name='ovs.healthcheck.check')
    def execute_check():
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

        if platform == 0:
            HealthCheckController.check_openvstorage()
            HealthCheckController.check_arakoon()
            HealthCheckController.check_alba()
        else:
            raise Exception("Platform '{0}' is CURRENTLY NOT supported".format(platform))

        return HealthCheckController.get_results()

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_openvstorage')
    def check_openvstorage():
        """
        Checks all critical components of Open vStorage
        """

        LOGGER.logger("Starting Open vStorage Health Check!", module, 3, 'starting_ovs_hc', False)
        LOGGER.logger("====================================\n", module, 3, 'starting_ovs_hc_ul', False)

        ovs = OpenvStorageHealthCheck(LOGGER)

        ovs.get_local_settings()
        if not unattended and not silent_mode:
            print ""
        ovs.check_ovs_processes()
        if not unattended and not silent_mode:
            print ""
        ovs.check_ovs_workers()
        if not unattended and not silent_mode:
            print ""
        ovs.check_ovs_packages()
        if not unattended and not silent_mode:
            print ""
        ovs.check_required_ports()
        if not unattended and not silent_mode:
            print ""
        ovs.get_zombied_and_dead_processes()
        if not unattended and not silent_mode:
            print ""
        ovs.check_required_dirs()
        if not unattended and not silent_mode:
            print ""
        ovs.check_hypervisor_management_information()
        if not unattended and not silent_mode:
            print ""
        ovs.check_size_of_log_files()
        if not unattended and not silent_mode:
            print ""
        ovs.check_if_dns_resolves()
        if not unattended and not silent_mode:
            print ""
        ovs.check_model_consistency()
        if not unattended and not silent_mode:
            print ""
        ovs.check_for_halted_volumes()
        if not unattended and not silent_mode:
            print ""
        ovs.check_filedrivers()
        if not unattended and not silent_mode:
            print ""
        ovs.check_volumedrivers()
        if not unattended and not silent_mode:
            print ""

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_arakoon')
    def check_arakoon():
        """
        Checks all critical components of Arakoon
        """

        LOGGER.logger("Starting Arakoon Health Check!", module, 3, 'starting_arakoon_hc', False)
        LOGGER.logger("==============================\n", module, 3, 'starting_arakoon_hc_ul', False)

        arakoon = ArakoonHealthCheck(LOGGER)

        arakoon.check_arakoons()
        if not unattended and not silent_mode:
            print ""

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_alba')
    def check_alba():
        """
        Checks all critical components of Alba
        """

        LOGGER.logger("Starting Alba Health Check!", module, 3, 'starting_alba_hc', False)
        LOGGER.logger("===========================\n", module, 3, 'starting_alba_hc_ul', False)

        alba = AlbaHealthCheck(LOGGER)

        alba.check_alba()
        if not unattended and not silent_mode:
            print ""

    @staticmethod
    @celery.task(name='ovs.healthcheck.get_results')
    def get_results():
        """
        Gets the result of the Open vStorage healthcheck

        @return: results & recap

        @rtype: dict with nested dicts
        """

        LOGGER.logger("Recap of Health Check!", module, 3, 'starting_recap_hc', False)
        LOGGER.logger("======================\n", module, 3, 'starting_recap_hc_ul', False)

        LOGGER.logger("SUCCESSFULL={0} FAILED={1} SKIPPED={2} WARNING={3} EXCEPTION={4}"
                      .format(LOGGER.success, LOGGER.failure, LOGGER.skip, LOGGER.warning,
                              LOGGER.exception), module, 1, 'exception_occured')

        if silent_mode or unattended:
            # returns dict with minimal and detailed information
            return {'result': LOGGER.healthcheck_dict, 'recap': {'SUCCESSFULL': LOGGER.success,
                                                                 'FAILED': LOGGER.failure,
                                                                 'SKIPPED': LOGGER.skip,
                                                                 'WARNING': LOGGER.warning,
                                                                 'EXCEPTION': LOGGER.exception}
                    }
        else:
            return None
