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
import sys
from subprocess import Popen

from path_helpers import path
from microdrop.plugin_helpers import get_plugin_info
from microdrop.plugin_manager import (PluginGlobals, Plugin, IPlugin,
                                      implements)
from microdrop.app_context import get_hub_uri
import gobject


PluginGlobals.push_env('microdrop.managed')

class DmfDeviceUiPlugin(Plugin):
    """
    This class is automatically registered with the PluginManager.
    """
    implements(IPlugin)
    version = get_plugin_info(path(__file__).parent).version
    plugin_name = get_plugin_info(path(__file__).parent).plugin_name

    def __init__(self):
        self.name = self.plugin_name
        self.gui_process = None
        self.gui_heartbeat_id = None
        self._gui_enabled = False

    def on_plugin_enable(self):
        self.reset_gui()

    def reset_gui(self):
        py_exe = sys.executable
        self.gui_process = Popen([py_exe, '-m',
                                  'dmf_device_ui.bin.device_view', '-n',
                                  self.name, 'fixed', get_hub_uri()])
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
        self.gui_heartbeat_id = gobject.timeout_add(200, keep_alive)

    def on_plugin_disable(self):
        self._gui_enabled = False
        self.cleanup()

    def on_app_exit(self):
        self._gui_enabled = False
        self.cleanup()

    def cleanup(self):
        if self.gui_heartbeat_id is not None:
            gobject.source_remove(self.gui_heartbeat_id)
        if self.gui_process is not None:
            self.gui_process.terminate()

PluginGlobals.pop_env()
