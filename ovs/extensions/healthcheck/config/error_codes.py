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
from operator import itemgetter


class ErrorCode(object):
    """
    Error code class. Every error code is defined by a unique code and provides information and a solution to a problem
    """
    def __init__(self, error_code, information, solution):
        self.error_code = error_code
        self.information = information
        self.solution = solution


class ErrorCodesType(type):
    """
    Class which customizes the properties for a certain other class
    This class is meant to be a metaclass
    """
    def __getattr__(self, item):
        return self._internal_codes[item]

    def __dir__(self):
        res = dir(type(self)) + list(self.__dict__.keys())
        res.extend(self._internal_codes.keys())
        return res


class ErrorCodes(object):
    """
    Container for all error codes
    """
    __metaclass__ = ErrorCodesType

    engineer_report = 'Report this to the engineers of OpenvStorage'
    no_action = 'No action required'
    _internal_codes = {
        ###########
        # Generic #
        ###########
        'ssh_connection_time': ErrorCode('GEN000', 'The SSH connection could not be established within a reasonable time frame', 'Validate whether this node can accept SSH connections'),
        'ssh_connection_fail': ErrorCode('GEN001', 'The SSH connection could not established', 'Validate whether this node can accept SSH connections'),
        'ssh_connection_authentication': ErrorCode('GEN002', 'The SSH connection could not established due to authentication issues', 'Validate whether this node has access to all nodes within the cluster'),

        # Healthcheck #
        ###############
        'default': ErrorCode('HC0000', 'Default code', 'Default code'),  # Used in the start of these error codes. Means no code is in place
        'unhandled_exception': ErrorCode('HC0001', 'An unhandled exception was caught', engineer_report),
        ########
        # ALBA #
        ########
        # General
        'alba_cmd_fail': ErrorCode('ALBA0001', 'A command towards ALBA failed', 'Validate whether the Arakoon cluster is running'),
        # OSD
        'osd_no_ip': ErrorCode('ALBA0100', 'An OSD has no associated IPs', 'Validate whether the asd-manager registered the correct IPs'),
        'osd_broken': ErrorCode('ALBA0101', 'An OSD seems to be broken', 'Validate whether the OSD is running correctly'),
        'osd_object_download_fail': ErrorCode('ALBA0102', 'An OSD did not return the correct object', 'Validate whether the OSD is running correctly'),
        # Proxy
        'proxy_namespace_create': ErrorCode('ALBA0200', 'The namespace was successfully created through the proxy', no_action),
        'proxy_namespace_fetch': ErrorCode('ALBA0201', 'The namespace was successfully fetched through the proxy', no_action),
        'proxy_upload_obj': ErrorCode('ALBA0202', 'The object was successfully uploaded through the proxy', no_action),
        'proxy_download_obj': ErrorCode('ALBA0203', 'The object was successfully downloaded through the proxy', no_action),
        'proxy_verify_obj': ErrorCode('ALBA0204', 'The object\'s contents did not change', no_action),
        'proxy_verify_obj_fail': ErrorCode('ALBA0205', 'The object\'s contents changed', engineer_report),
        'proxy_problems': ErrorCode('ALBA0206', 'Testing the proxies was unsuccessful', 'Look for previous errors and act accordingly'),
        #############
        # Framework #
        #############
        # General
        'log_file_size': ErrorCode('FWK0001', 'Log file size is bigger than the given maximum size', 'Change log level to log relevant items and enable log rotation'),
        'package_required': ErrorCode('FWK0002', 'A required package is missing', 'Install this required package'),
        'directory_ownership_incorrect': ErrorCode('FWK0003', 'The directory\'s owner is not as expected', 'Change the ownership to the correct user'),
        'directory_rights_incorrect': ErrorCode('FWK0004', 'The directory\'s rights are not as expected', 'Change the rights to the suggested ones'),
        'dns_resolve_fail': ErrorCode('FWK0005', 'The StorageRouter is unable to resolve a hostname', 'Validate the DNS settings and connection to the internet'),
        'missing_ovsdb': ErrorCode('FWK0006', 'There are volumes that are registered in the Volumedriver and not in the Framework', 'Validate if Celery is still working and sync the vdisks to reality'),
        'missing_volumedriver': ErrorCode('FWK0007', 'There are Volumes registered in the Framework that are gone in reality', 'Validate if Celery is still working and sync the vdisks to reality'),
        # Ports
        'port_memcached': ErrorCode('FWK0100', 'Unable to connect to Memcached server', 'Validate whether Memcached is still up and running'),
        'port_nginx': ErrorCode('FWK0101', 'Unable to connect to Nginx server', 'Validate whether Nginx is still up and running'),
        'port_celery': ErrorCode('FWK0102', 'Unable to connect to Celery', 'Validate whether Celery is still up and running'),
        # Processes
        'process_fwk': ErrorCode('FWK0200', 'An OpenvStorage service is not running', 'Make sure this service is running'),
        'process_fwk_not_found': ErrorCode('FWK0201', 'No OpenvStorage service is running on this node', 'Validate whether this node should be running services'),
        'process_celery_timeout': ErrorCode('FWK0202', 'Celery is not responding', 'Verify whether Celery is up and running and configured properly'),
        'process_zombie_found': ErrorCode('FWK0203', 'Celery is not responding', 'Verify whether Celery is up and running and configured properly'),
        'process_dead_found': ErrorCode('FWK0204', 'Celery is not responding', 'Verify whether Celery is up and running and configured properly'),
        'process_rabbit_mq': ErrorCode('FWK0205', 'RabbitMQ is experiencing partition problems', 'Verify whether RabbitMQ is up and running and configured properly'),
        # DAL
        'std_no_str': ErrorCode('FWK0300', 'The StorageDriver has no StorageRouter associated to it', engineer_report),
        # Configuration
        'configuration_not_found': ErrorCode('FWK0400', 'An entry was not found within the Configuration management', engineer_report),
        ###########
        # Arakoon #
        ###########
        'master_none': ErrorCode('ARA000', 'The Arakoon cluster could not determine a master', 'Validate if the Arakoon cluster still has a majority'),
        'node_missing': ErrorCode('ARA001', 'The Arakoon cluster is missing a node', 'Validate whether the Arakoon process is running on the node'),
        # Transactions
        'node_up_to_date': ErrorCode('ARA0100', 'The Arakoon node is currently up to date with the master', 'No actions required'),
        'master_behind': ErrorCode('ARA0101', 'The Arakoon slave is a couple of transactions behind the master', 'Wait for the catchup to complete'),
        'slave_catch_up': ErrorCode('ARA0102', 'The Arakoon slave is catching up to the master', 'Wait for the catchup to complete'),
        # Connections
        'arakoon_connection_ok': ErrorCode('ARA0200', 'Connection can be established to the Arakoon node', 'No actions required'),
        'arakoon_connection_failure': ErrorCode('ARA0201', 'Connection could not be established to the Arakoon node', 'Validate whether the Arakoon process is running on the node'),
        'arakoon_responded': ErrorCode('ARA0202', 'The Arakoon cluster responded', 'No actions required'),
        # Tlog and TLX
        'tlx_tlog_not_found': ErrorCode('ARA0300', 'Neither the TLX nor TLOG could be found on a node within the Arakoon cluster', 'Validate whether this Arakoon cluster has been setup correctly'),
        'tlog_not_found': ErrorCode('ARA0301', 'No open TLOG could be found on a node within the Arakoon cluster', 'Validate whether this Arakoon cluster has been setup correctly'),
        'collapse_ok': ErrorCode('ARA0302', 'The Arakoon cluster does not require collapsing yet', 'No actions required'),
        'collapse_not_ok': ErrorCode('ARA0303', 'The Arakoon cluster requires collapsing', 'Collapse the Arakoon cluster'),
        # File descriptors
        'arakoon_fd_ok': ErrorCode('ARA0401', 'Normal amount of TCP connection towards the Arakoon cluster', no_action),
        'arakoon_fd_95': ErrorCode('ARA0400', 'High amount of TCP connection towards the Arakoon cluster', no_action),
        'arakoon_fd_80': ErrorCode('ARA0401', 'High amount of TCP connection towards the Arakoon cluster', no_action),
        ################
        # Volumedriver #
        ################
        # vPools
        'vpools_none': ErrorCode('VOL0000', 'No vPools present', 'Add vPools to this node'),
        'vpool_not_local': ErrorCode('VOL0001', 'vPool not on this node', 'Extend vPool to this node'),
        # Volume states
        'volume_not_found': ErrorCode('VOL0100', 'Volumedriver does not recognize this volume', 'Verify whether this volume is still present'),
        'volume_max_redir': ErrorCode('VOL0101', 'Volumedriver can\'t retrieve information about the volume. This indicates the volume might be down', 'Verify whether this volume is running'),
        'volume_halted': ErrorCode('VOL0102', 'Volume is in the \'halted\' state. The volume could still be failing over to another node', 'A possible solution is restarting this volume (after the failover is done)'),
        # Volume DTL
        'volume_dtl_unknown': ErrorCode('VOL0200', 'The volume\'s DTL state which is not recognized', engineer_report),
        'volume_dtl_catch_up': ErrorCode('VOL0201', 'The volume\'s DTL state is still syncing', 'Wait for the sync to finish'),
        'volume_dtl_checkup_required': ErrorCode('VOL0202', 'The volume\'s DTL should be configured', 'Configure the DTL for this volume'),
        'volume_dtl_degraded': ErrorCode('VOL0203', 'The volume\'s DTL is degraded', 'Perform the DTL checkup for this volume'),
        'volume_dtl_ok': ErrorCode('VOL0204', 'The volume\'s DTL is fine', 'No action required for this volume'),
        'volume_dtl_standalone': ErrorCode('VOL0205', 'The volume\'s DTL is disabled', 'No action required for this volume'),
        # General
        'voldrv_connection_problem': ErrorCode('VOL0300', 'Volumedriver is not responding to calls (fast enough)', 'Verify whether this Volumedriver is running'),
        }

    @classmethod
    def print_md(cls):
        """
        Prints generated documentation about all codes in md table format
        :return: None
        :rtype: NoneType
        """
        headings = ['Error code', 'Information', 'Solution']
        row_data = []

        for error_code in cls._internal_codes.values():
            row_data.append([error_code.error_code, error_code.information, error_code.solution])
        row_data.sort(key=itemgetter(0))
        print MarkDownGenerator.generate_table(headings, row_data)


