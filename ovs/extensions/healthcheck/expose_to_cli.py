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


"""
Expose to CLI module. Depends on the python-click library
"""

from __future__ import absolute_import

import os
import imp
import sys
import copy
import time
import click
import inspect
from functools import wraps
from ovs.extensions.healthcheck.decorators import node_check
from ovs.extensions.healthcheck.result import HCResults
from ovs.extensions.storage.volatilefactory import VolatileFactory
from ovs.extensions.healthcheck.logger import Logger

# @todo Make it recursive. Current layout enforces SUBMODULE COMMAND, SUBMODULE, SUB, COMMAND is not possible


# noinspection PyPep8Naming
class expose_to_cli(object):
    """
    Class decorator which adds certain attributes so the method can be exposed
    Arguments can be passed using the python-click option decorator
    Example:
        import click
        @click.option('--to-json', default=False) -> will set to_json to False or w/e provided in the underlying function
    """
    attribute = '__expose_to_cli__'

    def __init__(self, module_name, method_name, addon_type=None, help=None, short_help=None):
        # type: (str, str, str, str, str) -> None
        # Change all arguments to a dict
        function_data = locals()
        function_data.pop('self', None)  # Exclude 'self'
        self.function_data = function_data

    def __call__(self, func):
        # type: (callable) -> callable
        setattr(func, self.attribute, self.function_data)
        return func

    @staticmethod
    def option(*param_decls, **attrs):
        # type: (*any, **any) -> callable
        """
        Decorator to create an option value for the exposed method
        Wraps around the click decorator
        :param param_decls: All possible param declarations (eg '--to-json', '-t')
        :param attrs: All possible attributes. See click.Option for all possible items
        """
        def wrapper(func):
            @wraps(func)
            def new_function(*args, **kwargs):
                return func(*args, **kwargs)
            return click.option(*param_decls, **attrs)(new_function)
        return wrapper


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
        # type: (*any, **any) -> None
        super(CLI, self).__init__(*args, **kwargs)

    def list_commands(self, ctx):
        # type: (click.Context) -> list[str]
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
        # type: (click.Context, str) -> callable
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
                # Try to avoid name collision with other modules. Might lead to unexpected results
                mod = imp.load_source('ovs_cli_{0}'.format(function_data['module_name']), function_data['location'])
                cl = getattr(mod, function_data['class'])()
                module_commands[function_name] = click.Command(function_name, callback=getattr(cl, function_data['function']))
            ret = self.GROUP_MODULE_CLASS(name, module_commands)
            return ret

    @classmethod
    def _discover_methods(cls):
        # type: () -> dict
        """
        Discovers all methods with the expose_to_cli decorator
        :return: dict that contains the required info based on module_name and method_name
        :rtype: dict
        """
        version_id = 1
        start_path = cls.CMD_FOLDER
        addon_type = cls.ADDON_TYPE

        def discover():
            """
            Build a dict listing all discovered methods with @expose_to_cli
            :return:  Dict with all discovered itms
            :rtype: dict
            """
            # Build cache
            found_items = {'expires': time.time() + cls.CACHE_EXPIRE_HOURS * 60 ** 2}
            path = start_path
            for root, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    if not (filename.endswith('.py') and filename != '__init__.py'):
                        continue
                    file_path = os.path.join(root, filename)
                    module_name = 'ovs_cli_{0}'.format(filename.replace('.py', ''))
                    # Import file, making it relative to the start path to avoid name collision.
                    # Without it, the module contents would be merged (eg. alba.py and testing/alba.py would be merged, overriding the path
                    # imp.load_source is different from importing. Therefore using the relative-joined name is safe
                    try:
                        mod = imp.load_source(module_name, file_path)
                    except ImportError:
                        cls.logger.exception('Unable to import module at {0}'.format(file_path))
                        continue
                    for member_name, member_value in inspect.getmembers(mod):
                        if not (inspect.isclass(member_value) and member_value.__module__ == module_name and 'object' in [base.__name__ for base in member_value.__bases__]):
                            continue
                        for submember_name, submember_value in inspect.getmembers(member_value):
                            if not hasattr(submember_value, expose_to_cli.attribute):
                                continue
                            exposed_data = getattr(submember_value, expose_to_cli.attribute)
                            method_module_name = exposed_data['module_name']
                            method_name = exposed_data['method_name']
                            method_addon_type = exposed_data['addon_type'] if 'addon_type' in exposed_data else None
                            if method_module_name not in found_items:
                                found_items[method_module_name] = {}
                            # Only return when the addon type matches
                            if method_addon_type == addon_type:
                                function_metadata = {'function': submember_value.__name__,
                                                     'class': member_value.__name__,
                                                     'location': file_path,
                                                     'version': version_id}
                                function_metadata.update(exposed_data)  # Add all exposed data for further re-use
                                found_items[method_module_name][method_name] = function_metadata
            return found_items

        def get_and_cache():
            found_items = cls._volatile_client.get(cls.CACHE_KEY)
            if found_items:
                cls._discovery_cache.update(found_items)
            return found_items

        try:
            exposed_methods = copy.deepcopy(cls._discovery_cache) or get_and_cache()
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

    @classmethod
    def clear_cache(cls):
        # type: () -> None
        """
        Clear all cache related to discovering methods
        :return: None
        :rtype: NoneType
        """
        cls._volatile_client.delete(cls.CACHE_KEY)


