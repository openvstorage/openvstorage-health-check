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
import ast
import imp
import os
import inspect
from datetime import datetime, timedelta
from ovs.extensions.healthcheck.result import HCResults
from ovs.log.log_handler import LogHandler


# class decorator
# noinspection PyPep8Naming
class expose_to_cli(object):
    def __init__(self, module_name=None, method_name=None):
        if module_name and method_name:
            self.module_name = module_name
            self.method_name = method_name

    def __call__(self, func):
        self.function = func
        func.module_name = self.module_name
        func.method_name = self.method_name
        return func
    
    
class CLIRunner(object):
    """
    Runs a method exposed by the expose_to_cli decorator. Serves as a base for all extensions using expose_to_cli
    """
    logger = LogHandler.get("ovs", "clirunner")
    OPTIONAL_ARGUMENTS = ["--help"]
    START_PATH = ''.join([os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))])

    def __init__(self):
        pass

    @classmethod
    def run_method(cls, *args):
        """
        Executes the given method
        :return:
        """
        module_name = ''
        method_name = ''
        # Extract option arguments
        optional_arguments = [arg for arg in cls.OPTIONAL_ARGUMENTS if arg in args]
        args = [arg for arg in args if arg not in optional_arguments]
        # Check for remaining arguments
        if len(args) >= 1:
            module_name = args[0]
        if len(args) >= 2:
            method_name = args[1]
        # Determine method to execute
        if (method_name and not module_name) or "--help" in optional_arguments:
            print "Both the module name and the method name must be specified.".format(method_name, module_name)
            return cls.print_help(module_name, method_name)
        # Find the required method and execute it
        discovered_data = cls._discover_methods(module_name, method_name)
        if discovered_data is None:
            print "Found no method {0} for module {1}".format(method_name, module_name)
            return cls.print_help(module_name)
        interrupted = False
        try:
            for exposed_module, exposed_methods in discovered_data.iteritems():
                if module_name and exposed_module != module_name:
                    continue
                for method_data in exposed_methods:
                    if not method_name or method_data['method_name'] == method_name:
                        mod = imp.load_source(method_data['module_name'], method_data['location'])
                        cl = getattr(mod, method_data['class'])()
                        if '--help' in optional_arguments:
                            print getattr(cl, method_data['function']).__doc__
                            return
                        # Execute method
                        try:
                            getattr(cl, method_data['function'])(*args)
                        except Exception:
                            cls.logger.exception('Error during execution of {0}.{1}'.format(cl, method_data['function']))
        except KeyboardInterrupt:
            interrupted = True
            cls.logger.warning('Caught keyboard interrupt. Output may be incomplete!')
        if interrupted is False:
            print "Found no methods for module {0}".format(module_name)
            return cls.print_help()

    @classmethod
    def _discover_methods(cls, module_name='', method_name=''):
        """
        Discovers all methods with the expose_to_cli decorator
        :param module_name:  module name specified with the cli
        :type module_name: str
        :param method_name: method name specified with the cli
        :type method_name: str
        :return: dict that contains the required info based on module_name and method_name
        :rtype: dict
        """
        temp_file_path = '/tmp/_discover_methods'
        time_format = "%Y-%m-%d %H:%M:%S"
        version_id = 1

        start_path = cls.START_PATH

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

        def build_cache(hours=2):
            """
            Builds the internal cache of the methods with expose_to_cli decorator. This cache expires within 2 hours
            :return: a dict the found items
            :rtype: dict
            """
            # Build cache
            # Executed from lib, want to go to extensions/healthcheck
            found_items = {'expires': (datetime.now() + timedelta(hours=hours)).strftime(time_format)}
            path = start_path
            for root, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    if filename.endswith('.py') and filename != '__init__.py':
                        name = filename.replace('.py', '')
                        file_path = os.path.join(root, filename)
                        # Import file
                        mod = imp.load_source(name, file_path)
                        for member in inspect.getmembers(mod):
                            if inspect.isclass(member[1]) and member[1].__module__ == name and 'object' in [base.__name__ for base in member[1].__bases__]:
                                for submember in inspect.getmembers(member[1]):
                                    if hasattr(submember[1], 'module_name') and hasattr(submember[1], 'method_name'):
                                        if not submember[1].module_name in found_items:
                                            found_items[submember[1].module_name] = []
                                        # noinspection PyUnresolvedReferences
                                        found_items[submember[1].module_name].append(
                                            {'method_name': submember[1].method_name,
                                             'module_name': name,
                                             'function': submember[1].__name__,
                                             'class': member[1].__name__,
                                             'location': file_path,
                                             'version': version_id
                                             })
            # Write the dict to a temp file
            with open(temp_file_path, 'w') as f2:
                f2.write(str(found_items))
            return found_items

        try:
            with open(temp_file_path, 'r') as f:
                exposed_methods = ast.literal_eval(f.read())
        except IOError:
            # If file doesn't exist
            exposed_methods = None

        result = None
        # Search first to use old cache
        if exposed_methods:
            if not datetime.strptime(exposed_methods['expires'], time_format) > datetime.now() + timedelta(hours=2):
                result = search_dict(exposed_methods)
        if not result:
            exposed_methods = build_cache()
            result = search_dict(exposed_methods)
        return result

    @classmethod
    def print_help(cls, module='', method=''):
        """
        Prints the possible methods that are exposed to the CLI
        :param module: module name specified with the cli
        :type module: str
        :param method: method name specified with the cli
        :type method: str
        :return: found cache
        :rtype: dict
        """
        print "Possible optional arguments are:"
        for arg in cls.OPTIONAL_ARGUMENTS:
            print "ovs healthcheck [module] [method] {0}".format(arg)
        cache = cls._discover_methods(module, method)
        if module:
            if cache is None:
                print "Found no methods for module {0}".format(module)
                return cls.print_help()
            else:
                print "Possible options for '{0}' are: ".format(module)
        else:
            print "Possible options are: "
        for module in cache:
            for option in cache[module]:
                print "ovs healthcheck {0} {1}".format(module, option['method_name'])
        return cache


