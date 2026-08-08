# -*- coding: utf-8 -*-

"""
This file contains the Qudi interfuse between ODMR Logic and MW/Slow Counter HW.

Qudi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Qudi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Qudi. If not, see <http://www.gnu.org/licenses/>.

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
"""

import numpy as np

from core.connector import Connector
from logic.generic_logic import GenericLogic
from interface.odmr_counter_interface import ODMRCounterInterface
from interface.microwave_interface import MicrowaveInterface
from interface.microwave_interface import TriggerEdge

import time

class ODMRCounterMicrowaveInterfuse(GenericLogic, ODMRCounterInterface,
                                    MicrowaveInterface):
    """
    Interfuse to enable a software trigger of the microwave source but still
    having a hardware timed counter.

    This interfuse connects the ODMR logic with a slowcounter and a microwave
    device.
    """

    slowcounter = Connector(interface='SlowCounterInterface')
    microwave = Connector(interface='MicrowaveInterface')
    pulsedmasterlogic = Connector(interface='PulsedMasterLogic')
    poimanagerlogic = Connector(interface='PoiManagerLogic')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._pulse_out_channel = 'dummy'
        self._lock_in_active = False
        self._oversampling = 10
        self._odmr_length = 100


    def on_activate(self):
        """ Initialisation performed during activation of the module."""
        self._mw_device = self.microwave()
        self._sc_device = self.slowcounter()  # slow counter device
        self._pulsedmasterlogic = self.pulsedmasterlogic() # if 'ConnectedInterfaceProxy' object is not callable, why does this not throw error??
        self._poimanagerlogic = self.poimanagerlogic()
        pass

    def on_deactivate(self):
        pass

    ### ODMR counter interface commands

    def set_up_odmr_clock(self, clock_frequency=None, clock_channel=None):
        """ Configures the hardware clock of the NiDAQ card to give the timing.

        @param float clock_frequency: if defined, this sets the frequency of the
                                      clock
        @param str clock_channel: if defined, this is the physical channel of
                                  the clock

        @return int: error code (0:OK, -1:error)
        """
        print("clock freq", clock_frequency)  #JSS print
        return self._sc_device.set_up_clock(clock_frequency=clock_frequency,
                                                   clock_channel=clock_channel)

    def set_up_odmr(self, counter_channel=None, photon_source=None,
                    clock_channel=None, odmr_trigger_channel=None):
        """ Configures the actual counter with a given clock.

        @param str counter_channel: if defined, this is the physical channel of
                                    the counter
        @param str photon_source: if defined, this is the physical channel where
                                  the photons are to count from
        @param str clock_channel: if defined, this specifies the clock for the
                                  counter
        @param str odmr_trigger_channel: if defined, this specifies the trigger
                                         output for the microwave

        @return int: error code (0:OK, -1:error)
        """

        return self._sc_device.set_up_counter(counter_channels=counter_channel,
                                                sources=photon_source,
                                                clock_channel=clock_channel,
                                                counter_buffer=None)

    def set_odmr_length(self, length=100):
        """Set up the trigger sequence for the ODMR and the triggered microwave.

        @param int length: length of microwave sweep in pixel

        @return int: error code (0:OK, -1:error)
        """
        self._odmr_length = length
        return 0

    def count_odmr_1(self, length = 100): # software timed contrast measurement

        counts = np.zeros((len(self.get_odmr_channels()), length))
        counts_off = np.zeros((len(self.get_odmr_channels()), length))
        # self.trigger()
        for i in range(length):

            t1 = time.time()
            self.trigger()
            t2 = time.time()

            for j in range(2000): #added for contrast type measurement

                self._mw_device.set_power(0)  #added for contrast type measurement
                time.sleep(0.1)
                t3 = time.time()
                self.set_up_odmr()  # added for contrast type measurement ##
                data = self._sc_device.get_counter(samples=2)
                counts[:, i] += np.mean(data, axis=1)  # or sum, depending on your need #JOHN:CAREFUL!
                t4 = time.time()
                self.close_odmr() #added for contrast type measurement ##


                self._mw_device.set_power(-100)   #added for contrast type measurement
                time.sleep(0.1)
                self.set_up_odmr()  # added for contrast type measurement ##
                data2 = self._sc_device.get_counter(samples=2)   #added for contrast type measurement
                counts_off[:, i] += np.mean(data2, axis=1)   #added for contrast type measurement

                self.close_odmr() #added for contrast type measurement ##

            print(f"trigger: {(t2 - t1) * 1000:.1f} ms, read: {(t4 - t3) * 1000:.1f} ms, power switch: {(t3 - t2) * 1000:.1f} ms") #") #
            print("counted", counts_off, counts)#)#    #modified for contrast type measurement

        self.trigger()
        self.set_up_odmr()  # added for contrast type measurement ##
        return False, (counts - counts_off)/(counts + counts_off) + 1 #counts #     #modified for contrast type measurement

    def count_odmr_2(self, length=100): #pulsed cw-odmr, with nv optimization DURING THE SWEEP!

        odmr = np.zeros((1, length))
        odmr_err = np.zeros((1, length))
        # self.trigger()
        for i in range(length):

            t1 = time.time()
            self.trigger()
            t2 = time.time()

            ############################################################
            # If everything is properly set, we can start a measurement simply by calling:
            self._pulsedmasterlogic.toggle_pulsed_measurement(True)
            print("initial state:", self._pulsedmasterlogic.module_state(), ", init sweep:",
                  self._pulsedmasterlogic.elapsed_sweeps)

            # time.sleep(5)
            while self._pulsedmasterlogic.status_dict['measurement_running'] == 0: #module_state() == 'locked':#
            # print(pulsedmeasurementlogic.module_state())
                time.sleep(0.2)
            self._poimanagerlogic.start_periodic_refocus()
            while self._pulsedmasterlogic.elapsed_sweeps != 1:
                time.sleep(0.2)

            while self._pulsedmasterlogic.elapsed_sweeps < 1:
                time.sleep(0.2)
            print("2")

            # we can stop measurement simply by calling:
            self._pulsedmasterlogic.toggle_pulsed_measurement(False)
            # Wait until the pulsedmeasurementlogic is actually idle and the measurement is stopped
            while self._pulsedmasterlogic.status_dict['measurement_running'] == 1:  # module_state() == 'locked':#
                # print(pulsedmeasurementlogic.module_state())
                time.sleep(0.2)
            print("Final state:", self._pulsedmasterlogic.module_state(), ", final sweep:",
                  self._pulsedmasterlogic.elapsed_sweeps)
            self._poimanagerlogic.stop_periodic_refocus()
            ############################################################

            contrast = self._pulsedmasterlogic.signal_data[1]
            error = self._pulsedmasterlogic.measurement_error[1]
            odmr[:, i] = contrast[0]
            odmr_err[:, i] = error[0]

            print("odmr:", odmr, odmr_err)

        self.trigger()
        return False, odmr

    def count_odmr(self, length=100): # pulsed cw-odmr, with poi manager isolated

        odmr = np.zeros((1, length))
        odmr_err = np.zeros((1, length))
        # self.trigger()
        for i in range(length):

            t1 = time.time()
            self.trigger()
            t2 = time.time()

            self._pulsedmasterlogic.toggle_pulse_generator(True)
            self._poimanagerlogic.start_periodic_refocus()
            time.sleep(7.5)
            self._poimanagerlogic.stop_periodic_refocus()
            self._pulsedmasterlogic.toggle_pulse_generator(False)
            ############################################################
            # If everything is properly set, we can start a measurement simply by calling:
            self._pulsedmasterlogic.toggle_pulsed_measurement(True)
            print("initial state:", self._pulsedmasterlogic.module_state(), ", init sweep:", self._pulsedmasterlogic.elapsed_sweeps)

            # time.sleep(5)
            while self._pulsedmasterlogic.status_dict['measurement_running'] == 0: #module_state() == 'locked':#
            # print(pulsedmeasurementlogic.module_state())
                time.sleep(0.2)

            while self._pulsedmasterlogic.elapsed_sweeps != 1:
                time.sleep(0.2)

            while self._pulsedmasterlogic.elapsed_sweeps < 2:
                time.sleep(0.2)
            print("2")

            # we can stop measurement simply by calling:
            self._pulsedmasterlogic.toggle_pulsed_measurement(False)
            # Wait until the pulsedmeasurementlogic is actually idle and the measurement is stopped
            while self._pulsedmasterlogic.status_dict['measurement_running'] == 1:  # module_state() == 'locked':#
                # print(pulsedmeasurementlogic.module_state())
                time.sleep(0.2)
            print("Final state:", self._pulsedmasterlogic.module_state(), ", final sweep:", self._pulsedmasterlogic.elapsed_sweeps)

            ############################################################

            contrast = self._pulsedmasterlogic.signal_data[1]
            error = self._pulsedmasterlogic.measurement_error[1]
            odmr[:, i] = contrast[0]
            odmr_err[:, i] = error[0]

            print("odmr:", odmr, odmr_err)

        self.trigger()
        return False, odmr

    def close_odmr(self):
        """ Close the odmr and clean up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        return self._sc_device.close_counter()

    def close_odmr_clock(self):
        """ Close the odmr and clean up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        return self._sc_device.close_clock()

    def get_odmr_channels(self):
        """ Return a list of channel names.

        @return list(str): channels recorded during ODMR measurement
        """
        return self._sc_device.get_counter_channels()

    ### ----------- Microwave interface commands -----------

    def trigger(self):

        return self._mw_device.trigger()

    def off(self):
        """
        Switches off any microwave output.
        Must return AFTER the device is actually stopped.

        @return int: error code (0:OK, -1:error)
        """
        return self._mw_device.off()

    def get_status(self):
        """
        Gets the current status of the MW source, i.e. the mode (cw, list or sweep) and
        the output state (stopped, running)

        @return str, bool: mode ['cw', 'list', 'sweep'], is_running [True, False]
        """
        return self._mw_device.get_status()

    def get_power(self):
        """
        Gets the microwave output power for the currently active mode.

        @return float: the output power in dBm
        """
        return self._mw_device.get_power()

    def get_frequency(self):
        """
        Gets the frequency of the microwave output.
        Returns single float value if the device is in cw mode.
        Returns list like [start, stop, step] if the device is in sweep mode.
        Returns list of frequencies if the device is in list mode.

        @return [float, list]: frequency(s) currently set for this device in Hz
        """
        return self._mw_device.get_frequency()

    def cw_on(self):
        """
        Switches on cw microwave output.
        Must return AFTER the device is actually running.

        @return int: error code (0:OK, -1:error)
        """
        return self._mw_device.cw_on()

    def set_cw(self, frequency=None, power=None):
        """
        Configures the device for cw-mode and optionally sets frequency and/or power

        @param float frequency: frequency to set in Hz
        @param float power: power to set in dBm

        @return tuple(float, float, str): with the relation
            current frequency in Hz,
            current power in dBm,
            current mode
        """
        return self._mw_device.set_cw(frequency=frequency, power=power)

    def list_on(self):
        """
        Switches on the list mode microwave output.
        Must return AFTER the device is actually running.

        @return int: error code (0:OK, -1:error)
        """
        return self._mw_device.list_on()

    def set_list(self, frequency=None, power=None):
        """
        Configures the device for list-mode and optionally sets frequencies and/or power

        @param list frequency: list of frequencies in Hz
        @param float power: MW power of the frequency list in dBm

        @return list, float, str: current frequencies in Hz, current power in dBm, current mode
        """
        return self._mw_device.set_list(frequency=frequency, power=power)

    def reset_listpos(self):
        """
        Reset of MW list mode position to start (first frequency step)

        @return int: error code (0:OK, -1:error)
        """
        return self._mw_device.reset_listpos()

    def sweep_on(self):
        """ Switches on the sweep mode.

        @return int: error code (0:OK, -1:error)
        """
        return self._mw_device.sweep_on()

    def set_sweep(self, start=None, stop=None, step=None, power=None):
        """
        Configures the device for sweep-mode and optionally sets frequency start/stop/step
        and/or power

        @return float, float, float, float, str: current start frequency in Hz,
                                                 current stop frequency in Hz,
                                                 current frequency step in Hz,
                                                 current power in dBm,
                                                 current mode
        """
        return self._mw_device.set_sweep(start=start, stop=stop, step=step,
                                         power=power)

    def reset_sweeppos(self):
        """
        Reset of MW sweep mode position to start (start frequency)

        @return int: error code (0:OK, -1:error)
        """
        return self._mw_device.reset_sweeppos()

    def set_ext_trigger(self, pol, timing):
        """ Set the external trigger for this device with proper polarization.

        @param TriggerEdge pol: polarisation of the trigger (basically rising edge or falling edge)
        @param timing: estimated time between triggers

        @return object: current trigger polarity [TriggerEdge.RISING, TriggerEdge.FALLING]
        """
        return self._mw_device.set_ext_trigger(pol=pol, timing=timing)

    def get_limits(self):
        """ Return the device-specific limits in a nested dictionary.

          @return MicrowaveLimits: Microwave limits object
        """
        return self._mw_device.get_limits()

    @property
    def oversampling(self):
        return self._oversampling

    @oversampling.setter
    def oversampling(self, val):
        if not isinstance(val, (int, float)):
            self.log.error('oversampling has to be int of float.')
        else:
            self._oversampling = int(val)

    @property
    def lock_in_active(self):
        return self._lock_in_active

    @lock_in_active.setter
    def lock_in_active(self, val):
        if not isinstance(val, bool):
            self.log.error('lock_in_active has to be boolean.')
        else:
            self._lock_in_active = val
            if self._lock_in_active:
                self.log.warn('Lock-In is not implemented')