class CLIAddonGroup(CLI):
    """
    Handles retrieving the right command
    """
    # @todo make it recurive here. The depth of the relation should indicate returning a command or antoher CLIAddonGroup

    def __init__(self, *args, **kwargs):
        # type: (*any, **any) -> None
        super(CLIAddonGroup, self).__init__(*args, **kwargs)

    def list_commands(self, ctx):
        # type: (click.Context) -> list[str]
        """
        Lists all possible commands found for this addon group
        All modules are retrieved
        :param ctx: Passed context
        :return: List of files to look for commands
        """
        current_module_name = ctx.command.name
        discovery_data = self._discover_methods()  # Will be coming from cache
        sub_commands = discovery_data.get(current_module_name, {}).keys()
        sub_commands.sort()
        return sub_commands

    def run_methods_in_module(self, ctx):
        # type: (click.Context) -> None
        """
        Invoked when no test option was passed
        Runs all tests part of this module
        :param ctx: Context object
        """
        # When run with subcommand, allow it to passthrough for default behaviour
        if ctx.invoked_subcommand is None:
            # Invoked without sub command. Run all functions.
            with self.make_context(ctx.invoked_subcommand, self.list_commands(ctx), parent=ctx) as context:
                self.invoke(context)
            return

    def get_command(self, ctx, name):
        # type: (click.Context, str) -> click.Command
        """
        Retrieves a command to execute
        :param ctx: Passed context
        :param name: Name of the command
        :return: Function pointer to the command or None when no import could happen
        :rtype: callable
        """
        # @todo Make recursive with other groups
        discovery_data = self._discover_methods()  # Will be coming from cache
        current_module_name = ctx.command.name
        if current_module_name in discovery_data.keys():
            if name in discovery_data[current_module_name]:
                function_data = discovery_data[current_module_name][name]
                mod = imp.load_source(function_data['module_name'], function_data['location'])
                cl = getattr(mod, function_data['class'])()
                method_to_run = getattr(cl, function_data['function'])
                click_command = click.command(name=name,
                                              help=function_data.get('help'),
                                              short_help=function_data.get('short_help'))
                return click_command(method_to_run)

###############################
# Healthcheck implementations #
###############################


class HealthcheckTerminatedException(Exception):
    """
    Thrown when a test would be terminated by the user
    """
    def __init__(self, message=None, result_handler=None):
        super(HealthcheckTerminatedException, self).__init__(message)
        self.result_handler = result_handler


class HealthCheckCLiContext(CLIContext):
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


class HealthCheckShared(object):
    """
    Constants for the HealthcheckCLI
    """

    ADDON_TYPE = 'healthcheck'
    CACHE_KEY = 'ovs_healthcheck_discover_method'

    logger = Logger("healthcheck-ovs_clirunner")
    CMD_FOLDER = os.path.join(os.path.dirname(__file__), 'suites')  # Folder to query for commands

    @staticmethod
    def get_healthcheck_results(result_handler):
        # type (HCResults) -> dict
        """
        Output the Healthcheck results
        :param result_handler: HCResults instance
        :type result_handler: HCResults
        :return dict with information
        :rtype: dict
        """
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


