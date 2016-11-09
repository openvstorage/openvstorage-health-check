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
            info = CacheHelper._to_json(info)
        CacheHelper.client.set(CacheHelper.prefix, info)

    @staticmethod
    def get(key=prefix):
        try:
            return CacheHelper._from_json(CacheHelper.client.get(key))
        except KeyNotFoundException:
            return None

    @staticmethod
    def _to_json(value):
        """
        Converts a dict/json to a json
        :param value: dict or json with data
        :type value: dict/string
        :return: json data
        :rtype: string
        """
        try:
            json_object = json.loads(str(value))
        except ValueError:
            return json.dumps(value)
        except TypeError:
            return value
        return json_object

    @staticmethod
    def _from_json(value):
        """
        Converts a json to dict
        If it fails: returns the string
        :param value: string type
        :type value
        :return:
        """
        try:
            loaded = json.loads(value)
        except (ValueError, TypeError) as e:
            return value
        return loaded

