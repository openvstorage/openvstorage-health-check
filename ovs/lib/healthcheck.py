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

import os
import inspect
import imp
import ast

from datetime import datetime, timedelta
from ovs.extensions.healthcheck.openvstorage.openvstoragecluster_health_check import OpenvStorageHealthCheck
from ovs.extensions.healthcheck.arakoon.arakooncluster_health_check import ArakoonHealthCheck
from ovs.extensions.healthcheck.utils.exceptions import PlatformNotSupportedException
from ovs.extensions.healthcheck.alba.alba_health_check import AlbaHealthCheck
from ovs.log.healthcheck_logHandler import HCLogHandler
from ovs.celery_run import celery

module = "healthcheck"
platform = 0
unattended = False
silent_mode = False
LOGGER = HCLogHandler(unattended, silent_mode)


class HealthCheckController(object):

    def __init__(self):
        pass

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_unattended')
    def check_unattended():
        """
        Executes the healthcheck in UNATTENDED mode

        :return: results of the healthcheck
        :rtype: dict
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

        :return: results of the healthcheck
        :rtype: dict
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

        :return: results of the healthcheck
        :rtype: dict
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

        :return: results of the healthcheck
        :rtype: dict
        """

        if platform == 0:
            HealthCheckController.check_openvstorage()
            HealthCheckController.check_arakoon()
            HealthCheckController.check_alba()
        else:
            raise PlatformNotSupportedException("Platform '{0}' is currently NOT supported".format(platform))

        return HealthCheckController.get_results()

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_openvstorage')
    def check_openvstorage():
        """
        Checks all critical components of Open vStorage
        """

        LOGGER.info("Starting Open vStorage Health Check!", 'starting_ovs_hc', False)
        LOGGER.info("====================================", 'starting_ovs_hc_ul', False)

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

        LOGGER.info("Starting Arakoon Health Check!", 'starting_arakoon_hc', False)
        LOGGER.info("==============================", 'starting_arakoon_hc_ul', False)

        arakoon = ArakoonHealthCheck(LOGGER)

        arakoon.check_required_ports()
        if not unattended and not silent_mode:
            print ""
        arakoon.check_arakoons()
        if not unattended and not silent_mode:
            print ""

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_alba')
    def check_alba():
        """
        Checks all critical components of Alba
        """

        LOGGER.info("Starting Alba Health Check!", 'starting_alba_hc', False)
        LOGGER.info("===========================", 'starting_alba_hc_ul', False)

        alba = AlbaHealthCheck(LOGGER)

        alba.check_alba()
        if not unattended and not silent_mode:
            print ""

    @staticmethod
    @celery.task(name='ovs.healthcheck.get_results')
    def get_results():
        """
        Gets the result of the Open vStorage healthcheck

        :return: results & recap
        :rtype: dict with nested dicts
        """

        LOGGER.info("Recap of Health Check!", 'starting_recap_hc', False)
        LOGGER.info("======================", 'starting_recap_hc_ul', False)

        LOGGER.success("SUCCESS={0} FAILED={1} SKIPPED={2} WARNING={3} EXCEPTION={4}"
                       .format(LOGGER.counters['SUCCESS'], LOGGER.counters['FAILED'], LOGGER.counters['SKIPPED'], LOGGER.counters['WARNING'],
                               LOGGER.counters['EXCEPTION']), 'exception_occured')

        if silent_mode or unattended:
            # returns dict with minimal and detailed information
            return {'result': LOGGER.healthcheck_dict, 'recap': {'SUCCESS': LOGGER.counters['SUCCESS'],
                                                                 'FAILED': LOGGER.counters['FAILED'],
                                                                 'SKIPPED': LOGGER.counters['SKIPPED'],
                                                                 'WARNING': LOGGER.counters['WARNING'],
                                                                 'EXCEPTION': LOGGER.counters['EXCEPTION']}}
        else:
            return None

    @staticmethod
    def _discover_methods(module_name=None, method_name=None):
        TEMP_FILE_PATH = '/tmp/_discover_methods'
        TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
        VERSION_ID = 1

        def search_dict(data):
            # Return without expire
            del data['expires']
            # Search the dict for the search terms
            if module_name or method_name:
                try:
                    for option in data[module_name]:
                        if method_name:
                            if option['method_name'] == method_name:
                                return {module_name: [option]}
                        else:
                            return {module_name: data[module_name]}
                except KeyError:
                    pass
            return data

        def build_cache():
            # Build cache
            # Executed from lib, want to go to extensions/healthcheck
            found_items = {'expires': (datetime.now() + timedelta(hours=2)).strftime(TIME_FORMAT)}
            path = ''.join(
                [os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)), '/extensions/healthcheck'])
            for root, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    if filename.endswith('.py') and filename != '__init__.py':
                        name = filename.replace('.py', '')
                        file_path = os.path.join(root, filename)
                        # Import file
                        mod = imp.load_source(name, file_path)
                        for member in inspect.getmembers(mod):
                            if inspect.isclass(member[1]) \
                                    and member[1].__module__ == name \
                                    and 'object' in [base.__name__ for base in member[1].__bases__]:
                                for submember in inspect.getmembers(member[1]):
                                    if hasattr(submember[1], 'module_name') and hasattr(submember[1], 'method_name'):
                                        if not submember[1].module_name in found_items:
                                            found_items[submember[1].module_name] = []
                                        found_items[submember[1].module_name] \
                                            .append({'method_name': submember[1].method_name,
                                                     'module_name': name,
                                                     'function': submember[1].__name__,
                                                     'class': member[1].__name__,
                                                     'location': file_path,
                                                     'version': VERSION_ID})
            # Write the dict to a temp file
            with open(TEMP_FILE_PATH, 'w') as f2:
                f2.write(str(found_items))
            return found_items
        try:
            with open(TEMP_FILE_PATH, 'r') as f:
                exposed_methods = ast.literal_eval(f.read())
        except IOError:
            # If file doesn't exist
            exposed_methods = None

        result = None
        # Search first to use old cache
        if exposed_methods:
            if not datetime.strptime(exposed_methods['expires'], TIME_FORMAT) > datetime.now() + timedelta(hours=2):
                result = search_dict(exposed_methods)
        if not result:
            exposed_methods = build_cache()
            result = search_dict(exposed_methods)
        return result

    @staticmethod
    def print_methods(mod=None, method=None):
        obj = HealthCheckController._discover_methods(mod, method)
        if mod:
            print "Possible options for '{0}' are: ".format(mod)
        else:
            print "Possible options are: "
        for mod in obj:
            for option in obj[mod]:
                print "ovs healthcheck {0} {1}".format(mod, option['method_name'])
        return obj

    @staticmethod
    def run_method(module_name=None, method_name=None, *args):
        # Special cases
        if module_name == 'help':
            return HealthCheckController.print_methods()
        elif module_name == 'unattended':
            return HealthCheckController.check_unattended()
        elif module_name == 'silent':
            return HealthCheckController.check_silent()
        elif not module_name and not method_name or module_name == 'attended':
            return HealthCheckController.check_attended()
        if not method_name or not module_name:
            print "Both the module name and the method name must be specified.".format(method_name, module_name)
            return HealthCheckController.print_methods(module_name, method_name)
        obj = HealthCheckController._discover_methods(module_name, method_name)
        # search the obj
        try:
            for option in obj[module_name]:
                if option['method_name'] == method_name:
                    mod = imp.load_source(option['module_name'], option['location'])
                    cl = getattr(mod, option['class'])
                    if len(args) > 0 and args[0] == 'help':
                        print getattr(cl, option['function']).__doc__
                        return
                    return getattr(cl, option['function'])(*args)
        except KeyError:
            print "Found no methods for mod {0}".format(module_name)
            return
        print "Found no method {0} for mod {1}".format(method_name, module_name)
        return HealthCheckController.print_methods()

if __name__ == '__main__':
    import sys
    from ovs.lib.healthcheck import HealthCheckController
    arguments = sys.argv
    # Remove filename
    del arguments[0]
    HealthCheckController.run_method(*arguments)
