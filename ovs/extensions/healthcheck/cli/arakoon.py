# Copyright (C) 2018 iNuron NV
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
Command line interface for Arakoon
"""

import click
from ovs.extensions.healthcheck.cli.cli import HealthcheckAddonGroup
from ovs.extensions.healthcheck.arakoon_hc import ArakoonHealthCheck


# Decorator which will retrieve the HCResults instance created by the "healthcheck_entry_point" function
MODULE = 'arakoon'


@click.group('arakoon', cls=HealthcheckAddonGroup)
@click.pass_context
def cli(ctx):
    # Main entry point for the Arakoon Healthcheck
    """
    Arakoon module of the Healthcheck
    """
    hc_context = ctx.obj
    result_handler = hc_context.result_handler
    hc_context.modules[MODULE] = ArakoonHealthCheck(result_handler)


@cli.command(name='ports-test')
@click.option('--my-option', is_flag=True, help='Only output the results in a JSON format')
@click.pass_context
def ports_test(ctx, my_option):
    arakoon_hc = ctx.obj.modules[MODULE]  # type: ArakoonHealthCheck
    return arakoon_hc.check_arakoon_ports()
