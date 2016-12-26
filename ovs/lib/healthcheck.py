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
from datetime import datetime, timedelta
from ovs.extensions.healthcheck.result import HCResults
from ovs.log.log_handler import LogHandler


class HealthCheckController(object):
    
    logger = LogHandler.get("health_check", "controller")
    PLATFORM = 0
    OPTIONAL_ARGUMENTS = ["--to-json", "--unattended", "--help"]

    @staticmethod
    def get_results(result_handler, unattended, to_json, module_name=None, method_name=None):
        """
        Gets the result of the Open vStorage healthcheck

        :param unattended: unattendend mode?
        :type unattended: bool
        :param to_json: silent mode?
        :type to_json: bool
        :param result_handler: result parser
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: results & recap
        :rtype: dict
        """
        recap_executer = 'Health Check'
        if (module_name and method_name) is not None:
            recap_executer = '{0} {1}'.format(module_name, method_name)

        result_handler.info("Recap of {0}!".format(recap_executer), 'starting_recap_hc')
        result_handler.info("======================", 'starting_recap_hc_ul')

        result_handler.info("SUCCESS={0} FAILED={1} SKIPPED={2} WARNING={3} EXCEPTION={4}"
                            .format(result_handler.counters['SUCCESS'], result_handler.counters['FAILED'],
                                    result_handler.counters['SKIPPED'], result_handler.counters['WARNING'],
                                    result_handler.counters['EXCEPTION']))

        if to_json:
            result = result_handler.get_results(False)
        elif unattended:
            result = result_handler.get_results(True)
        # returns dict with minimal and detailed information
        else:
            return None
        return {'result': result, 'recap': {'SUCCESS': result_handler.counters['SUCCESS'],
                                            'FAILED': result_handler.counters['FAILED'],
                                            'SKIPPED': result_handler.counters['SKIPPED'],
                                            'WARNING': result_handler.counters['WARNING'],
                                            'EXCEPTION': result_handler.counters['EXCEPTION']}}

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
    def print_help(module=None, method=None):
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
        for arg in HealthCheckController.OPTIONAL_ARGUMENTS:
            print "ovs healthcheck [module] [method] {0}".format(arg)
        cache = HealthCheckController._discover_methods(module, method)
        if module:
            if cache is None:
                print "Found no methods for module {0}".format(module)
                return HealthCheckController.print_help()
            else:
                print "Possible options for '{0}' are: ".format(module)
        else:
            print "Possible options are: "
        for module in cache:
            for option in cache[module]:
                print "ovs healthcheck {0} {1}".format(module, option['method_name'])
        return cache

    @staticmethod
    def run_method(*args):
        """
        Executes the given method
        :return:
        """
        module_name = None
        method_name = None
        # Extract option arguments
        optional_arguments = [arg for arg in HealthCheckController.OPTIONAL_ARGUMENTS if arg in args]
        args = [arg for arg in args if arg not in optional_arguments]
        # Check for remaining arguments
        if len(args) >= 1:
            module_name = args[0]
        if len(args) >= 2:
            method_name = args[1]
        # Determine method to execute
        if (method_name is not None and module_name is None) or "--help" in optional_arguments:
            print "Both the module name and the method name must be specified.".format(method_name, module_name)
            return HealthCheckController.print_help(module_name, method_name)
        # Find the required method and execute it
        obj = HealthCheckController._discover_methods(module_name, method_name)
        if obj is None:
            print "Found no method {0} for module {1}".format(method_name, module_name)
            return HealthCheckController.print_help(module_name)
        to_json = "--to-json" in optional_arguments
        unattended = "--unattended" in optional_arguments
        result_handler = HCResults(not (unattended and to_json))
        executed = False
        for mod_name, options in obj.iteritems():
            if not (module_name is None or mod_name == module_name):
                continue
            for option in options:
                # Exclude combined tests: exposed via method_name = test
                if method_name is None or option['method_name'] == method_name:
                    mod = imp.load_source(option['module_name'], option['location'])
                    cl = getattr(mod, option['class'])()
                    if '--help' in optional_arguments:
                        print getattr(cl, option['function']).__doc__
                        return
                    # Execute method
                    try:
                        getattr(cl, option['function'])(result_handler)
                        executed = True
                    except:
                        HealthCheckController.logger.exception('Error during execution of {0}.{1}'.format(cl, option['function']))
                        raise
        # Get results
        if executed is True:
            return HealthCheckController.get_results(result_handler, unattended, to_json, module_name, method_name)
        else:
            print "Found no methods for module {0}".format(module_name)
            return HealthCheckController.print_help()

    if __name__ == '__main__':
        import sys
        from ovs.lib.healthcheck import HealthCheckController
        arguments = sys.argv
        # Remove filename
        del arguments[0]
        HealthCheckController.run_method(*arguments)
