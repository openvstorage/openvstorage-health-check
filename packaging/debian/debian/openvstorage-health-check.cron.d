# /etc/cron.d/openvstorage-health-check: crontab entries for the openvstorage-health-check package

0 *   * * *  root  /usr/bin/ovs healthcheck silent