class HealthcheckAddonGroup(CLIAddonGroup):
    """
    Healthcheck Addon group class
    A second separation was required to inject the correct result handler instance
    """
    # Explicitly setting these here because if this class would inherit from Shared too:
    # MRO would point to CLIAddonGroup first to resolve the attr
    ADDON_TYPE = HealthCheckShared.ADDON_TYPE
    CACHE_KEY = HealthCheckShared.CACHE_KEY
    CMD_FOLDER = HealthCheckShared.CMD_FOLDER

    logger = HealthCheckShared.logger

    def __init__(self, *args, **kwargs):
        # type: (*any, **any) -> None
        # Allow modules to be invoked without any other options behind them for backwards compatibility
        super(HealthcheckAddonGroup, self).__init__(chain=True,
                                                    invoke_without_command=True,
                                                    callback=click.pass_context(self.run_methods_in_module),
                                                    *args, **kwargs)

    def list_commands(self, ctx):
        # type: (click.Context) -> list[str]
        """
        Lists all possible commands found for this addon group
        All modules are retrieved
        :param ctx: Passed context
        :return: List of files to look for commands
        """
        current_module_name = ctx.command.name
        discovery_data = self._discover_methods()  # Will be coming from cache
        sub_commands = discovery_data.get(current_module_name, {}).keys()
        sub_commands.sort()
        return sub_commands

    def get_command(self, ctx, name):
        # type: (click.Context, str) -> click.Command
        """
        Retrieves a command to execute
        :param ctx: Passed context
        :param name: Name of the command
        :return: Function pointer to the command or None when no import could happen
        :rtype: callable
        """
        discovery_data = self._discover_methods()  # Will be coming from cache
        result_handler = ctx.obj.result_handler  # type: HCResults
        current_module_name = ctx.command.name
        if current_module_name in discovery_data.keys():
            if name in discovery_data[current_module_name]:
                # Function found, inject the result handler
                function_data = discovery_data[current_module_name][name]
                # Try to avoid name collision with other modules. Might lead to unexpected results
                mod = imp.load_source('healthcheck_{0}'.format(function_data['module_name']), function_data['location'])
                cl = getattr(mod, function_data['class'])()
                method_to_run = getattr(cl, function_data['function'])
                wrapped_function = (self.healthcheck_wrapper(result_handler, str(name))(method_to_run))  # Inject our Healthcheck arguments
                # Wrap around the click decorator to extract the option arguments
                click_command = click.command(name=name,
                                              help=function_data.get('help'),
                                              short_help=function_data.get('short_help'))
                return click_command(wrapped_function)

    def healthcheck_wrapper(self, result_handler, test_name):
        # type: (HCResults, str) -> callable
        """
        Healthcheck function decorator to run Healthcheck test methods while preserving all context
        - changes the name of the passed function to the new desired one
        - Injects the result collector instance
        - Preserves all other options
        :param result_handler: The result handler instance
        :type result_handler: HCResults
        :param test_name: Name of the test to run
        :type test_name: str
        """
        result_collector = result_handler.HCResultCollector(result=result_handler, test_name=test_name)

        def wrapper(func):
            """
            Wrapper function
            :param func: Then function to wrap
            :type func: callable
            :return: New wrapped function
            :rtype: callable
            """
            @wraps(func)
            def new_function(*args, **kwargs):
                """
                Wrapping function. Injects the result collector and captures any exceptions that might occur
                """
                if not result_handler.started:
                    result_handler.log_start_of_application()

                try:
                    return func(result_handler=result_collector, *args, **kwargs)
                except (click.Abort, KeyboardInterrupt):
                    self.logger.warning('Caught keyboard interrupt during {0}. Output may be incomplete!'.format(test_name))
                    raise HealthcheckTerminatedException(result_handler=result_handler)  # Will be handled more globally. The whole Healthcheck should abort
                except:
                    self.logger.exception('Unhandled exception caught when executing {0}'.format(test_name))
                    result_handler.exception('Unhandled exception caught when executing {0}'.format(test_name))
            # Change the name to the desired one
            new_function.__name__ = test_name
            # Wrap around a node check to only test once per node
            return node_check(new_function)
        return wrapper

    def run_methods_in_module(self, ctx):
        """
        Invoked when no test option was passed
        Runs all tests part of this module
        :param ctx: Context object
        """
        # When run with subcommand, allow it to passthrough for default behaviour
        if ctx.invoked_subcommand is None:
            # Invoked without sub command. Run all functions.
            with self.make_context(ctx.invoked_subcommand, self.list_commands(ctx), parent=ctx) as context:
                self.invoke(context)
            return


