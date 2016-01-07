"""
Copyright 2015 Christian Fobel

This file is part of dmf_device_ui_plugin.

dmf_device_ui_plugin is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

dmf_control_board is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with dmf_device_ui_plugin.  If not, see <http://www.gnu.org/licenses/>.
"""
import json
import logging
import sys
from subprocess import Popen

from flatland import Integer, Form
from path_helpers import path
from microdrop.plugin_helpers import AppDataController, get_plugin_info
from microdrop.plugin_manager import (PluginGlobals, Plugin, IPlugin,
                                      implements, get_service_instance_by_name,
                                      ScheduleRequest)
from microdrop.app_context import get_hub_uri
import gobject
import gtk

logger = logging.getLogger(__name__)


def hub_execute(*args, **kwargs):
    service = get_service_instance_by_name('wheelerlab.device_info_plugin',
                                            env='microdrop')
    return service.plugin.execute(*args, **kwargs)


def gtk_wait(wait_duration_s): gtk.main_iteration_do()

PluginGlobals.push_env('microdrop.managed')


class DmfDeviceUiPlugin(AppDataController, Plugin):
    """
    This class is automatically registered with the PluginManager.
    """
    implements(IPlugin)
    version = get_plugin_info(path(__file__).parent).version
    plugin_name = get_plugin_info(path(__file__).parent).plugin_name

    AppFields = Form.of(
        Integer.named('x').using(default=None, optional=True,
                                 properties={'show_in_gui': False}),
        Integer.named('y').using(default=None, optional=True,
                                 properties={'show_in_gui': False}),
        Integer.named('width').using(default=400, optional=True,
                                     properties={'show_in_gui': False}),
        Integer.named('height').using(default=500, optional=True,
                                      properties={'show_in_gui': False}))

    def __init__(self):
        self.name = self.plugin_name
        self.gui_process = None
        self.gui_heartbeat_id = None
        self._gui_enabled = False

    def on_plugin_enable(self):
        super(DmfDeviceUiPlugin, self).on_plugin_enable()
        self.reset_gui()

    def reset_gui(self):
        py_exe = sys.executable
        # Set allocation based on saved app values (i.e., remember window size
        # and position from last run).
        allocation = self.get_app_values()
        allocation_args = ['-a', json.dumps(allocation)]
        self.gui_process = Popen([py_exe, '-m',
                                  'dmf_device_ui.bin.device_view', '-n',
                                  self.name] + allocation_args +
                                 ['fixed', get_hub_uri()])
        self.gui_process.daemon = False
        self._gui_enabled = True

        def keep_alive():
            if not self._gui_enabled:
                return False
            elif self.gui_process.poll() == 0:
                # GUI process has exited.  Restart.
                self.cleanup()
                self.reset_gui()
                return False
            else:
                # Keep checking.
                return True
        self.gui_heartbeat_id = gobject.timeout_add(1000, keep_alive)

    def on_plugin_disable(self):
        super(DmfDeviceUiPlugin, self).on_plugin_disable()
        self._gui_enabled = False
        self.cleanup()

    def on_app_exit(self):
        if self.gui_process is not None:
            # Try to request allocation to save in app options.
            try:
                allocation = hub_execute(self.name, 'get_allocation',
                                         wait_func=gtk_wait, timeout_s=2)
            except IOError:
                logger.warning('Timed out waiting for device window size and '
                               'position request.')
            else:
                if allocation:
                    # Save window allocation settings (i.e., width, height, x,
                    # y) as app values.
                    app_values = self.get_app_values()
                    app_values.update(allocation)
                    self.set_app_values(app_values)

        self._gui_enabled = False
        self.cleanup()

    def cleanup(self):
        if self.gui_heartbeat_id is not None:
            gobject.source_remove(self.gui_heartbeat_id)
        if self.gui_process is not None:
            self.gui_process.terminate()

    def get_schedule_requests(self, function_name):
        """
        Returns a list of scheduling requests (i.e., ScheduleRequest
        instances) for the function specified by function_name.
        """
        if function_name == 'on_plugin_enable':
            return [ScheduleRequest('wheelerlab.droplet_planning_plugin',
                                    self.name)]
        return []


PluginGlobals.pop_env()
