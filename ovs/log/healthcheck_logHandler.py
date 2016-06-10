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

import datetime
import json
import os
from ovs.extensions.healthcheck.utils.extension import Utils


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
        self.HEALTHCHECK_DIR = self.settings["healthcheck"]["logging"]["directory"]
        self.HEALTHCHECK_FILE = self.settings["healthcheck"]["logging"]["file"]
        self.debug = self.settings["healthcheck"]["debug_mode"]

        # utils log settings (determine modus)
        if silent_mode:
            # if silent_mode is true, the unattended is also true
            self.unattended_mode = True
            self.silent_mode = True
        else:
            self.unattended_mode = unattended_mode
            self.silent_mode = False

        # HC counters
        self.failure = 0
        self.success = 0
        self.warning = 0
        self.info = 0
        self.exception = 0
        self.skip = 0
        self.debug = 0

        # result of healthcheck in dict form
        self.healthcheck_dict = {}

        # create if dir does not exists
        if not os.path.isdir(self.HEALTHCHECK_DIR):
            os.makedirs(self.HEALTHCHECK_DIR)

    def logger(self, message, module, log_type, unattended_mode_name, unattended_print_mode=True):
        """
        Logs the healthcheck output in a certain way chosen by the user

        @param message: Log message for attended run
        @param module: describes the module you are logging from
        @param log_type: describes the log level
            * failure = 0
            * success = 1
            * warning = 2
            * info = 3
            * exception = 4
            * skip = 5
            * debug = 6
        @param unattended_mode_name: name for monitoring output
        @param unattended_print_mode: describes if you want to print the output during a unattended run

        @type message: str
        @type module: str
        @type log_type: int
        @type unattended_print_mode: bool
        @type unattended_mode_name: str
        """

        try:
            target = open('{0}/{1}'.format(self.HEALTHCHECK_DIR, self.HEALTHCHECK_FILE), 'a')
            now = datetime.datetime.now()

            if log_type == 0:
                target.write("{0} - [FAILURE] - [{1}] - {2}\n".format(now, module, message))
                self.failure += 1

                if not self.silent_mode:
                    if self.unattended_mode:
                        if unattended_print_mode:
                            print "{0} FAILURE".format(unattended_mode_name)
                            self.healthcheck_dict[unattended_mode_name] = "FAILURE"
                    else:
                        print _Colors.FAIL + "[FAILURE] " + _Colors.ENDC + "%s" % (str(message))
                else:
                    if unattended_print_mode:
                        self.healthcheck_dict[unattended_mode_name] = "FAILURE"

            elif log_type == 1:
                target.write("{0} - [SUCCESS] - [{1}] - {2}\n".format(now, module, message))
                self.success += 1

                if not self.silent_mode:
                    if self.unattended_mode:
                        if unattended_print_mode:
                            print "{0} SUCCESS".format(unattended_mode_name)
                            self.healthcheck_dict[unattended_mode_name] = "SUCCESS"
                    else:
                        print _Colors.OKGREEN + "[SUCCESS] " + _Colors.ENDC + "%s" % (str(message))
                else:
                    if unattended_print_mode:
                        self.healthcheck_dict[unattended_mode_name] = "SUCCESS"

            elif log_type == 2:
                target.write("{0} - [WARNING] - [{1}] - {2}\n".format(now, module, message))
                self.warning += 1

                if not self.silent_mode:
                    if self.unattended_mode:
                        if unattended_print_mode:
                            print "{0} WARNING".format(unattended_mode_name)
                            self.healthcheck_dict[unattended_mode_name] = "WARNING"
                    else:
                        print _Colors.WARNING + "[WARNING] " + _Colors.ENDC + "%s" % (str(message))
                else:
                    if unattended_print_mode:
                        self.healthcheck_dict[unattended_mode_name] = "WARNING"

            elif log_type == 3:
                target.write("{0} - [INFO] - [{1}] - {2}\n".format(now, module, message))
                self.info += 1

                # info_mode is NOT logged silently
                if not self.silent_mode:
                    if self.unattended_mode:
                        if unattended_print_mode:
                            print "{0} INFO".format(unattended_mode_name)
                            self.healthcheck_dict[unattended_mode_name] = "INFO"
                    else:
                        print _Colors.OKBLUE + "[INFO] " + _Colors.ENDC + "%s" % (str(message))

            elif log_type == 4:
                target.write("{0} - [EXCEPTION] - [{1}] - {2}\n".format(now, module, message))
                self.exception += 1

                if not self.silent_mode:
                    if self.unattended_mode:
                        if unattended_print_mode:
                            print "{0} EXCEPTION".format(unattended_mode_name)
                            self.healthcheck_dict[unattended_mode_name] = "EXCEPTION"
                    else:
                        print _Colors.FAIL + "[EXCEPTION] " + _Colors.ENDC + "%s" % (str(message))
                else:
                    if unattended_print_mode:
                        self.healthcheck_dict[unattended_mode_name] = "EXCEPTION"

            elif log_type == 5:
                target.write("{0} - [SKIPPED] - [{1}] - {2}\n".format(now, module, message))
                self.skip += 1

                if not self.silent_mode:
                    if self.unattended_mode:
                        if unattended_print_mode:
                            print "{0} SKIPPED".format(unattended_mode_name)
                            self.healthcheck_dict[unattended_mode_name] = "SKIPPED"
                    else:
                        print _Colors.SKIP + "[SKIPPED] " + _Colors.ENDC + "%s" % (str(message))
                else:
                    if unattended_print_mode:
                        self.healthcheck_dict[unattended_mode_name] = "SKIPPED"

            elif log_type == 6:
                if self.debug:
                    target.write("{0} - [DEBUG] - [{1}] - {2}\n".format(now, module, message))
                    self.debug += 1
                    print _Colors.OKBLUE + "[DEBUG] " + _Colors.ENDC + "%s" % (str(message))
                    self.healthcheck_dict[unattended_mode_name] = "DEBUG"

            else:
                target.write("{0} - [UNEXPECTED_EXCEPTION] - [{1}] - {2}\n".format(now, module, message))
                self.exception += 1

                if not self.silent_mode:
                    if self.unattended_mode:
                        if unattended_print_mode:
                            print "{0} UNEXPECTED_EXCEPTION".format(unattended_mode_name)
                            self.healthcheck_dict[unattended_mode_name] = "UNEXPECTED_EXCEPTION"
                    else:
                        print _Colors.FAIL + "[UNEXPECTED_EXCEPTION] " + _Colors.ENDC + "%s" % (str(message))
                else:
                    if unattended_print_mode:
                        self.healthcheck_dict[unattended_mode_name] = "UNEXPECTED_EXCEPTION"

            target.close()

        except Exception, e:
            print "An unexpected exception occured during logging in '{0}': \n{1}".format(self.HEALTHCHECK_DIR, e)