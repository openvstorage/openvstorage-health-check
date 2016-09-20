#!/bin/bash

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

cd /opt/OpenvStorage
if [ "$1" = "unattended" ] ; then
    # launch unattended healthcheck
    python -c "from ovs.lib.healthcheck import HealthCheckController; HealthCheckController().check_unattended()"
elif [ "$1" = "silent" ] ; then
    # launch silent healthcheck
    python -c "from ovs.lib.healthcheck import HealthCheckController; HealthCheckController().check_silent()"
else
    # launch healthcheck
    python -c "from ovs.lib.healthcheck import HealthCheckController; HealthCheckController().check_attended()"
fi
