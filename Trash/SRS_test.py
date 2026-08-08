
import socket  # ADDED
import numpy as np



class SG(object):
    def __init__(self, ip="10.107.54.148"):  # Added

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # ADDED
        try:
            self.socket.connect((ip, 5025))  # ADDED
        except:
            print("check your signal generator connections or ip address")
        self.mfnc = {"sin": '0', "ramp": '1', "triangle": '2', "square": '3', "noise": '4', "external": '5'}

    def send_cmd(self, cmd):  # John: modify "_write", refer "tell" in `tektronix_awg5002c`
        cmd = cmd + "\n"  # ADDED
        sent = self.socket.send(cmd.encode())  # ADDED but not as .encode(), but as UTF-8 byte type (CPed from "tell")
        if sent == 0:
            raise RuntimeError("signal generator socket connection broken.")

    def recieve(self):  # JOHN: no parallel, but required by "query" below #ADDED
        chunk = self.socket.recv(4096)  # Added
        if chunk == b'':
            raise RuntimeError("signal generator socket connection broken")
        return chunk

    def set_display(self):  # John: This and many other settings are in those 15 entries under set_list
        self.send_cmd('DISP 2')

    def query(self, cmd):  # JOHN: modify "_ask", refer "ask" in `tektronix_awg5002c` #ADDED
        self.send_cmd(cmd)
        return (self.recieve())

    def set_amplitude(self, amplitude, channel="rf", unit="dbm"):
        channel = channel.lower()  # John: not sure what this "lower" does, no parallel found in qudi
        unit = unit.lower()

        if unit == "dbm":
            if amplitude < -110 or amplitude > 5:
                raise Exception("Output power can only be between -110dbm and 16.5dbm")
        elif unit == "rms":
            if amplitude > 1.5:
                raise Exception("rms voltage can not be greater than 1.5V")
        elif unit == "vpp":
            if amplitude > 1.5 * np.sqrt(8):
                raise Exception("Vpp can not exceed 4.2V")
        else:
            raise Exception("amplitude unit should be dbm, rms, or vpp")

        if channel == "rf":
            self.send_cmd('AMPR ' + str(amplitude) + ' ' + unit)
        elif channel == "low":
            self.send_cmd('AMPL ' + str(amplitude) + ' ' + unit)
        else:
            raise Exception("Select a channel between rf and low")

    def close(self):  # Added
        self.socket.close()

sg = SG()