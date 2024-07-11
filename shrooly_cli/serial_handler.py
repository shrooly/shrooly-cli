import time
# import serial
import os
import subprocess
import threading
import re
from enum import Enum
from .constants import (HIGH, LOW, MINIMAL_EN_LOW_DELAY)
from .logging_handler import logging_handler, logging_level
from datetime import datetime

class serial_trigger_result(Enum):
    OK = 0
    ERROR = 1
    TIMEOUT = 2

class serial_trigger_response_type(Enum):
    LINE = 0
    MATCHGROUPS = 1
    BUFFER = 2

class serial_interface_status(Enum):
    DISCONNECTED = 0
    CONNECTED = 1
    ERROR = 2

class serial_trigger:
    name = ""
    regex_pattern = ""
    callback = None
    active = True
    response_timeout = 0
    added_time = 0
    single_use = False
    response_type = serial_trigger_response_type.BUFFER

    def __init__(self, name, regex_pattern, callback=None, single_use=False, response_type=serial_trigger_response_type.BUFFER, response_timeout=0):
        self.name = name
        self.regex_pattern = regex_pattern
        self.callback = callback
        self.single_use = single_use
        self.response_type = response_type
        self.response_timeout = response_timeout
        self.added_time = time.time()

class serial_handler:
    exit_signal = False        
    serial_buffer = ""
    serial_trigger_array = []
    serial_line_buffer = ""
    status = serial_interface_status.DISCONNECTED
    logger = logging_handler()
    serial_log = None
    serialExceptionCallback = None
    
    master_fd = None
    slave_fd = None
    idf_monitor_process = None
    
    def __init__(self, log_level=None,ext_logger=None, serial_log=None):
        self.logger.ext_log_pipe = ext_logger
        self.serial_log = serial_log

        if serial_log is not None:
            with open(serial_log, mode='w', newline='\n') as file:
                current_time = datetime.now()
                formatted_time = current_time.strftime("%Y-%m-%dT%H:%M:%S")
                file.write("Shrooly log started on: " + formatted_time + '\n')
                file.write("===========================================\n")
        
        if ext_logger is not None: 
            self.logger.setLevel(ext_logger.getEffectiveLevel())
        elif log_level is not None:
            self.logger.setLevel(log_level)

    def raiseSerialExceptionCallback(self):
        if self.serialExceptionCallback is not None:
            self.logger.error("[SERIAL_HANDLER] Unexpected serial error, calling the exception callback..")
            self.serialExceptionCallback()
        else:
            self.logger.error("[SERIAL_HANDLER] Unexpected serial error, no callback defined.")
            
    def read_stderr(self, pipe):
        while True:
            output = pipe.read(1024)
            if not output:
                break
            if self.exit_signal:
                break
            print(f"STDERR: {output}", end='')
    
    def connect(self, port='/dev/ttyACM0', no_reset=False):
        self.logger.debug("[SERIAL_HANDLER] Opening esp-idf monitor..")
        
        self.master_fd, self.slave_fd = os.openpty()
        
        command = ["python3", "-m", "esp_idf_monitor", "--no-reset", "-p", port]
        
        if no_reset == False:
            command = ["python3", "-m", "esp_idf_monitor", "-p", port]
        
        self.idf_monitor_process = subprocess.Popen(command, stdin=self.slave_fd, stdout=self.slave_fd, stderr=subprocess.PIPE, text=True)
        self.stderr_thread = threading.Thread(target=self.read_stderr, args=(self.idf_monitor_process.stderr,))
        self.stderr_thread.start()
        
        self.read_thread = threading.Thread(target=self.handle_read_serial_port)
        self.read_thread.start()

        self.logger.debug("[SERIAL_HANDLER] Opening was successful!")
        self.status = serial_interface_status.CONNECTED
        return True

    def disconnect(self):
        self.logger.debug("[SERIAL_HANDLER] Serial disconnect has been called")
        self.logger.debug("[SERIAL_HANDLER] Stopping serial read thread")
        self.exit_signal = True
        # Calling every outstanding serial trigger with status.ERROR, empty payload
        self.logger.debug("[SERIAL_HANDLER] Calling single use, still active triggers..")
        for serial_trigger_instance in self.serial_trigger_array:
            
            if serial_trigger_instance.single_use is True:
                serial_trigger_instance.callback(serial_trigger_result.ERROR, "")
                serial_trigger_instance.active = False

        self.serial_trigger_array = []
        
        #os.close(self.master_fd)
        #os.close(self.slave_fd)
        
        self.idf_monitor_process.terminate()
        self.idf_monitor_process.wait()
        # self.stderr_thread.join()
        
        self.logger.info("[SERIAL_HANDLER] esp-idf disconnected!")
        self.status = serial_interface_status.DISCONNECTED

    def add_serial_trigger(self, trigger_name, regex_trigger, callback=None, single_use=False, response_type=serial_trigger_response_type.BUFFER, response_timeout=10):
        serial_trigger_instance = serial_trigger(trigger_name, regex_trigger, callback, single_use, response_type, response_timeout)
        self.logger.debug("[SERIAL_HANDLER] Registering new serial trigger: Name:" + trigger_name + ", regex: \"" + self.get_beautified_string(regex_trigger) + "\", timeout: " + str(response_timeout))
        self.serial_trigger_array.append(serial_trigger_instance)
    
    def handle_read_serial_port(self):
        if not self.status == serial_interface_status.CONNECTED: # exit if serial reader is not connected
            self.logger.critical("[SERIAL_HANDLER] Serial handler is not connected while attempting to read, exiting..")
            self.raiseSerialExceptionCallback()
            self.disconnect()

        last_check_time = 0
        while True: # infinite loop for handling reads
            if self.exit_signal: # if the external exit_signal is raised, break the loop
                self.logger.debug("[SERIAL_HANDLER] Exiting serial read loop")
                break
            
            current_time = time.time()
            
            if last_check_time + 1 < current_time:
                #print("checking timeouts..")
                for serial_trigger_instance in self.serial_trigger_array:
                    if serial_trigger_instance.response_timeout > 0 and serial_trigger_instance.added_time + serial_trigger_instance.response_timeout < current_time:
                        #print("timeout at: " + serial_trigger_instance.name)
                        serial_trigger_instance.callback(serial_trigger_result.TIMEOUT, "")
                        serial_trigger_instance.active = False

                last_check_time = time.time()
            
            self.serial_trigger_array = [obj for obj in self.serial_trigger_array if obj.active]
            try: # try to read, exit the script if error is detected
                serial_cache = os.read(self.master_fd, 128).decode("utf-8", "ignore")
            except Exception as e:
                self.logger.critical("[SERIAL_HANDLER] Serial read error: " + str(e))
                self.raiseSerialExceptionCallback()
                self.disconnect()
                continue

            for serial_character in serial_cache:
                # print(serial_character + ", HEX: " + self.get_hex_string(serial_character))
                self.serial_line_buffer = self.serial_line_buffer + str(serial_character)
                
                if(serial_character == '\n'):
                    self.logger.debug("[SERIAL_HANDLER] processing line: " + self.remove_special_characters(self.serial_line_buffer))
                    
                    if self.serial_log is not None:
                        with open(self.serial_log, mode='a', encoding='utf-8') as file:
                            line_to_write = self.serial_line_buffer.replace('\r\r', '\r')
                            file.write(self.clean_ansi_escape_codes(line_to_write))

                    self.process_serial_line_buffer()
                    self.serial_buffer = self.serial_buffer + self.serial_line_buffer
                    self.serial_line_buffer = ""

    def process_serial_line_buffer(self):
        for serial_trigger_instance in self.serial_trigger_array:            
            regex_pattern = serial_trigger_instance.regex_pattern
            regex_match = re.search(regex_pattern, self.serial_line_buffer)
            
            if regex_match: # If regex is a match
                self.logger.debug("[SERIAL_HANDLER] Match at: \"" + serial_trigger_instance.name + "\"")
                
                if serial_trigger_instance.callback != None: # There is a callback
                    self.logger.debug("[SERIAL_HANDLER] Invoking callback: \"" + str(serial_trigger_instance.callback.__name__) + "\"")
                    
                    if serial_trigger_instance.response_type == serial_trigger_response_type.LINE:
                        serial_trigger_instance.callback(serial_trigger_result.OK, self.serial_line_buffer)
                    elif serial_trigger_instance.response_type == serial_trigger_response_type.MATCHGROUPS:
                        serial_trigger_instance.callback(serial_trigger_result.OK, regex_match.groups())
                    elif serial_trigger_instance.response_type == serial_trigger_response_type.BUFFER: 
                        serial_trigger_instance.callback(serial_trigger_result.OK, self.serial_buffer)
                else: # There is no callback
                    self.logger.debug("[SERIAL_HANDLER] No callback has been specified")

                if serial_trigger_instance.single_use == True:
                    serial_trigger_instance.active = False
                    self.logger.debug("[SERIAL_HANDLER] Trigger was single use, deactivating.")
                
            else:
                self.logger.debug("[SERIAL_HANDLER] No match found at: \"" + serial_trigger_instance.name + "\"")

        self.serial_trigger_array = [obj for obj in self.serial_trigger_array if obj.active]

    def direct_write(self, strInput):
        data_to_send = strInput.encode('utf-8')
        self.serial_buffer = ""
        self.serial_line_buffer = ""
        
        if not self.status == serial_interface_status.CONNECTED: # exit if serial handler is not connected
            self.logger.critical("[SERIAL_HANDLER] Serial handler is not connected while attempting to write, exiting..")
            self.raiseSerialExceptionCallback()
            self.disconnect()
            return

        try:
            os.write(self.master_fd, data_to_send)
        except Exception as e:
            self.logger.critical("[SERIAL_HANDLER] Error while writing to serial port: " + str(e)) 
            self.raiseSerialExceptionCallback()
            self.disconnect()
            return False
        
        strInput_hex = self.get_hex_string(strInput)
        strInput_beatufied = self.get_beautified_string(strInput)
        self.logger.debug("[SERIAL_HANDLER] Serial_write: Sending payload: \'" + strInput_beatufied + "\', HEX: " + strInput_hex)
        return True
    
    def get_beautified_string(self, input_string):
        string_beautifed = ""
        for char in input_string:
            if char == '\x03':
                string_beautifed += "^C"
            elif char == '\r':
                string_beautifed += "\\r"
            elif char == '\n':
                string_beautifed += "\\n"
            else:
                string_beautifed += char

        return string_beautifed

    def remove_special_characters(self, input_string):
        cleaned_string = input_string.replace('\r', '').replace('\t', '').replace('\n', '').replace('\x03', '').replace("^[[0n", '')
        return cleaned_string

    def get_hex_string(self, input_string):
        hex_string = input_string.encode('utf-8')
        hex_string = "0x" + hex_string.hex()
        return hex_string

    def clean_ansi_escape_codes(self, text):
        """
        Remove ANSI escape codes from a string
        """
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)