# Copyright (C) 2017 iNuron NV
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

import os
import imp
import time
import click
import inspect
from ovs.extensions.healthcheck.decorators import node_check
from ovs.extensions.healthcheck.helpers.helper import Helper
from ovs.extensions.healthcheck.result import HCResults
from ovs.extensions.storage.volatilefactory import VolatileFactory
from ovs.extensions.healthcheck.logger import Logger


# noinspection PyPep8Naming
class expose_to_cli(object):
    """
    Class decorator which adds certain attributes so the method can be exposed
    """
    def __init__(self, module_name, method_name, addon_type=None):
        self.module_name = module_name
        self.method_name = method_name
        self.addon_type = addon_type

    def __call__(self, func):
        func.expose_to_cli = {'module_name': self.module_name,
                              'method_name': self.method_name,
                              'addon_type': self.addon_type}
        return func


######################################################################
# Generic implementation - perhaps the Framework could use these too #
######################################################################

class CLIContext(object):
    """
    Context object which holds some information
    """
    pass


class CLI(click.MultiCommand):
    """
    Click CLI which dynamically loads all possible commands
    Implementations require an entry point
    An entry point is defined as:
    @click.group(cls=CLI)
    def entry_point():
        pass

    if __name__ == '__main__':
        entry_point()
    """
    ADDON_TYPE = 'ovs'  # Type of addon the CLI is
    CACHE_KEY = 'ovs_discover_method'
    CACHE_EXPIRE_HOURS = 2  # Amount of hours the cache would expire
    GROUP_MODULE_CLASS = click.Group
    CMD_FOLDER = os.path.join(os.path.dirname(__file__))  # Folder to query for commands

    logger = Logger("ovs_clirunner")
    _volatile_client = VolatileFactory.get_client()
    _discovery_cache = {}

    def __init__(self, *args, **kwargs):
        super(CLI, self).__init__(*args, **kwargs)

    def list_commands(self, ctx):
        """
        Lists all possible commands found within the directory of this file
        All modules are retrieved
        :param ctx: Passed context
        :return: List of files to look for commands
        """
        sub_commands = self._discover_methods().keys()  # Returns all underlying modules
        sub_commands.sort()
        return sub_commands

    def get_command(self, ctx, name):
        """
        Retrieves a command to execute
        :param ctx: Passed context
        :param name: Name of the command
        :return: Function pointer to the command or None when no import could happen
        :rtype: callable
        """
        discovery_data = self._discover_methods()
        if name in discovery_data.keys():
            # The current passed name is a module. Wrap it up in a group and add all commands under it dynamically
            module_commands = {}
            for function_name, function_data in discovery_data[name].iteritems():
                # Register the decorated function as callback to click
                mod = imp.load_source(function_data['module_name'], function_data['location'])
                cl = getattr(mod, function_data['class'])()
                module_commands[function_name] = click.Command(function_name, callback=getattr(cl, function_data['function']))
            ret = self.GROUP_MODULE_CLASS(name, module_commands)
            return ret

    @classmethod
    def _discover_methods(cls):
        """
        Discovers all methods with the expose_to_cli decorator
        :return: dict that contains the required info based on module_name and method_name
        :rtype: dict
        """
        version_id = 1
        start_path = cls.CMD_FOLDER
        addon_type = cls.ADDON_TYPE

        # @todo remove
        cls._volatile_client.delete(cls.CACHE_KEY)
        def discover():
            """
            Build a dict listing all discovered methods with @expose_to_cli
            :return:  Dict with all discovered itms
            :rtype: dict
            """
            # Build cache
            # Executed from lib, want to go to extensions/healthcheck
            found_items = {'expires': time.time() + cls.CACHE_EXPIRE_HOURS * 60 ** 2}
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
                                found_items[method_module_name] = {}
                            # Only return when the addon type matches
                            if method_addon_type == addon_type:
                                # noinspection PyUnresolvedReferences
                                found_items[method_module_name][method_name] = {'method_name': method_name,
                                                                                'module_name': name,
                                                                                'function': submember[1].__name__,
                                                                                'class': member[1].__name__,
                                                                                'location': file_path,
                                                                                'version': version_id,
                                                                                'addon_type': method_addon_type}
            return found_items

        try:
            exposed_methods = cls._discovery_cache or cls._volatile_client.get(cls.CACHE_KEY)
            if exposed_methods and exposed_methods['expires'] > time.time():
                # Able to use the cache, has not expired yet
                del exposed_methods['expires']
                return exposed_methods
        except:
            cls.logger.exception('Unable to retrieve the exposed resources from cache')
        exposed_methods = discover()
        try:
            cls._discovery_cache = exposed_methods
            cls._volatile_client.set(cls.CACHE_KEY, exposed_methods)
        except:
            cls.logger.exception('Unable to cache the exposed resources')
        del exposed_methods['expires']
        return exposed_methods

###############################
# Healthcheck implementations #
###############################


class HealthcheckCLiContext(CLIContext):
    """
    Context object which holds some information
    """
    def __init__(self, result_handler):
        # type: (HCResults) -> None
        """
        Initialize a context item
        :param result_handler: Result handler to store results in.
        Serves as the main parent for the Healthcheck tests (stores the to-json/unattended)
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        """
        self.result_handler = result_handler
        self.modules = {}