class HealthCheckCLI(CLI):
    """
    Click CLI which dynamically loads all possible commands
    """
    UNATTENDED = '--unattended'
    TO_JSON = '--to-json'
    GROUP_MODULE_CLASS = HealthcheckAddonGroup

    # Explicitly setting these here because if this class would inherit from Shared too:
    # MRO would point to CLIAddonGroup first to resolve the attr
    ADDON_TYPE = HealthCheckShared.ADDON_TYPE
    CACHE_KEY = HealthCheckShared.CACHE_KEY
    CMD_FOLDER = HealthCheckShared.CMD_FOLDER

    logger = HealthCheckShared.logger

    def __init__(self, *args, **kwargs):
        # type: (*any, **any) -> None
        """
        Initializes a CLI instance
        Injects a healthcheck specific callback
        """
        super(HealthCheckCLI, self).__init__(chain=True,
                                             invoke_without_command=True,
                                             result_callback=self.healthcheck_result_handler,
                                             *args, **kwargs)

    def parse_args(self, ctx, args):
        # type: (click.Context, list) -> None
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
        super(HealthCheckCLI, self).parse_args(ctx, args)

    def get_command(self, ctx, name):
        # type: (click.Context, str) -> HealthcheckAddonGroup
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
            ret = self.GROUP_MODULE_CLASS(name=name)
            return ret

    @staticmethod
    @click.pass_context
    def healthcheck_result_handler(ctx, result, *args, **kwargs):
        # type: (click.Context, any, *any, **any) -> dict
        """
        Handle the result printing of the Healthcheck
        :param ctx: Context object
        :param result: Result of the executed command
        """
        _ = result, args, kwargs
        hc_context = ctx.obj
        result_handler = hc_context.result_handler
        return HealthCheckShared.get_healthcheck_results(result_handler)

    def main(self, args=None, prog_name=None, complete_var=None, standalone_mode=False, **extra):
        # type: (list, str, bool, bool, **any) -> dict
        try:
            return super(HealthCheckCLI, self).main(args, prog_name, complete_var, standalone_mode, **extra)
        except (click.Abort, KeyboardInterrupt):
            # Aborted before running any command. Print and return an empty result to stdout.
            # Unable to capture output params in this stage as it is handled by the main method
            result_handler = HCResults()
            result_handler.failure('Terminated before starting!')
            return HealthCheckShared.get_healthcheck_results(result_handler)
        except HealthcheckTerminatedException as ex:
            self.logger.warning('Caught keyboard interrupt while testing. Output may be incomplete!')
            result_handler = ex.result_handler  # type: HCResults
            # Raised when an invoked command was aborted. The invoked command will output all results and then raise the exception
            return HealthCheckShared.get_healthcheck_results(result_handler)
        except click.ClickException as e:
            e.show()
            sys.exit(e.exit_code)

    def invoke(self, ctx):
        """
        Wrap around the invoking part to capture any keyboard interrupts so the main can print a decent log
        """
        try:
            return super(HealthCheckCLI, self).invoke(ctx)
        except (click.Abort, KeyboardInterrupt):
            raise HealthcheckTerminatedException(result_handler=ctx.obj.result_handler)


@click.group(cls=HealthCheckCLI)
@click.option('--unattended', is_flag=True, help='Only output the results in a compact format')
@click.option('--to-json', is_flag=True, help='Only output the results in a JSON format')
@click.pass_context
def healthcheck_entry_point(ctx, unattended, to_json):
    # type: (click.Context, bool, bool) -> any
    """
    OpenvStorage healthcheck command line interface
    """
    # Will be the 'callback' method for the HealthcheckCLi instance
    # Provide a new instance of the results to collect all results within the complete healthcheck
    result_handler = HCResults(unattended=unattended, to_json=to_json)
    ctx.obj = HealthCheckCLiContext(result_handler)
    # When run with subcommand, it will fetch the command to execute
    if ctx.invoked_subcommand is None:
        # Invoked without sub command. Run all functions.
        cli_instance = ctx.command  # type: HealthCheckCLI
        for sub_command in cli_instance.list_commands(ctx):
            ctx.invoke(cli_instance.get_command(ctx, sub_command))
        return result_handler


class HealthCheckCLIRunner(object):
    """
    For backwards compatibility
    """

    @classmethod
    def run_method(cls, *args, **kwargs):
        # type (*any, **any) -> any
        """
        Executes the given method like it would be executed through the CLI
        """
        if not isinstance(args, tuple):
            args = (args,)
        return healthcheck_entry_point(args)
