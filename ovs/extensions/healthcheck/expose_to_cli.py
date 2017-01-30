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
import imp
import os
import inspect
from datetime import datetime, timedelta
from ovs.extensions.healthcheck.result import HCResults
from ovs.extensions.storage.volatilefactory import VolatileFactory
from ovs.log.log_handler import LogHandler


# class decorator
# noinspection PyPep8Naming
class expose_to_cli(object):
    def __init__(self, module_name, method_name, addon_type=None):
        self.module_name = module_name
        self.method_name = method_name
        self.addon_type = addon_type

    def __call__(self, func):
        func.expose_to_cli = {'module_name': self.module_name,
                              'method_name': self.method_name,
                              'addon_type': self.addon_type}
        return func
    
    
class CLIRunner(object):
    """
    Runs a method exposed by the expose_to_cli decorator. Serves as a base for all extensions using expose_to_cli
    """
    logger = LogHandler.get("ovs", "clirunner")
    START_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    CACHE_KEY = 'ovs_discover_method'
    _WILDCARD = 'X'

    def __init__(self):
        pass

    @classmethod
    def _get_methods(cls, module_name, method_name, addon_type=None):
        """
        Gets method by the specified values
        :param module_name: module to which the method belong
        :type module_name: str
        :param method_name: name of the method
        :type method_name: str
        :param addon_type: type of the method, distinguishes different addons
        :type addon_type: str
        :return: list of all found functions
        rtype: list[function]
        """
        result = []
        discovered_data = cls._discover_methods()
        module_names = discovered_data.keys() if module_name == cls._WILDCARD else [module_name]
        for module_name in module_names:
            for function_data in discovered_data[module_name]:
                if addon_type != function_data['addon_type'] or (method_name != cls._WILDCARD and method_name != function_data['method_name']):
                    continue
                mod = imp.load_source(function_data['module_name'], function_data['location'])
                cl = getattr(mod, function_data['class'])()
                result.append(getattr(cl, function_data['function']))
                if method_name == function_data['method_name']:
                    break
        return result

    @classmethod
    def extract_arguments(cls, *args):
        """
        Extracts arguments from the CLI
        Always expects a module_name and a method_name (the wildcard is X)
        :param args: arguments passed on by bash
        :return: tuple of module_name, method_name, bool if --help was in and remaining arguments
        :rtype: tuple(str, str, bool, list)
        """
        args = list(args)
        help_requested = False
        # Always expect at least X X
        if len(args) < 2:
            raise ValueError('Expecting at least {0} {0} as arguments.'.format(cls._WILDCARD))
        if '--help' in args[0:3]:
            args.remove('--help')
            help_requested = True
        return args.pop(0), args.pop(0), help_requested, args

    @classmethod
    def run_method(cls, *args):
        """
        Executes the given method
        :return: None
        :rtype: NoneType
        """
        module_name, method_name, help_requested, args = cls.extract_arguments(*args)
        found_method_pointers = cls._get_methods(module_name, method_name)
        if help_requested is True:
            cls.print_help(found_method_pointers)
            return
        try:
            for found_method in found_method_pointers:
                found_method(*args)
        except KeyboardInterrupt:
            cls.logger.warning('Caught keyboard interrupt. Output may be incomplete!')

    @classmethod
    def _discover_methods(cls):
        """
        Discovers all methods with the expose_to_cli decorator
        :return: dict that contains the required info based on module_name and method_name
        :rtype: dict
        """
        time_format = "%Y-%m-%d %H:%M:%S"
        version_id = 1
        start_path = cls.START_PATH
        client = VolatileFactory.get_client()
        cache_expirey_hours = 2  # Amount of hours the cache would expire

        def build_cache():
            """
            Build a dict listing all discovered methods with @expose_to_cli
            :return:  None
            :rtype: NoneType
            """
            # Build cache
            # Executed from lib, want to go to extensions/healthcheck
            found_items = {'expires': (datetime.now() + timedelta(hours=cache_expirey_hours)).strftime(time_format)}
            path = start_path
            for root, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    if not (filename.endswith('.py') and filename != '__init__.py'):
                        continue
                    name = filename.replace('.py', '')
                    file_path = os.path.join(root, filename)
                    # Import file
                    mod = imp.load_source(name, file_path)
                    for member in inspect.getmembers(mod):
                        if not (inspect.isclass(member[1]) and member[1].__module__ == name and 'object' in [base.__name__ for base in member[1].__bases__]):
                            continue
                        for submember in inspect.getmembers(member[1]):
                            if not hasattr(submember[1], 'expose_to_cli'):
                                continue
                            exposed_data = submember[1].expose_to_cli
                            method_module_name = exposed_data['module_name']
                            method_name = exposed_data['method_name']
                            method_addon_type = exposed_data['addon_type'] if 'addon_type' in exposed_data else None
                            if method_module_name not in found_items:
                                found_items[method_module_name] = []
                            # noinspection PyUnresolvedReferences
                            found_items[method_module_name].append(
                                {'method_name': method_name,
                                 'module_name': name,
                                 'function': submember[1].__name__,
                                 'class': member[1].__name__,
                                 'location': file_path,
                                 'version': version_id,
                                 'addon_type': method_addon_type}
                            )
            client.set(cls.CACHE_KEY, found_items)

        exposed_methods = client.get(cls.CACHE_KEY)
        # Search first to use old cache
        if exposed_methods and datetime.strptime(exposed_methods['expires'], time_format) > datetime.now() + timedelta(hours=cache_expirey_hours):
            del exposed_methods['expires']
            return exposed_methods
        build_cache()
        exposed_methods = client.get(cls.CACHE_KEY)
        del exposed_methods['expires']
        return exposed_methods

    @classmethod
    def print_help(cls, method_pointers):
        """
        Prints the possible methods that are exposed to the CLI
        :param method_pointers: list of method pointers
        :type method_pointers: list[function]
        :return: None
        :rtype: NoneType
        """
        print 'Possible optional arguments are:'
        if len(method_pointers) == 0:
            # Nothing found for the search terms
            print 'Found no methods matching your search terms.'
        elif len(method_pointers) == 1:
            # Found only one method -> search term was module_name + method_name
            print method_pointers[0].__doc__
        else:
            # Multiple entries found means only the module_name was supplied
            print 'ovs healthcheck {0} {0} -- will run all checks'.format(CLIRunner._WILDCARD)
            print 'ovs healthcheck MODULE {0} -- will run all checks for module'.format(CLIRunner._WILDCARD)
            # Sort based on module_name
            print_dict = {}
            for method_pointer in method_pointers:
                module_name = method_pointer.expose_to_cli['module_name']
                method_name = method_pointer.expose_to_cli['method_name']
                if module_name in print_dict:
                    print_dict[module_name].append(method_name)
                    continue
                print_dict[module_name] = [method_name]
            for module_name, method_names in print_dict.iteritems():
                for method_name in method_names:
                    print "ovs healthcheck {0} {1}".format(module_name, method_name)


