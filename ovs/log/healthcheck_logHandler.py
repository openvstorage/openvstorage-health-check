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
LogHandler module for OVS health check
"""

import json
from ovs.extensions.healthcheck.utils.extension import Utils
from ovs.log.log_handler import LogHandler


class _Colors:
    """
    Colors for Open vStorage healthcheck logging
    """
    def __init__(self):
        """ Init method """
        pass

    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    SKIP = '\033[95m'
    ENDC = '\033[0m'


class HCLogHandler:
    """
    Open vStorage Log Handler
    """

    def __init__(self, unattended_mode, silent_mode=False):
        """
        Init method for the HealthCheck Log handler

        @param unattended_mode: determines the attended modus you are running
            * unattended run (for monitoring)
            * attended run (for user)
        @param silent_mode: determines if you are running in silent mode
            * silent run (to use in-code)

        @type unattended_mode: bool
        @type silent_mode: bool
        """

        # module specific
        self.module = "utils"

        # load config file
        with open(Utils.SETTINGS_LOC) as settings_file:
            self.settings = json.load(settings_file)

        # fetch from config file
        self.debug = self.settings["healthcheck"]["debug_mode"]
        self.enable = self.settings["healthcheck"]["logging"]["enable"]

        # utils log settings (determine modus)
        if silent_mode:
            # if silent_mode is true, the unattended is also true
            self.unattended_mode = True
            self.silent_mode = True
        else:
            self.unattended_mode = unattended_mode
            self.silent_mode = False

        # HC counters
        self.HC_failure = 0
        self.HC_success = 0
        self.HC_warning = 0
        self.HC_info = 0
        self.HC_exception = 0
        self.HC_skip = 0
        self.HC_debug = 0

        # result of healthcheck in dict form
        self.healthcheck_dict = {}

        self._logger = LogHandler.get("healthcheck")

    def failure(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :param module: describes the module you are logging from
        :return:
        """
        if self.enable:
            self._logger.error('FAILED - {0}'.format(msg))

        self.HC_failure += 1

        if not self.silent_mode:
            if self.unattended_mode:
                if unattended_print_mode:
                    print "{0} FAILED".format(unattended_mode_name)
                    self.healthcheck_dict[unattended_mode_name] = "FAILED"
            else:
                print _Colors.FAIL + "[FAILED] " + _Colors.ENDC + "%s" % (str(msg))
        else:
            if unattended_print_mode:
                self.healthcheck_dict[unattended_mode_name] = "FAILED"

    def success(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :param module: describes the module you are logging from
        :return:
        """
        if self.enable:
            self._logger.info('SUCCESS - {0}'.format(msg))
        self.HC_success += 1

        if not self.silent_mode:
            if self.unattended_mode:
                if unattended_print_mode:
                    print "{0} SUCCESS".format(unattended_mode_name)
                    self.healthcheck_dict[unattended_mode_name] = "SUCCESS"
            else:
                print _Colors.OKGREEN + "[SUCCESS] " + _Colors.ENDC + "%s" % (str(msg))
        else:
            if unattended_print_mode:
                self.healthcheck_dict[unattended_mode_name] = "SUCCESS"

    def warning(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :param module: describes the module you are logging from
        :return:
        """
        if self.enable:
            self._logger.warning('{0}'.format(msg))
        self.HC_warning += 1

        if not self.silent_mode:
            if self.unattended_mode:
                if unattended_print_mode:
                    print "{0} WARNING".format(unattended_mode_name)
                    self.healthcheck_dict[unattended_mode_name] = "WARNING"
            else:
                print _Colors.WARNING + "[WARNING] " + _Colors.ENDC + "%s" % (str(msg))
        else:
            if unattended_print_mode:
                self.healthcheck_dict[unattended_mode_name] = "WARNING"

    def info(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :param module: describes the module you are logging from
        :return:
        """
        if self.enable:
            self._logger.info('{0}'.format(msg))
        self.HC_info += 1

        # info_mode is NOT logged silently
        if not self.silent_mode:
            if self.unattended_mode:
                if unattended_print_mode:
                    print "{0} INFO".format(unattended_mode_name)
                    self.healthcheck_dict[unattended_mode_name] = "INFO"
            else:
                print _Colors.OKBLUE + "[INFO] " + _Colors.ENDC + "%s" % (str(msg))

    def exception(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :param module: describes the module you are logging from
        :return:
        """
        if self.enable:
            self._logger.exception('EXCEPTION - {0}'.format(msg))
        self.HC_exception += 1

        if not self.silent_mode:
            if self.unattended_mode:
                if unattended_print_mode:
                    print "{0} EXCEPTION".format(unattended_mode_name)
                    self.healthcheck_dict[unattended_mode_name] = "EXCEPTION"
            else:
                print _Colors.FAIL + "[EXCEPTION] " + _Colors.ENDC + "%s" % (str(msg))
        else:
            if unattended_print_mode:
                self.healthcheck_dict[unattended_mode_name] = "EXCEPTION"

    def skip(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :param module: describes the module you are logging from
        :return:
        """
        if self.enable:
            self._logger.info('SKIPPED - {0}'.format(msg))
        self.HC_skip += 1

        if not self.silent_mode:
            if self.unattended_mode:
                if unattended_print_mode:
                    print "{0} SKIPPED".format(unattended_mode_name)
                    self.healthcheck_dict[unattended_mode_name] = "SKIPPED"
            else:
                print _Colors.SKIP + "[SKIPPED] " + _Colors.ENDC + "%s" % (str(msg))

    def debug(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :param module: describes the module you are logging from
        :return:
        """
        if self.debug:
            if self.enable:
                self._logger.debug('{0}'.format(msg))
            self.HC_debug += 1
            print _Colors.OKBLUE + "[DEBUG] " + _Colors.ENDC + "%s" % (str(msg))
            self.healthcheck_dict[unattended_mode_name] = "DEBUG"