class HealthcheckAddonGroup(CLI):
    """
    Healthcheck Addon group class
    A second separation was required to inject the correct result handler instance
    """
    ADDON_TYPE = 'healthcheck'

    def __init__(self, *args, **kwargs):
        super(HealthcheckAddonGroup, self).__init__(*args, **kwargs)

    def get_command(self, ctx, name):
        """
        Retrieves a command to execute
        :param ctx: Passed context
        :param name: Name of the command
        :return: Function pointer to the command or None when no import could happen
        :rtype: callable
        """
        discovery_data = self._discover_methods()  # Will be coming from cache
        result_handler = ctx.obj.result_handler
        current_module_name = ctx.command.name
        if current_module_name in discovery_data.keys():
            if name in discovery_data[current_module_name]:
                # Function found, inject the result handler
                function_data = discovery_data[current_module_name][name]
                mod = imp.load_source(function_data['module_name'], function_data['location'])
                cl = getattr(mod, function_data['class'])()
                method_to_run = getattr(cl, function_data['function'])
                # node_check(found_method)(result_handler.HCResultCollector(result=result_handler, test_name=test_name))  # Wrapped in nodecheck for callback
                result_collector = result_handler.HCResultCollector(result=result_handler, test_name=name)
                # Wrapping the function in a nodecheck to only test once at the same time
                # @todo support arguments passed in expose to cli
                return click.Command(name, callback=lambda: node_check(method_to_run)(result_collector))


class HealthcheckCLI(CLI):
    """
    Click CLI which dynamically loads all possible commands
    """
    UNATTENDED = '--unattended'
    TO_JSON = '--to-json'
    ADDON_TYPE = 'healthcheck'
    GROUP_MODULE_CLASS = HealthcheckAddonGroup

    logger = Logger("healthcheck-ovs_clirunner")

    def __init__(self, *args, **kwargs):
        """
        Initializes a CLI instance
        Injects a healthcheck specific callback
        """
        super(HealthcheckCLI, self).__init__(*args, **kwargs)
        self.result_callback = self.healthcheck_result_handler

    def parse_args(self, ctx, args):
        """
        Parses arguments. This method slices off to-json or attended for backwards compatibility
        """
        # Intercept --to-json and --help and put them in front so the group handles it
        # This is for backwards compatibility
        # but changes the help output for every command (no --unattended or --to-json listed as options)
        if self.UNATTENDED in args:
            args.remove(self.UNATTENDED)
            args.insert(0, self.UNATTENDED)
        if self.TO_JSON in args:
            args.remove(self.TO_JSON)
            args.insert(0, self.TO_JSON)
        super(HealthcheckCLI, self).parse_args(ctx, args)

    def get_command(self, ctx, name):
        """
        Retrieves a command to execute
        :param ctx: Passed context
        :param name: Name of the command
        :return: Function pointer to the command or None when no import could happen
        :rtype: callable
        """
        discovery_data = self._discover_methods()
        if name in discovery_data.keys():
            # The current passed name is a module. Wrap it up in a group and add all commands under it dynamically
            module_commands = {}
            ret = self.GROUP_MODULE_CLASS(name, module_commands)
            return ret

    @staticmethod
    @click.pass_context
    def healthcheck_result_handler(ctx, result, *args, **kwargs):
        """
        Handle the result printing of the Healthcheck
        :param ctx: Context object
        :param result: Result of the executed command
        :return:
        """
        _ = result
        hc_context = ctx.obj
        result_handler = hc_context.result_handler
        recap_executer = 'Health Check'
        result = result_handler.get_results()
        result_handler.info("Recap of {0}!".format(recap_executer))
        result_handler.info("======================")
        recount = []  # Order matters
        for severity in ['SUCCESS', 'FAILED', 'SKIPPED', 'WARNING', 'EXCEPTION']:
            recount.append((severity, result_handler.counter[severity]))
        result_handler.info(' '.join('{0}={1}'.format(s, v) for s, v in recount))
        # returns dict with minimal and detailed information
        return {'result': result, 'recap': dict(recount)}


@click.group(cls=HealthcheckCLI)
@click.option('--unattended', is_flag=True, help='Only output the results in a compact format')
@click.option('--to-json', is_flag=True, help='Only output the results in a JSON format')
@click.pass_context
def healthcheck_entry_point(ctx, unattended, to_json):
    """
    OpenvStorage healthcheck command line interface
    """
    # Provide a new instance of the results to collect all results within the complete healthcheck
    result_handler = HCResults(unattended=unattended, to_json=to_json)
    ctx.obj = HealthcheckCLiContext(result_handler)
    result_handler.info('Starting OpenvStorage Healthcheck version {0}'.format(Helper.get_healthcheck_version()))
    result_handler.info("======================")


# @todo remove
class HealthCheckCLIRunner(object):
    """
    Healthcheck adaptation of CLIRunner
    Injects a result_handler instance with shared resources to every test to collect the results.
    """
    logger = Logger("healthcheck-healthcheck_clirunner")
    START_PATH = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)), 'healthcheck')
    ADDON_TYPE = 'healthcheck'


if __name__ == '__main__':
    healthcheck_entry_point(['arakoon', 'ports-test', '--to-json'])
    # healthcheck_entry_point()