class MarkDownGenerator(object):
    """
    Class which generates a table in markdown format
    """
    @staticmethod
    def generate_table(headings, rows_data):
        """
        Generate an md table based on the provided data
        :param headings: List of column headings
        :type headings: list[str]
        :param rows_data: List with iterables which contain the data
        A requirement for aligning everything nicely is that iterable is sorted
        The inner list entries will be matched with the columns
        Example: columns: ['test', 'test'1], records: [['my_test_value', 'my_test1_value']]
        :type rows_data: list[iterable(any)]
        """
        # Compute the table cell data
        rows = [headings] + rows_data
        columns = [list(x) for x in zip(*rows)]  # Transpose our rows
        columns_widths = [len(max(column, key=len)) for column in columns]
        heading_separator = [':{0}'.format('-' * (width - 1)) for width in columns_widths]
        rows.insert(1, heading_separator)
        columns = [list(x) for x in zip(*rows)]  # Transpose our rows again
        # Center it all for an even table
        even_columns = []
        for index, column in enumerate(columns):
            even_column = []
            for cell in column:
                even_column.append(str(cell).center(columns_widths[index]))
            even_columns.append(even_column)
        rows = [list(x) for x in zip(*even_columns)]  # Transpose our columns
        md_table = ''
        for row in rows:
            md_table += ' | ' + ' | '.join(row) + ' | \n'
        return md_table
