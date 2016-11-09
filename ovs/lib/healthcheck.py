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

import ast
import imp
import os
import inspect
from ovs.celery_run import celery
from datetime import datetime, timedelta
from ovs.log.healthcheck_logHandler import HCLogHandler
from ovs.extensions.healthcheck.alba.alba_health_check import AlbaHealthCheck
from ovs.extensions.healthcheck.helpers.exceptions import PlatformNotSupportedException
from ovs.extensions.healthcheck.arakoon.arakooncluster_health_check import ArakoonHealthCheck
from ovs.extensions.healthcheck.volumedriver.volumedriver_health_check import VolumedriverHealthCheck
from ovs.extensions.healthcheck.openvstorage.openvstoragecluster_health_check import OpenvStorageHealthCheck


class HealthCheckController(object):
    
    MODULE = "healthcheck"
    PLATFORM = 0

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_self.unattended')
    def check_unattended():
        """
        Executes the healthcheck in UNATTENDED mode for e.g. Check_MK

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
    def execute_check(unattended=False, silent_mode=False, logger=None):
        """
        Executes all available checks

        :param unattended: unattendend mode?
        :type unattended: bool
        :param silent_mode: silent mode?
        :type silent_mode: bool
        :return: results of the healthcheck
        :param logger: logging object or none
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler or bool
        :rtype: dict
        """
        if logger is None:
            logger = HCLogHandler(not silent_mode and not unattended)

        if HealthCheckController.PLATFORM == 0:
            HealthCheckController.check_openvstorage(logger)
            HealthCheckController.check_volumedriver(logger)
            HealthCheckController.check_arakoon(logger)
            HealthCheckController.check_alba(logger)
        else:
            raise PlatformNotSupportedException("Platform '{0}' is currently NOT supported"
                                                .format(HealthCheckController.PLATFORM))

        return HealthCheckController.get_results(logger, unattended, silent_mode)

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_openvstorage')
    def check_openvstorage(logger):
        """
        Checks all critical components of Open vStorage

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        :returns
        """

        logger.info("Starting Open vStorage Health Check!", 'starting_ovs_hc')
        logger.info("====================================", 'starting_ovs_hc_ul')

        OpenvStorageHealthCheck.run(logger)

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_arakoon')
    def check_arakoon(logger):
        """
        Checks all critical components of Arakoon

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        :returns
        """

        logger.info("Starting Arakoon Health Check!", 'starting_arakoon_hc')
        logger.info("==============================", 'starting_arakoon_hc_ul')

        ArakoonHealthCheck.run(logger)

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_alba')
    def check_alba(logger):
        """
        Checks all critical components of Alba

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        :returns
        """

        logger.info("Starting Alba Health Check!", 'starting_alba_hc')
        logger.info("===========================", 'starting_alba_hc_ul')

        AlbaHealthCheck.run(logger)

    @staticmethod
    @celery.task(name='ovs.healthcheck.check_volumedriver')
    def check_volumedriver(logger):
        """
        Checks all critical components of Alba

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        :returns
        """

        logger.info("Starting Volumedriver Health Check!", 'starting_volumedriver_hc')
        logger.info("===================================", 'starting_volumedriver_hc_ul')

        VolumedriverHealthCheck.run(logger)

    @staticmethod
    @celery.task(name='ovs.healthcheck.get_results')
    def get_results(logger, unattended, silent_mode, module_name=None, method_name=None):
        """
        Gets the result of the Open vStorage healthcheck

        :param unattended: unattendend mode?
        :type unattended: bool
        :param silent_mode: silent mode?
        :type silent_mode: bool
        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        :return: results & recap
        :rtype: dict
        """
        recap_executer = 'Health Check'
        if (module_name and method_name) is not None:
            recap_executer = '{0} {1}'.format(module_name, method_name)

        logger.info("Recap of {0}!".format(recap_executer), 'starting_recap_hc')
        logger.info("======================", 'starting_recap_hc_ul')

        logger.info("SUCCESS={0} FAILED={1} SKIPPED={2} WARNING={3} EXCEPTION={4}"
                       .format(logger.counters['SUCCESS'], logger.counters['FAILED'],
                               logger.counters['SKIPPED'], logger.counters['WARNING'],
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

    @staticmethod
    def _discover_methods(module_name=None, method_name=None):
        """
        Discovers all methods with the exposecli decorator

        :param module_name:  module name specified with the cli
        :type module_name: str
        :param method_name: method name specified with the cli
        :type method_name: str
        :return: dict that contains the required info based on module_name and method_name
        :rtype: dict
        """
        TEMP_FILE_PATH = '/tmp/_discover_methods'
        TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
        VERSION_ID = 1

        def search_dict(data):
            """
            Searches the given data
            :param data: dict with modules and methods
            :type data: dict
            :return: dict with filtered modules and methods
            :rtype: dict
            """
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
            else:
                return data
            return None

        def build_cache():
            """
            Builds the internal cache of the methods with exposedcli decorator
            :return: a dict the found items
            :rtype: dict
            """
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
                                    if hasattr(submember[1], 'module_name') and hasattr(submember[1],
                                                                                        'method_name'):
                                        if not submember[1].module_name in found_items:
                                            found_items[submember[1].module_name] = []
                                        found_items[submember[1].module_name].append(
                                            {'method_name': submember[1].method_name,
                                             'module_name': name,
                                             'function': submember[1].__name__,
                                             'class': member[1].__name__,
                                             'location': file_path,
                                             'version': VERSION_ID
                                             })
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
        """
        Prints the possible methods that are exposed to the CLI
        :param mod: module name specified with the cli
        :type mod: str
        :param method: method name specified with the cli
        :type method: str
        :return: found cache
        :rtype: dict
        """
        cache = HealthCheckController._discover_methods(mod, method)
        if mod:
            if cache is None:
                print "Found no methods for module {0}".format(mod)
                return HealthCheckController.print_methods()
            else:
                print "Possible options for '{0}' are: ".format(mod)
        else:
            print "Possible options are: "
        for mod in cache:
            for option in cache[mod]:
                print "ovs healthcheck {0} {1}".format(mod, option['method_name'])
        return cache

    @staticmethod
    def run_method(module_name=None, method_name=None, *args):
        """
        Executes the given method
        :param module_name:  module name specified with the cli
        :type module_name: str
        :param method_name: method name specified with the cli
        :type method_name: str
        :return:
        """

        # Special cases
        if module_name == 'help':
            return HealthCheckController.print_methods()
        elif module_name == 'unattended':
            return HealthCheckController.check_unattended()
        elif module_name == 'silent':
            return HealthCheckController.check_silent()
        elif not module_name and not method_name or module_name == 'attended':
            return HealthCheckController.check_attended()
        # Determine method to execute
        if not method_name or not module_name:
            print "Both the module name and the method name must be specified.".format(method_name, module_name)
            return HealthCheckController.print_methods(module_name, method_name)

        # If help was added to a module name, print all possible options
        if method_name == 'help':
            return HealthCheckController.print_methods(module_name)

        obj = HealthCheckController._discover_methods(module_name, method_name)
        if obj is None:
            print "Found no method {0} for module {1}".format(method_name, module_name)
            return HealthCheckController.print_methods(module_name)
        # Find the required method and execute it
        for option in obj[module_name]:
            if option['method_name'] == method_name:
                mod = imp.load_source(option['module_name'], option['location'])
                cl = getattr(mod, option['class'])()
                if len(args) > 0 and args[0] == 'help':
                    print getattr(cl, option['function']).__doc__
                    return
                # Add a valid logger based on the optional arguments (unattended, silent) that could be present in args
                # Determine type of execution - default to attended
                unattended = False
                silent_mode = False
                if 'unattended' in args:
                    unattended = True
                    silent_mode = False
                elif 'silent' in args:
                    unattended = False
                    silent_mode = True

                logger = HCLogHandler(not silent_mode and not unattended)
                # Execute method
                getattr(cl, option['function'])(logger)
                # Get results
                HealthCheckController.get_results(logger, unattended, silent_mode, module_name, method_name)
                return
        print "Found no methods for module {0}".format(module_name)
        return HealthCheckController.print_methods()

    if __name__ == '__main__':
        import sys
        from ovs.lib.healthcheck import HealthCheckController
        arguments = sys.argv
        # Remove filename
        del arguments[0]
        # arguments = ('alba', 'disk-safety')
        HealthCheckController.run_method(*arguments)