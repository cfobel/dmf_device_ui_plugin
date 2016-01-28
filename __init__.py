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
from datetime import datetime
from subprocess import Popen, CREATE_NEW_PROCESS_GROUP
import io
import json
import logging
import sys
import time

from flatland import Integer, Form, String
from microdrop.plugin_helpers import (AppDataController, get_plugin_info,
                                      hub_execute, hub_execute_async)
from microdrop.plugin_manager import (PluginGlobals, Plugin, IPlugin,
                                      implements, ScheduleRequest)
from microdrop.app_context import get_app, get_hub_uri
from path_helpers import path
from pygtkhelpers.utils import refresh_gui
from si_prefix import si_format
import gobject
import pandas as pd

logger = logging.getLogger(__name__)


PluginGlobals.push_env('microdrop.managed')


class DmfDeviceUiPlugin(AppDataController, Plugin):
    """
    This class is automatically registered with the PluginManager.
    """
    implements(IPlugin)
    version = get_plugin_info(path(__file__).parent).version
    plugin_name = get_plugin_info(path(__file__).parent).plugin_name

    AppFields = Form.of(
        String.named('video_config').using(default='', optional=True,
                                           properties={'show_in_gui': False}),
        String.named('canvas_corners').using(default='', optional=True,
                                             properties={'show_in_gui':
                                                         False}),
        String.named('frame_corners').using(default='', optional=True,
                                            properties={'show_in_gui': False}),
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
        self.alive_timestamp = None

    def on_plugin_enable(self):
        super(DmfDeviceUiPlugin, self).on_plugin_enable()
        self.reset_gui()

    def reset_gui(self):
        py_exe = sys.executable
        # Set allocation based on saved app values (i.e., remember window size
        # and position from last run).
        app_values = self.get_app_values()
        allocation_args = ['-a', json.dumps(app_values)]

        app = get_app()
        if app.config.data.get('advanced_ui', False):
            debug_args = ['-d']
        else:
            debug_args = []

        self.gui_process = Popen([py_exe, '-m',
                                  'dmf_device_ui.bin.device_view', '-n',
                                  self.name] + allocation_args + debug_args +
                                 ['fixed', get_hub_uri()],
                                 creationflags=CREATE_NEW_PROCESS_GROUP)
        self.gui_process.daemon = False
        self._gui_enabled = True

        def keep_alive():
            if not self._gui_enabled:
                self.alive_timestamp = None
                return False
            elif self.gui_process.poll() == 0:
                # GUI process has exited.  Restart.
                self.cleanup()
                self.reset_gui()
                return False
            else:
                self.alive_timestamp = datetime.now()
                # Keep checking.
                return True
        # Go back to Undo 613 for working corners
        self.wait_for_gui_process()
        self.set_default_corners()
        self.set_video_config()
        self.gui_heartbeat_id = gobject.timeout_add(1000, keep_alive)

    def on_plugin_disable(self):
        self._gui_enabled = False
        self.cleanup()

    def on_app_exit(self):
        if self.gui_process is not None:
            app_values = self.get_app_values()
            original_values = app_values.copy()

            # Try to request video configuration.
            try:
                video_config = hub_execute(self.name, 'get_video_config',
                                           wait_func=lambda *args:
                                           refresh_gui(), timeout_s=2)
            except IOError:
                logger.warning('Timed out waiting for device window size and '
                               'position request.')
            else:
                if video_config is not None:
                    app_values['video_config'] = video_config.to_json()
                else:
                    app_values['video_config'] = ''

            # Try to request allocation to save in app options.
            try:
                data = hub_execute(self.name, 'get_corners', wait_func=lambda
                                   *args: refresh_gui(), timeout_s=2)
            except IOError:
                logger.warning('Timed out waiting for device window size and '
                               'position request.')
            else:
                if data:
                    # Save window allocation settings (i.e., width, height, x,
                    # y) as app values.
                    # Replace `df_..._corners` with CSV string with name
                    # `..._corners` (no `df_` prefix).
                    for k in ('df_canvas_corners', 'df_frame_corners'):
                        if k in data:
                            data['allocation'][k[3:]] = data.pop(k).to_csv()
                    app_values.update(data['allocation'])

            if app_values != original_values:
                self.set_app_values(app_values)

        self._gui_enabled = False
        self.cleanup()

    def cleanup(self):
        if self.gui_heartbeat_id is not None:
            gobject.source_remove(self.gui_heartbeat_id)
        if self.gui_process is not None:
            hub_execute_async(self.name, 'terminate')
        self.alive_timestamp = None

    def get_schedule_requests(self, function_name):
        """
        Returns a list of scheduling requests (i.e., ScheduleRequest
        instances) for the function specified by function_name.
        """
        if function_name == 'on_plugin_enable':
            return [ScheduleRequest('wheelerlab.droplet_planning_plugin',
                                    self.name)]
        return []

    def set_default_corners(self):
        if self.alive_timestamp is None or self.gui_process is None:
            # Repeat until GUI process has started.
            raise IOError('GUI process not ready.')

        app_values = self.get_app_values()
        canvas_corners = app_values.get('canvas_corners', None)
        frame_corners = app_values.get('frame_corners', None)
        logger.info('[_set_default_corners] canvas_corners=%s', canvas_corners)
        logger.info('[_set_default_corners] frame_corners=%s', frame_corners)

        if not canvas_corners or not frame_corners:
            return

        df_canvas_corners = pd.read_csv(io.BytesIO(bytes(canvas_corners)),
                                        index_col=0)
        df_frame_corners = pd.read_csv(io.BytesIO(bytes(frame_corners)),
                                        index_col=0)

        hub_execute(self.name, 'set_default_corners',
                    canvas=df_canvas_corners, frame=df_frame_corners,
                    wait_func=lambda *args: refresh_gui(), timeout_s=5)

    def set_video_config(self):
        if self.alive_timestamp is None or self.gui_process is None:
            # Repeat until GUI process has started.
            raise IOError('GUI process not ready.')

        app_values = self.get_app_values()
        video_config_json = app_values.get('video_config')

        if not video_config_json:
            video_config = pd.Series(None)
        else:
            video_config = pd.Series(json.loads(video_config_json))

        hub_execute(self.name, 'set_video_config', video_config=video_config,
                    wait_func=lambda *args: refresh_gui(), timeout_s=5)

    def wait_for_gui_process(self, retry_count=10, retry_duration_s=1):
        start = datetime.now()
        for i in xrange(retry_count):
            try:
                hub_execute(self.name, 'ping', wait_func=lambda *args:
                            refresh_gui(), timeout_s=5, silent=True)
            except:
                logger.debug('[wait_for_gui_process] failed (%d of %d)', i + 1,
                             retry_count, exc_info=True)
            else:
                logger.info('[wait_for_gui_process] success (%d of %d)', i + 1,
                            retry_count)
                self.alive_timestamp = datetime.now()
                return
            for j in xrange(10):
                time.sleep(retry_duration_s / 10.)
                refresh_gui()
        raise IOError('Timed out after %ss waiting for GUI process to connect '
                      'to hub.' % si_format((datetime.now() -
                                             start).total_seconds()))


PluginGlobals.pop_env()
