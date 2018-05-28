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
Rpm Package module
"""

import time
import collections
from distutils.version import LooseVersion
from subprocess import check_output, CalledProcessError
from ovs.extensions.healthcheck.logger import Logger


class RpmPackage(object):
    """
    Contains all logic related to RPM packages (used in e.g. CentOS)
    """
    _logger = Logger('extensions')

    def __init__(self, package_info):
        self.package_info = package_info

    @staticmethod
    def get_release_name(client=None):
        """
        Get the release name based on the name of the repository
        :param client: Client on which to check the release name
        :type client: ovs_extensions.generic.sshclient.SSHClient
        :return: Release name
        :rtype: str
        """
        command = "cat /etc/yum.repos.d/ovs.repo | grep url | awk -F/ '{print $NF}'"
        if client is None:
            output = check_output(command, shell=True).strip()
        else:
            output = client.run(command, allow_insecure=True).strip()
        return output.replace('-', ' ').title()

    def get_installed_versions(self, client=None, package_names=None):
        """
        Retrieve currently installed versions of all packages
        :param client: Client on which to check the installed versions
        :type client: SSHClient
        :param package_names: Name of the packages to check
        :type package_names: list
        :return: Package installed versions
        :rtype: dict
        """
        versions = collections.OrderedDict()
        if package_names is None:
            package_names = set()
            for names in self.package_info['names'].itervalues():
                package_names = package_names.union(names)
        for package_name in sorted(package_names):
            command = "yum info '{0}' | grep Version | cut -d ':' -f 2 || true".format(package_name.replace(r"'", r"'\''"))
            if client is None:
                version_info = check_output(command, shell=True).strip()
            else:
                version_info = client.run(command, allow_insecure=True).strip()
            if version_info and 'No matching Packages to list' not in version_info:
                versions[package_name] = LooseVersion(version_info)
        return versions

    @classmethod
    def get_candidate_versions(cls, client, package_names):
        """
        Retrieve the versions candidate for installation of all packages
        :param client: Root client on which to check the candidate versions
        :type client: SSHClient
        :param package_names: Name of the packages to check
        :type package_names: list
        :return: Package candidate versions
        :rtype: dict
        """
        RpmPackage.update(client=client)
        versions = collections.OrderedDict()
        for package_name in sorted(package_names):
            installed = None
            candidate = None
            versions[package_name] = ''
            try:
                for line in client.run(['yum', 'list', package_name]).splitlines():
                    if line.startswith(package_name):
                        version = line.split()
                        if len(version) > 1:
                            if installed is None:
                                candidate = version[1]
                            else:
                                candidate = version[1]
                versions[package_name] = LooseVersion(candidate) if candidate else ''
            except CalledProcessError:
                pass
        return versions

    def get_binary_versions(self, client, package_names=None):
        """
        Retrieve the versions for the binaries related to the package_names
        :param client: Root client on which to retrieve the binary versions
        :type client: ovs_extensions.generic.sshclient.SSHClient
        :param package_names: Names of the packages
        :type package_names: list
        :return: Binary versions
        :rtype: dict
        """
        if package_names is None:
            package_names = set()
            for names in self.package_info['binaries'].itervalues():
                package_names = package_names.union(names)

        versions = collections.OrderedDict()
        version_commands = self.package_info['version_commands']
        for package_name in sorted(package_names):
            if package_name not in version_commands:
                raise ValueError('Only the following packages in the OpenvStorage repository have a binary file: "{0}"'.format('", "'.join(sorted(version_commands.keys()))))
            versions[package_name] = LooseVersion(client.run(version_commands[package_name], allow_insecure=True))
        return versions

    @staticmethod
    def install(package_name, client):
        """
        Install the specified package
        :param package_name: Name of the package to install
        :type package_name: str
        :param client: Root client on which to execute the installation of the package
        :type client: SSHClient
        :return: None
        """
        if client.username != 'root':
            raise RuntimeError('Only the "root" user can install packages')

        counter = 0
        max_counter = 3
        while counter < max_counter:
            try:
                client.run(['yum', 'update', '-y', package_name])
                break
            except CalledProcessError as cpe:
                # Retry 3 times if fail
                if counter == max_counter:
                    RpmPackage._logger.error('Install {0} failed. Error: {1}'.format(package_name, cpe.output))
                    raise cpe
            except Exception as ex:
                raise ex
            counter += 1
            time.sleep(1)

    @staticmethod
    def update(client):
        """
        Run the 'yum check-update' command on the specified node to update the package information
        :param client: Root client on which to update the package information
        :type client: SSHClient
        :return: None
        """
        if client.username != 'root':
            raise RuntimeError('Only the "root" user can update packages')
        try:
            client.run(['yum', 'check-update'])
        except CalledProcessError as cpe:
            # Returns exit value of 100 if there are packages available for an update
            if cpe.returncode != 100:
                RpmPackage._logger.error('Update failed. Error: {0}'.format(cpe.output))
                raise cpe
