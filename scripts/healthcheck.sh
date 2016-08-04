#!/bin/bash
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
