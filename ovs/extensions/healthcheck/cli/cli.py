import os
import sys
import click
from ovs.extensions.healthcheck.result import HCResults


class HealthcheckCLiContext(object):
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


class HealthcheckCLI(click.MultiCommand):
    """
    Click CLI which dynamically loads all possible commands
    Registering a new set of commands:
    - create a file within this directory.
    - Add a method "cli" to it and register click decorators. Make sure that all commands are under a click.group with class 'HealthcheckAddonGroup'
    - All methods must return a HCResults instance
    """
    UNATTENDED = '--unattended'
    TO_JSON = '--to-json'

    cmd_folder = os.path.join(os.path.dirname(__file__))

    def __init__(self, *args, **kwargs):
        super(HealthcheckCLI, self).__init__(*args, **kwargs)
        self.result_callback = self.healthcheck_result_handler

    def parse_args(self, ctx, args):
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

    def list_commands(self, ctx):
        """
        Lists all possible commands found within the directory of this file
        :param ctx: Passed context
        :return: List of files to look for commands
        """
        commands = []
        for filename in os.listdir(self.cmd_folder):
            if filename.endswith('.py') and filename != '__init__.py' and filename != os.path.basename(__file__):
                commands.append(filename[:-3])  # Cut of .py
        commands.sort()
        return commands

    def get_command(self, ctx, name):
        """
        Retrieves a command to execute
        :param ctx: Passed context
        :param name: Name of the command
        :return: Function pointer to the command or None when no import could happen
        :rtype: callable
        """
        try:
            if sys.version_info[0] == 2:
                name = name.encode('ascii', 'replace')
            mod = __import__('ovs.extensions.healthcheck.cli.' + name, None, None, ['cli'])
        except ImportError:
            return
        return mod.cli

    @staticmethod
    @click.pass_context
    def healthcheck_result_handler(ctx, result, *args, **kwargs):
        """
        Handle the result printing of the Healthcheck
        :param ctx: Context object
        :param result: Result of the executed command
        :return:
        """
        if not isinstance(result, HCResults):
            raise ValueError('Unsupported result of command passed')
        hc_context = ctx.obj
        result_handler = hc_context.result_handler
        result_handler.combine(result)
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


class HealthcheckAddonGroup(click.Group):
    """
    Healthcheck Addon group class
    No callback should be registered onto this group
    - Automatically registers a callback which renames results of tests to to CLI exposed counter parts
    - Returns the HCResult instance towards the main CLI interface which then proceeds to print
    """
    def __init__(self, *args, **kwargs):
        super(HealthcheckAddonGroup, self).__init__(*args, **kwargs)
        self.result_callback = self.healthcheck_result_callback

    @staticmethod
    @click.pass_context
    def healthcheck_result_callback(ctx, result, *args, **kwargs):
        """
        Default callback for Healthcheck Addon Groups
        :return: The processed result
        """
        if not isinstance(result, HCResults):
            raise ValueError('The processed function returned an unsupported argument')
        # Attempt to rename result handler
        return result.rename('{0}-{1}'.format(ctx.command.name, ctx.invoked_subcommand))


@click.group(cls=HealthcheckCLI)
@click.option('--unattended', is_flag=True, help='Only output the results in a compact format')
@click.option('--to-json', is_flag=True, help='Only output the results in a JSON format')
@click.pass_context
def healthcheck_entry_point(ctx, unattended, to_json):
    """
    OpenvStorage healthcheck command line interface
    """
    # Provide a new instance of the results to collect all results within the complete healthcheck
    ctx.obj = HealthcheckCLiContext(HCResults(unattended=unattended, to_json=to_json))


if __name__ == '__main__':
    # healthcheck_entry_point(['arakoon', 'ports-test', '--to-json'])
    healthcheck_entry_point()
