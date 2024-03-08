from .constants import PROMPT_REGEX
from shrooly_cli.serial_handler import serial_trigger_response_type, serial_interface_status, serial_callback_status

class terminal_handler:
    """
    A class that handles terminal commands and responses.

    Attributes:
        waiting_for_terminal_resp (bool): Indicates if the terminal is waiting for a response.
        terminal_resp_status (str): The status of the terminal response.
        terminal_resp_payload (str): The payload of the terminal response.
        serial_handler_instance (object): An instance of the serial handler.

    Methods:
        __init__(self, serial_handler): Initializes the terminal handler with a serial handler instance.
        terminal_command_callback(self, status, payload): Callback function for terminal command response.
        send_command(self, strInput, name="", timeout=5): Sends a command to the terminal and waits for response.
    """

    waiting_for_terminal_resp = False
    terminal_resp_status = ""
    terminal_resp_payload = ""
    serial_handler_instance = None

    def __init__(self, serial_handler):
        """
        Initializes the terminal handler with a serial handler instance.

        Args:
            serial_handler (object): An instance of the serial handler.
        """
        self.serial_handler_instance = serial_handler

    def terminal_command_callback(self, status, payload):
        """
        Callback function for terminal command response.

        Args:
            status (str): The status of the terminal response.
            payload (str): The payload of the terminal response.
        """
        self.terminal_resp_status = status
        self.terminal_resp_payload = payload
        self.waiting_for_terminal_resp = False
    
    def send_command(self, strInput, name="", timeout=5, no_trigger=False):
        if self.serial_handler_instance.status is not serial_interface_status.CONNECTED:
            return serial_callback_status.ERROR, ""
        
        if no_trigger is False:
            self.serial_handler_instance.add_serial_trigger(name, PROMPT_REGEX, self.terminal_command_callback, True, serial_trigger_response_type.BUFFER, timeout)
        
        self.serial_handler_instance.direct_write(strInput+"\r\n")
        self.waiting_for_terminal_resp = True

        if no_trigger is True:
            return serial_callback_status.OK, ""
        
        while True: 
            if self.waiting_for_terminal_resp is not True:
                return self.terminal_resp_status, self.terminal_resp_payload
            if self.serial_handler_instance.status is not serial_interface_status.CONNECTED:
                return serial_callback_status.ERROR, ""