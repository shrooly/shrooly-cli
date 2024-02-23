import time
import serial
import threading
import logging
import queue
import re
from enum import Enum
from .constants import (HIGH, LOW, MINIMAL_EN_LOW_DELAY)
from .logger_switcher import logger_switcher, logging_level

class serial_trigger_response_type(Enum):
    LINE = 0
    MATCHGROUPS = 1
    BUFFER = 2

class serial_trigger:
    name = ""
    regex_pattern = ""
    callback = None
    active = True
    single_use = False
    response_type = serial_trigger_response_type.BUFFER

    def __init__(self, name: str, regex_pattern: str, callback=None, single_use=False, response_type=serial_trigger_response_type.BUFFER):
        self.name = name
        self.regex_pattern = regex_pattern
        self.callback = callback
        self.single_use = single_use
        self.response_type = response_type

class serial_handler:
    exit_signal = False        
    serial_buffer = ""
    serial_trigger_array = []

    logger = logger_switcher()
    
    def __init__(self, ext_logger=None):
        self.ser = serial.Serial()
        
        self.logger.ext_log_pipe = ext_logger
        
        if ext_logger is not None: 
            self.logger.setLevel(ext_logger.getEffectiveLevel())
    
    def connect(self, port='/dev/ttyACM0', baud=921600, no_reset=False):
        self.logger.debug("[SERIAL_HANDLER] Serial connect has been called")
        try:
            self.ser = serial.serial_for_url(port, baud, timeout=1, do_not_open=True, exclusive=True)
            self.ser.setRTS(LOW)
            self.ser.setDTR(LOW)
            
            self.ser.open()
            self.logger.info("[SERIAL_HANDLER] Successfully opened serial!")

            self.ser.setRTS(HIGH)
            self.ser.setDTR(HIGH)
        except Exception as e:
            self.logger.critical("[SERIAL_HANDLER] Couldn't connect to serial at " + port + ", baud: " + str(baud) + ". Exception: " + str(e))
            self.kill()

        if(no_reset==False):
            self.logger.info("[SERIAL_HANDLER] Sending hard reset to device..")
            
            self.ser.setRTS(LOW)  # EN=LOW, chip in reset
            time.sleep(MINIMAL_EN_LOW_DELAY)
            self.ser.setRTS(HIGH)  # EN=HIGH, chip out of reset
        
        self.read_thread = threading.Thread(target=self.handle_read_serial_port)
        self.read_thread.start()

        self.logger.debug("[SERIAL_HANDLER] Serial connection successful!")

    def disconnect(self):
        self.logger.info("[SERIAL_HANDLER] Serial disconnect has been called")
        self.kill()

    def kill(self):
        self.logger.debug("[SERIAL_HANDLER] Kill has been called, stopping all threads")
        self.exit_signal = True
        
    def add_serial_trigger(self, name, regex_pattern, callback=None, single_use=False, response_type=serial_trigger_response_type.BUFFER):
        serial_trigger_instance = serial_trigger(name, regex_pattern, callback, single_use, response_type)
        self.logger.debug("[SERIAL_HANDLER] Registering new serial trigger: Name:" + name + ", regex: \"" + regex_pattern + "\"")
        self.serial_trigger_array.append(serial_trigger_instance)
    
    def handle_read_serial_port(self):
        if not self.ser.is_open: # exit if serial port is not open
            self.logger.critical("[SERIAL_HANDLER] Serial port is not open while attempting to read, exiting..")
            self.kill()

        serial_line_buffer = ""

        while True: # infinite loop for handling reads
            if self.exit_signal: # if the external exit_signal is raised, kill the loop
                self.logger.debug("[SERIAL_HANDLER] Exiting serial read loop")
                break
            
            try: # try to read, exit the script if error is detected
                serial_cache = self.ser.read_all()
            except Exception as e:
                self.logger.critical("[SERIAL_HANDLER] Serial error: " + str(e))
                self.kill()
                continue

            serial_cache = serial_cache.decode("utf-8", "ignore")

            for serial_character in serial_cache:
                #self.logger.debug("[SERIAL_HANDLER] SERIAL CHAR RECEIVED: " + serial_character)
                serial_line_buffer = serial_line_buffer + str(serial_character)
                if(serial_character == '\n'):
                    self.logger.debug("[SERIAL_HANDLER] processing line: " + self.remove_special_characters(serial_line_buffer))
                    self.process_serial_line_buffer(serial_line_buffer)
                    self.serial_buffer += serial_line_buffer
                    serial_line_buffer = ""

    def process_serial_line_buffer(self, serial_line_buffer):
        for serial_trigger_instance in self.serial_trigger_array:            
            regex_pattern = serial_trigger_instance.regex_pattern
            regex_match = re.search(regex_pattern, serial_line_buffer)
            
            if regex_match: # If regex is a match
                self.logger.debug("[SERIAL_HANDLER] Match at: \"" + serial_trigger_instance.name + "\"")
                
                if serial_trigger_instance.callback != None: # There is a callback
                    self.logger.debug("[SERIAL_HANDLER] Invoking callback: \"" + str(serial_trigger_instance.callback.__name__) + "\"")
                    
                    if serial_trigger_instance.response_type == serial_trigger_response_type.LINE:
                        serial_trigger_instance.callback(serial_line_buffer)
                    elif serial_trigger_instance.response_type == serial_trigger_response_type.MATCHGROUPS:
                        serial_trigger_instance.callback(regex_match.groups())
                    elif serial_trigger_instance.response_type == serial_trigger_response_type.BUFFER: 
                        serial_trigger_instance.callback(self.serial_buffer)
                        self.serial_buffer = ""
                else: # There is no callback
                    self.logger.debug("[SERIAL_HANDLER] No callback has been specified")

                if serial_trigger_instance.single_use == True:
                    serial_trigger_instance.active = False
                    self.logger.debug("[SERIAL_HANDLER] Trigger was single use, deactivating.")
                
            else:
                self.logger.debug("[SERIAL_HANDLER] No match found at: \"" + serial_trigger_instance.name + "\"")

        self.serial_trigger_array = [obj for obj in self.serial_trigger_array if obj.active]

    # def add_to_write_queue(self, payload, callback=None, metadata=""):
    #     element_to_put = write_buffer_element(payload, callback, metadata)
        
    #     payload_cleaned = self.remove_special_characters(payload)
    #     payload_cleaned_hex = self.get_hex_string(payload_cleaned)

    #     self.logger.debug("[SERIAL_HANDLER] Added to serial queue: \'" + str(payload_cleaned) + "\', HEX: " + payload_cleaned_hex)
    #     self.write_buffer_queue.put(element_to_put)
    
    # def handle_write_serial_port(self):
    #     try:
    #         while True:
    #             if self.exit_signal:
    #                 self.logger.debug("[SERIAL_HANDLER] Exiting serial write thread")
    #                 break

    #             if self.write_buffer_queue.qsize() > 0 and self.active_element == None:
    #                 self.active_element = self.write_buffer_queue.get()
    #                 payload_string = str(self.active_element.payload)
    #                 payload_string_cleaned = self.remove_special_characters(payload_string)
                    
    #                 if (len(payload_string_cleaned) > 20):
    #                     payload_string_cleaned = payload_string_cleaned[0:20] + "..."
                    
    #                 payload_string_cleaned_capped = "\"" + payload_string_cleaned+ "\""
    #                 self.logger.debug("[SERIAL_HANDLER] Serial_write: Queue size > 0, no active element, getting next one: " + payload_string_cleaned_capped)
    #                 self.ser.reset_input_buffer()
    #                 self.serial_line = ""
    #                 self.serial_response = ""
    #                 self.is_first_received_line = True
    #                 self.direct_write(self.active_element)
    #                 self.logger.debug("[SERIAL_HANDLER] Serial_write: Payload sent!")
                
    #             if self.active_element is not None:
    #                 self.logger.debug("[SERIAL_HANDLER] Serial_write: Active element is being processed, waiting for completion. Qsize: " + str(self.write_buffer_queue.qsize()))
    #                 time.sleep(0.1)
                
    #     except serial.SerialException as e:
    #         self.logger.error("[SERIAL_HANDLER] Serial error: " + str(e))
    
    def direct_write(self, strInput):
        data_to_send = strInput.encode('utf-8')
        
        try:
            self.ser.write(data_to_send)
        except Exception as e:
            self.logger.critical("[SERIAL_HANDLER] Error while writing to serial port: " + str(e)) 

        strinput_beautifed = ""
        
        for char in strInput:
            if char == '\x03':
                strinput_beautifed += "^C"
            elif char == '\r':
                strinput_beautifed += "\\r"
            elif char == '\n':
                strinput_beautifed += "\\n"
            else:
                strinput_beautifed += char

        strInput_hex = self.get_hex_string(strInput)
        self.logger.debug("[SERIAL_HANDLER] Serial_write: Sending payload: \'" + strinput_beautifed + "\', HEX: " + strInput_hex)
    
    def remove_special_characters(self, input_string):
        cleaned_string = input_string.replace('\r', '').replace('\t', '').replace('\n', '').replace('\x03', '').replace("^[[0n", '')
        return cleaned_string

    def get_hex_string(self, input_string):
        hex_string = input_string.encode('utf-8')
        hex_string = "0x" + hex_string.hex()
        return hex_string