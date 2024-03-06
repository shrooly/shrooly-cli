from .constants import PROMPT_REGEX
from shrooly_cli.serial_handler import serial_trigger_response_type, serial_interface_status, serial_callback_status

class terminal_handler:
    waiting_for_terminal_resp = False
    terminal_resp_status = ""
    terminal_resp_payload = ""
    serial_handler_instance = None

    def __init__(self, serial_handler):
        self.serial_handler_instance = serial_handler

    def terminal_command_callback(self, status, payload):
        self.terminal_resp_status = status
        self.terminal_resp_payload = payload
        self.waiting_for_terminal_resp = False
    
    def send_command(self, strInput, name="", timeout=5):
        if self.serial_handler_instance.status is not serial_interface_status.CONNECTED:
            return serial_callback_status.ERROR, ""
        
        self.serial_handler_instance.add_serial_trigger(name, PROMPT_REGEX, self.terminal_command_callback, True, serial_trigger_response_type.BUFFER, timeout)
        self.serial_handler_instance.direct_write(strInput+"\r\n")
        self.waiting_for_terminal_resp = True

        while True: 
            if self.waiting_for_terminal_resp is not True:
                return self.terminal_resp_status, self.terminal_resp_payload
            if self.serial_handler_instance.status is not serial_interface_status.CONNECTED:
                return serial_callback_status.ERROR, ""