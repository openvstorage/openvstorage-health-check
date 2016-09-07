#!/usr/bin/python

# Copyright (C) 2016 iNuron NV
#
# This file is part of Open vStorage Open Source Edition (OSE),
# as available from
#
#      http://www.openvstorage.org and
#      http://www.openvstorage.com.
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)
# as published by the Free Software Foundation, in version 3 as it comes
# in the LICENSE.txt file of the Open vStorage OSE distribution.
#
# Open vStorage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY of any kind.

"""
Module for HealthCheckController
"""

from ovs.extensions.healthcheck.openvstorage.openvstoragecluster_health_check import OpenvStorageHealthCheck
from ovs.extensions.healthcheck.arakoon.arakooncluster_health_check import ArakoonHealthCheck
from ovs.extensions.healthcheck.utils.exceptions import PlatformNotSupportedException
from ovs.extensions.healthcheck.alba.alba_health_check import AlbaHealthCheck
from ovs.log.healthcheck_logHandler import HCLogHandler
from ovs.celery_run import celery


class HealthCheckController(object):
    
    MODULE = "healthcheck"
    PLATFORM = 0

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_self.unattended')
    def check_unattended():
        """
        Executes the healthcheck in UNATTENDED mode
        Check MK
        :return: results of the healthcheck
        :rtype: dict
        """

        unattended = True
        silent_mode = False

        # execute the check
        return HealthCheckController.execute_check(unattended, silent_mode)

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_attended')
    def check_attended():
        """
        Executes the healthcheck in ATTENDED mode

        :return: results of the healthcheck
        :rtype: dict
        """

        unattended = False
        silent_mode = False

        # execute the check
        return HealthCheckController.execute_check(unattended, silent_mode)

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_silent')
    def check_silent():
        """
        Executes the healthcheck in SILENT mode

        :return: results of the healthcheck
        :rtype: dict
        """

        unattended = False
        silent_mode = True

        # execute the check
        return HealthCheckController.execute_check(unattended, silent_mode)

    @staticmethod
    @celery.task(name='ovs.healthcheck.check')
    def execute_check(unattended=False, silent_mode=False):
        """
        Executes all available checks for the chosen HealthCheckController.PLATFORM
            * Vanilla (Open vStorage + Arakoon + Alba) = 0
            * Swift (Open vStorage + Arakoon + Swift) = 1
            * Ceph (Open vStorage + Arakoon + Ceph) = 2
            * Distributed FS (Open vStorage + Arakoon + Distributed FS) = 3
            * S3 (Open vStorage + Arakoon + S3) = 4

        :return: results of the healthcheck
        :rtype: dict
        """

        logger = HCLogHandler(not silent_mode and not unattended)

        if HealthCheckController.PLATFORM == 0:
            HealthCheckController.check_openvstorage(logger)
            HealthCheckController.check_arakoon(logger)
            HealthCheckController.check_alba(logger)
        else:
            raise PlatformNotSupportedException("Platform '{0}' is currently NOT supported".format(HealthCheckController.PLATFORM))

        return HealthCheckController.get_results(logger, unattended, silent_mode)

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_openvstorage')
    def check_openvstorage(logger):
        """
        Checks all critical components of Open vStorage
        """

        logger.info("Starting Open vStorage Health Check!", 'starting_ovs_hc')
        logger.info("====================================", 'starting_ovs_hc_ul')

        OpenvStorageHealthCheck.get_local_settings(logger)
        OpenvStorageHealthCheck.check_ovs_processes(logger)
        OpenvStorageHealthCheck.check_ovs_workers(logger)
        OpenvStorageHealthCheck.check_ovs_packages(logger)
        OpenvStorageHealthCheck.check_required_ports(logger)
        OpenvStorageHealthCheck.get_zombied_and_dead_processes(logger)
        OpenvStorageHealthCheck.check_required_dirs(logger)
        OpenvStorageHealthCheck.check_size_of_log_files(logger)
        OpenvStorageHealthCheck.check_if_dns_resolves(logger)
        OpenvStorageHealthCheck.check_model_consistency(logger)
        OpenvStorageHealthCheck.check_for_halted_volumes(logger)
        OpenvStorageHealthCheck.check_filedrivers(logger)
        OpenvStorageHealthCheck.check_volumedrivers(logger)

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_arakoon')
    def check_arakoon(logger):
        """
        Checks all critical components of Arakoon
        """

        logger.info("Starting Arakoon Health Check!", 'starting_arakoon_hc')
        logger.info("==============================", 'starting_arakoon_hc_ul')

        ArakoonHealthCheck.check_required_ports(logger)
        ArakoonHealthCheck.check_arakoons(logger)

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_alba')
    def check_alba(logger):
        """
        Checks all critical components of Alba
        """

        logger.info("Starting Alba Health Check!", 'starting_alba_hc')
        logger.info("===========================", 'starting_alba_hc_ul')

        AlbaHealthCheck.check_alba(logger)

    @staticmethod
    @celery.task(name='ovs.healthcheck.get_results')
    def get_results(logger, unattended, silent_mode):
        """
        Gets the result of the Open vStorage healthcheck

        :return: results & recap
        :rtype: dict with nested dicts
        """
        logger.info("Recap of Health Check!", 'starting_recap_hc')
        logger.info("======================", 'starting_recap_hc_ul')

        logger.success("SUCCESS={0} FAILED={1} SKIPPED={2} WARNING={3} EXCEPTION={4}"
                       .format(logger.counters['SUCCESS'], logger.counters['FAILED'], logger.counters['SKIPPED'], logger.counters['WARNING'],
                               logger.counters['EXCEPTION']), 'exception_occured')

        if silent_mode:
            result = logger.get_results(False)
        elif unattended:
            result = logger.get_results(True)
        # returns dict with minimal and detailed information
        else:
            return None
        return {'result': result, 'recap': {'SUCCESS': logger.counters['SUCCESS'],
                                            'FAILED': logger.counters['FAILED'],
                                            'SKIPPED': logger.counters['SKIPPED'],
                                            'WARNING': logger.counters['WARNING'],
                                            'EXCEPTION': logger.counters['EXCEPTION']}}
