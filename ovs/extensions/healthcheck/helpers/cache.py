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
import json
from ovs.extensions.storage.exceptions import KeyNotFoundException
from ovs.extensions.storage.persistentfactory import PersistentFactory


class CacheHelper(object):

    client = PersistentFactory.get_client()
    prefix = 'ovs-health-check'

    @staticmethod
    def set(info):
        """
        Store the information to the config management
        :param info:
        :return:
        """

        if isinstance(info, type(dict)):
            info = CacheHelper._parse_data(info)
        CacheHelper.client.set(CacheHelper.prefix, info)

    @staticmethod
    def get(key=prefix):
        try:
            return CacheHelper._parse_data(CacheHelper.client.get(key))
        except KeyNotFoundException:
            return None

    @staticmethod
    def delete(key=prefix):
        try:
            CacheHelper.client.delete(key)
            return True
        except KeyNotFoundException:
            return False

    @staticmethod
    def _parse_data(data):
        """
        Could data so it can be stored in PersistentFactory

        :param data: any value
        :type data: object
        :return: parsed data - either the same type or dicts converted to json
        :rtype: object
        """
        try:
            parsed_data = json.loads(data)
        except ValueError:
            # Not a good formatted dict
            return json.dumps(data)
        except TypeError:
            # Not a dict
            return data
        return parsed_data

    @staticmethod
    def _test_type_handling():
        """
        Test if CacheHelper can cope with all primitive types
        :return:
        """
        testers = {
            'integer': 1,
            'double': 2.0,
            'string': "test",
            'literal': 'test',
            'dict': {"test": "test"},
            'list': [1,2],
            'set': set([1,2])
        }

        for key, value in testers.iteritems():
            try:
                CacheHelper.set(value)
            except Exception as e:
                print "Could not set {0} type. Got {1}".format(key, e.message)
            try:
                data = CacheHelper.get()
                print key
                print type(data)
            except Exception as e:
                print "Could not get {0} type. Got {1}".format(key, e.message)
        CacheHelper.delete()
