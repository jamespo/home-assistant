"""
Tracks devices by sending a ICMP echo request (ping) and query arp table.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/device_tracker.ping/
"""

import logging
import subprocess
import sys
import re
from datetime import timedelta

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.device_tracker import (
    PLATFORM_SCHEMA)
from homeassistant.components.device_tracker.const import (
    CONF_SCAN_INTERVAL, SCAN_INTERVAL, SOURCE_TYPE_ROUTER)
from homeassistant import util
from homeassistant import const

_LOGGER = logging.getLogger(__name__)

CONF_PING_COUNT = 'count'
CONF_IFACE = 'iface'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(const.CONF_HOSTS): {cv.string: cv.string},
    vol.Optional(CONF_PING_COUNT, default=1): cv.positive_int,
    vol.Optional(CONF_IFACE): cv.string,
})


class Host:
    """Host object with ping detection."""

    def __init__(self, ip_address, dev_id, hass, config):
        """Initialize the Host pinger."""
        self.hass = hass
        self.ip_address = ip_address
        self.dev_id = dev_id
        self._count = config[CONF_PING_COUNT]
        self._iface = config[CONF_IFACE]

        if self._iface:
            self._ping_cmd = ['ping', '-I', self._iface, '-n', '-q', '-c1', '-W1', self.ip_address]
            self._parp_cmd = ['arp', '-i', self._iface, '-n', self.ip_address]
        else:
            self._ping_cmd = ['ping', '-n', '-q', '-c1', '-W1', self.ip_address]
            self._parp_cmd = ['arp', '-n', self.ip_address]

    def ping(self):
        """Send an ICMP echo request and return True if success."""
        pinger = subprocess.Popen(self._ping_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            pinger.communicate()
            return pinger.returncode == 0
        except subprocess.CalledProcessError:
            return False


    def parp(self):
        """Get the MAC address for a given IP."""
        arp = subprocess.Popen(self._parp_cmd, stdout=subprocess.PIPE)
        out, _ = arp.communicate()
        match = re.search(r'(([0-9A-Fa-f]{1,2}\:){5}[0-9A-Fa-f]{1,2})', str(out))
        if match:
             return True
        return False

    def update(self, see):
        """Update device state by sending one or more ping messages."""
        failed = 0
        while failed < self._count:  # check more times if host is unreachable

            if self.ping():
                see(dev_id=self.dev_id, source_type=SOURCE_TYPE_ROUTER)
                _LOGGER.info("Ping OK from %s", self.ip_address)
                return True
            _LOGGER.info("No response from %s failed=%d", self.ip_address, failed)

            if self.parp():
                 see(dev_id=self.dev_id, source_type=SOURCE_TYPE_ROUTER)
                 _LOGGER.info("Arp OK from %s", self.ip_address)
                 return True
            _LOGGER.info("No MAC address found")
            failed += 1

def setup_scanner(hass, config, see, discovery_info=None):
    """Set up the Host objects and return the update function."""
    hosts = [Host(ip, dev_id, hass, config) for (dev_id, ip) in
             config[const.CONF_HOSTS].items()]

    interval = config.get(CONF_SCAN_INTERVAL, timedelta(seconds=len(hosts) * config[CONF_PING_COUNT]) + SCAN_INTERVAL)

    _LOGGER.info("Started ping tracker with interval=%s on hosts: %s", interval, ",".join([host.ip_address for host in hosts]))

    def update_interval(now):
        """Update all the hosts on every interval time."""
        try:
            for host in hosts:
                host.update(see)
        finally:
            hass.helpers.event.track_point_in_utc_time(
                update_interval, util.dt.utcnow() + interval)

    update_interval(None)
    return True
