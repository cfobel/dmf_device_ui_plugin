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
import sys, traceback
from datetime import datetime

from path_helpers import path
from flatland import Integer, Boolean, Form, String
from flatland.validation import ValueAtLeast, ValueAtMost
from microdrop.logger import logger
from microdrop.plugin_helpers import (AppDataController, StepOptionsController,
                                      get_plugin_info)
from microdrop.plugin_manager import (PluginGlobals, Plugin, IPlugin,
                                      implements, emit_signal)
from microdrop.app_context import get_app
import gobject

PluginGlobals.push_env('microdrop.managed')

class DmfDeviceUiPlugin(Plugin, AppDataController, StepOptionsController):
    """
    This class is automatically registered with the PluginManager.
    """
    implements(IPlugin)
    version = get_plugin_info(path(__file__).parent).version
    plugin_name = get_plugin_info(path(__file__).parent).plugin_name

    '''
    AppFields
    ---------

    A flatland Form specifying application options for the current plugin.
    Note that nested Form objects are not supported.

    Since we subclassed AppDataController, an API is available to access and
    modify these attributes.  This API also provides some nice features
    automatically:
        -all fields listed here will be included in the app options dialog
            (unless properties=dict(show_in_gui=False) is used)
        -the values of these fields will be stored persistently in the microdrop
            config file, in a section named after this plugin's name attribute
    '''
    AppFields = Form.of(
        Integer.named('duration_ms').using(optional=True, default=750),
        #Boolean.named('bool_field').using(optional=True, default=False),
        #String.named('string_field').using(optional=True, default=''),
    )

    '''
    StepFields
    ---------

    A flatland Form specifying the per step options for the current plugin.
    Note that nested Form objects are not supported.

    Since we subclassed StepOptionsController, an API is available to access and
    modify these attributes.  This API also provides some nice features
    automatically:
        -all fields listed here will be included in the protocol grid view
            (unless properties=dict(show_in_gui=False) is used)
        -the values of these fields will be stored persistently for each step
    '''
    StepFields = Form.of(
        #Integer.named('int_field').using(optional=True, default=750,
                                          #validators=
                                          #[ValueAtLeast(minimum=0),
                                          # ValueAtMost(maximum=100000)]),
        #Boolean.named('bool_field').using(optional=True, default=False),
        #String.named('string_field').using(optional=True, default=''),
    )

    def __init__(self):
        self.name = self.plugin_name
        self.timeout_id = None
        self.start_time = None

    def on_step_run(self):
        """
        Handler called whenever a step is executed. Note that this signal
        is only emitted in realtime mode or if a protocol is running.

        Plugins that handle this signal must emit the on_step_complete
        signal once they have completed the step. The protocol controller
        will wait until all plugins have completed the current step before
        proceeding.

        return_value can be one of:
            None
            'Repeat' - repeat the step
            or 'Fail' - unrecoverable error (stop the protocol)
        """
        app = get_app()
        logger.info('[DmfDeviceUiPlugin] on_step_run(): step #%d',
                    app.protocol.current_step_number)
        app_values = self.get_app_values()
        try:
            if self.timeout_id is not None:
                # Timer was already set, so cancel previous timer.
                gobject.source_remove(self.timeout_id)

            self.start_time = datetime.now()
            gobject.idle_add(self.on_timer_tick, False)
            self.timeout_id = gobject.timeout_add(app_values['duration_ms'],
                                                  self.on_timer_tick)
        except:
            print "Exception in user code:"
            print '-'*60
            traceback.print_exc(file=sys.stdout)
            print '-'*60
            # An error occurred while initializing Analyst remote control.
            emit_signal('on_step_complete', [self.name, 'Fail'])

    def on_timer_tick(self, continue_=True):
        '''
        Args:
            continue_ (bool) : If `False`, timer does not trigger again.
        Returns:
            (bool) : If `True`, timer triggers again.  If `False`, timer stops.
        '''
        try:
            emit_signal('on_step_complete', [self.name, None])
            self.timeout_id = None
            self.start_time = None
            return False
        except:
            print "Exception in user code:"
            print '-'*60
            traceback.print_exc(file=sys.stdout)
            print '-'*60
            emit_signal('on_step_complete', [self.name, 'Fail'])
            self.timeout_id = None
            self.remote = None
            return False
        return continue_

    def on_step_options_swapped(self, plugin, old_step_number, step_number):
        """
        Handler called when the step options are changed for a particular
        plugin.  This will, for example, allow for GUI elements to be
        updated based on step specified.

        Parameters:
            plugin : plugin instance for which the step options changed
            step_number : step number that the options changed for
        """
        pass

    def on_step_swapped(self, old_step_number, step_number):
        """
        Handler called when the current step is swapped.
        """


PluginGlobals.pop_env()
