from .constants import PROMPT_REGEX
from shrooly_cli.serial_handler import serial_trigger_response_type

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
        
        def send_command(self, strInput, name="", timeout=1):
            self.serial_handler_instance.add_serial_trigger(name, PROMPT_REGEX, self.terminal_command_callback, True, serial_trigger_response_type.BUFFER, 5)
            self.serial_handler_instance.direct_write(strInput+"\r\n")
            self.waiting_for_terminal_resp = True

            while True: # TBD: kellene timeout ide is, hátha serial rétegen gond van
                if self.waiting_for_terminal_resp is False:
                    break
            return self.terminal_resp_status, self.terminal_resp_payload