class HealthCheckCLIRunner(CLIRunner):
    """
    Healthcheck adaptation of CLIRunner
    Injects a result_handler instance with shared resources to every test to collect the results.
    """
    logger = LogHandler.get("healthcheck", "clirunner")
    OPTIONAL_ARGUMENTS = CLIRunner.OPTIONAL_ARGUMENTS + ['--to-json', '--unattended']
    START_PATH = ''.join([os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)), '/healthcheck'])

    @staticmethod
    def run_method(*args):
        """
        Executes the given method
        :return:
        """
        module_name = ''
        method_name = ''
        # Extract option arguments
        optional_arguments = [arg for arg in HealthCheckCLIRunner.OPTIONAL_ARGUMENTS if arg in args]
        args = [arg for arg in args if arg not in optional_arguments]
        # Check for remaining arguments
        if len(args) >= 1:
            module_name = args[0]
        if len(args) >= 2:
            method_name = args[1]
        # Determine method to execute
        if (method_name and not module_name) or "--help" in optional_arguments:
            print "Both the module name and the method name must be specified.".format(method_name, module_name)
            return HealthCheckCLIRunner.print_help(module_name, method_name)
        # Find the required method and execute it
        discovered_data = HealthCheckCLIRunner._discover_methods(module_name, method_name)
        if discovered_data is None:
            print "Found no method {0} for module {1}".format(method_name, module_name)
            return HealthCheckCLIRunner.print_help(module_name)
        to_json = "--to-json" in optional_arguments
        unattended = "--unattended" in optional_arguments
        result_handler = HCResults(unattended, to_json)
        executed = False
        interrupted = False
        try:
            for exposed_module, exposed_methods in discovered_data.iteritems():
                if module_name and exposed_module != module_name:
                    continue
                for method_data in exposed_methods:
                    if not method_name or method_data['method_name'] == method_name:
                        mod = imp.load_source(method_data['module_name'], method_data['location'])
                        cl = getattr(mod, method_data['class'])()
                        if '--help' in optional_arguments:
                            print getattr(cl, method_data['function']).__doc__
                            return
                        # Execute method
                        try:
                            executed = True
                            getattr(cl, method_data['function'])(result_handler.HCResultCollector(result_handler, '{0}-{1}'.format(exposed_module, method_data['function'])))
                        except Exception as ex:
                            result_handler.exception('Uncaught exception during execution of {0}.{1}. Got {2}'.format(cl, method_data['function'], str(ex)))
                            HealthCheckCLIRunner.logger.exception('Error during execution of {0}.{1}'.format(cl, method_data['function']))
        except KeyboardInterrupt:
            interrupted = True
            result_handler.warning('Caught keyboard interrupt. Output may be incomplete!')
        # Get results
        if executed is True:
            return HealthCheckCLIRunner.get_results(result_handler, module_name, method_name)
        elif interrupted is False:
            print "Found no methods for module {0}".format(module_name)
            return HealthCheckCLIRunner.print_help()

    @staticmethod
    def get_results(result_handler, module_name=None, method_name=None):
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
        if module_name and method_name:
            recap_executer = '{0} {1}'.format(module_name, method_name)

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