class HealthCheckCLIRunner(CLIRunner):
    """
    Healthcheck adaptation of CLIRunner
    Injects a result_handler instance with shared resources to every test to collect the results.
    """
    logger = LogHandler.get("healthcheck", "clirunner")
    START_PATH = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)), 'healthcheck')
    ADDON_TYPE = 'healthcheck'

    @staticmethod
    def run_method(*args):
        """
        Executes the given method
        :return: None
        :rtype: NoneType
        """
        args = list(args)
        unattended = False
        to_json = False
        if '--unattended' in args:
            args.remove('--unattended')
            unattended = True
        if '--to-json' in args:
            args.remove('--to-json')
            to_json = True
        module_name, method_name, help_requested, args = HealthCheckCLIRunner.extract_arguments(*args)
        result_handler = HCResults(unattended, to_json)
        found_method_pointers = HealthCheckCLIRunner._get_methods(module_name, method_name, HealthCheckCLIRunner.ADDON_TYPE)
        if help_requested is True:
            HealthCheckCLIRunner.print_help(found_method_pointers)
            return
        try:
            for found_method in found_method_pointers:
                test_name = '{0}-{1}'.format(found_method.expose_to_cli['module_name'], found_method.expose_to_cli['method_name'])
                found_method(result_handler.HCResultCollector(result=result_handler, test_name=test_name))
            HealthCheckCLIRunner.get_results(result_handler, module_name, method_name)
        except KeyboardInterrupt:
            HealthCheckCLIRunner.logger.warning('Caught keyboard interrupt. Output may be incomplete!')
            HealthCheckCLIRunner.get_results(result_handler, module_name, method_name)

    @staticmethod
    def get_results(result_handler, module_name, method_name):
        """
        Gets the result of the Open vStorage healthcheck
        :param result_handler: result parser
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :param module_name:  module name specified with the cli
        :type module_name: str
        :param method_name: method name specified with the cli
        :type method_name: str
        :return: results & recap
        :rtype: dict
        """
        recap_executer = 'Health Check'
        if module_name != HealthCheckCLIRunner._WILDCARD:
            recap_executer = '{0} module {1}'.format(recap_executer, module_name)
        if method_name != HealthCheckCLIRunner._WILDCARD:
            recap_executer = '{0} test {1}'.format(recap_executer, method_name)

        result = result_handler.get_results()

        result_handler.info("Recap of {0}!".format(recap_executer))
        result_handler.info("======================")

        result_handler.info("SUCCESS={0} FAILED={1} SKIPPED={2} WARNING={3} EXCEPTION={4}"
                            .format(result_handler.counters['SUCCESS'], result_handler.counters['FAILED'],
                                    result_handler.counters['SKIPPED'], result_handler.counters['WARNING'],
                                    result_handler.counters['EXCEPTION']))
        # returns dict with minimal and detailed information
        return {'result': result, 'recap': {'SUCCESS': result_handler.counters['SUCCESS'],
                                            'FAILED': result_handler.counters['FAILED'],
                                            'SKIPPED': result_handler.counters['SKIPPED'],
                                            'WARNING': result_handler.counters['WARNING'],
                                            'EXCEPTION': result_handler.counters['EXCEPTION']}}
