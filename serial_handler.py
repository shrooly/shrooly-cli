import time
import serial
import threading
from colorlog import ColoredFormatter
import logging
import queue
import re
from constants import (HIGH, LOW, MINIMAL_EN_LOW_DELAY)

class write_buffer_element:
    payload = ""
    callback = None
    metadata = ""
    
    def __init__(self, payload, callback=None, metadata=""):
        self.callback = callback
        self.payload = payload
        self.metadata = metadata

class serial_handler:
    active_element = None
    write_buffer_queue = queue.Queue()
    
    is_first_received_line = True
    serial_line = ""
    serial_response = ""
    exit_signal = False
    prompt_received = False
    boot_finished = False
    
    def __init__(self, logger):
        self.logger = logger
        self.serial_line = ""
        self.serial_response = ""
        self.ser = serial.Serial()
        self.logger.setLevel(logger.getEffectiveLevel())
        #self.logger.setLevel("DEBUG")
    
    def connect(self, port='/dev/ttyACM0', baud=921600, no_reset=False):
        self.logger.debug("[SERIAL_HANDLER] Serial connect has been called")
        try:
            self.ser = serial.serial_for_url(port, baud, timeout=1, do_not_open=True, exclusive=True)
            self.ser.setRTS(LOW)
            self.ser.setDTR(LOW)
            
            self.ser.open()
            self.logger.info("Successfully opened serial!")

            self.ser.setRTS(HIGH)
            self.ser.setDTR(HIGH)
        except Exception as e:
            print(str(e))
            self.logger.critical("Couldn't connect to serial at " + port + ", baud: " + str(baud))
            exit()

        if(no_reset==False):
            self.logger.info("Sending hard reset to device..")
            
            self.ser.setRTS(LOW)  # EN=LOW, chip in reset
            time.sleep(MINIMAL_EN_LOW_DELAY)
            self.ser.setRTS(HIGH)  # EN=HIGH, chip out of reset
        
        self.read_thread = threading.Thread(target=self.handle_read_serial_port)
        self.read_thread.start()

        self.write_thread = threading.Thread(target=self.handle_write_serial_port)
        self.write_thread.start()
        self.logger.debug("[SERIAL_HANDLER] Serial connection successful!")

    def disconnect(self):
        self.logger.info("Serial disconnect has been called")
        self.exit_signal = True
    
    def getQueueSize(self):
        return self.write_buffer_queue.qsize()

    def getActiveElement(self):
        return self.active_element
    
    def handle_read_serial_port(self):
        if not self.ser.is_open: # exit if serial port is not open
            self.logger.critical("Serial port is not open while attempting to read, exiting..")
            exit()

        while True: # infinite loop for handling reads
            if self.exit_signal: # if the external exit_signal is raised, kill the loop
                self.logger.debug("[SERIAL_HANDLER] Exiting serial read loop")
                break
            
            try: # try to read, continue the while loop if error
                serial_cache = self.ser.read_all()
            except Exception as e:
                self.logger.error("[SERIAL_HANDLER] Serial error: " + str(e))
                continue

            serial_cache = serial_cache.decode("utf-8", "ignore")

            for serial_character in serial_cache:
                #self.logger.debug("[SERIAL_HANDLER] SERIAL CHAR RECEIVED: " + serial_character)
                if serial_character == '\r': # we want to filter out carriage return chars
                    pass
                elif serial_character == '\n': # end of line received
                    #self.logger.debug("[SERIAL_HANDLER]  End char received, processing: " + self.serial_line)
                    self.serial_line = self.serial_line + '\n'
                    self.process_serial_line(self.serial_line)
                    self.serial_line = ""
                else:
                    self.serial_line = self.serial_line + str(serial_character)

    def add_to_write_queue(self, payload, callback=None, metadata=""):
        element_to_put = write_buffer_element(payload, callback, metadata)
        
        payload_cleaned = self.remove_special_characters(payload)
        payload_cleaned_hex = self.get_hex_string(payload_cleaned)

        self.logger.debug("[SERIAL_HANDLER] Added to serial queue: \'" + str(payload_cleaned) + "\', HEX: " + payload_cleaned_hex)
        self.write_buffer_queue.put(element_to_put)
    
    def handle_write_serial_port(self):
        try:
            while True:
                if self.exit_signal:
                    self.logger.debug("[SERIAL_HANDLER] Exiting serial write thread")
                    break

                if self.write_buffer_queue.qsize() > 0 and self.active_element == None:
                    self.active_element = self.write_buffer_queue.get()
                    payload_string = str(self.active_element.payload)
                    payload_string_cleaned = self.remove_special_characters(payload_string)
                    if (len(payload_string_cleaned) > 20):
                        payload_string_cleaned = payload_string_cleaned[0:20] + "..."
                    payload_string_cleaned_capped = "\"" + payload_string_cleaned+ "\""
                    self.logger.debug("[SERIAL_HANDLER] Serial_write: Queue size > 0, no active element, getting next one: " + payload_string_cleaned_capped)
                    self.ser.reset_input_buffer()
                    self.serial_line = ""
                    self.serial_response = ""
                    self.is_first_received_line = True
                    self.direct_write(self.active_element.payload)
                    self.logger.debug("[SERIAL_HANDLER] Serial_write: Payload sent!")
                
                if self.active_element is not None:
                    self.logger.debug("[SERIAL_HANDLER] Serial_write: Active element is being processed, waiting for completion. Qsize: " + str(self.write_buffer_queue.qsize()))
                    time.sleep(0.5)
                
        except serial.SerialException as e:
            self.logger.error("[SERIAL_HANDLER] Serial error: " + str(e))
    
    def direct_write(self, strInput):
        data_to_send = strInput.encode('utf-8')
        #print("sending: " + strInput)
        try:
            self.ser.write(data_to_send)
        except Exception as e:
            self.logger.critical("error while writing to serial port: " + str(e)) 

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
    
    def process_serial_line(self, strInput):
        payload_cleaned = self.remove_special_characters(strInput)

        boot_finish_pattern = "I \(\d+\) [a-zA-Z_]*: Task initialization completed\."
        boot_finish_match = re.search(boot_finish_pattern, self.serial_line)
        
        prompt_pattern = "[a-zA-Z0-9]+:~\$.+"
        prompt_match = re.search(prompt_pattern, self.serial_line)

        if prompt_match:
            return_text = "[SERIAL_HANDLER] Prompt found in serial line!: \"" + payload_cleaned + "\""
            if self.prompt_received == False: 
                self.prompt_received = True
            self.serial_line = ""
            if self.active_element is not None: # it is a prompt and there is a defined active element
                self.logger.debug(return_text + " Callback specified, invoking it: \"" + str(self.active_element.callback.__name__) + "\"")
                self.active_element.callback(self.serial_response, self.active_element.metadata)
                self.active_element = None
            else:
                self.logger.debug(return_text + " No callback specified.")
            
            self.serial_response = ""
        elif boot_finish_match:
            self.logger.debug("[SERIAL_HANDLER] Boot finish line found")
            self.boot_finished = True
        else:
            self.logger.debug("[SERIAL_HANDLER] processing line: \"" + payload_cleaned) 
            
            if self.is_first_received_line == False: 
                self.serial_response = self.serial_response + strInput
            
            if self.is_first_received_line:
                self.is_first_received_line = False
    
    def remove_special_characters(self, input_string):
       
        cleaned_string = input_string.replace('\r', '').replace('\t', '').replace('\n', '').replace('\x03', '').replace("^[[0n", '')
        return cleaned_string

    def get_hex_string(self, input_string):
        hex_string = input_string.encode('utf-8')
        hex_string = "0x" + hex_string.hex()
        return hex_string


def processDumpJson(strInput):
    strInput = strInput.replace('\n', '')
    strInput = strInput.replace('\t', '')

    logger.info("SHIT RECEIVED: >>" + strInput + "<<")

def processFileList(strInput):
    logger.info("PFL:")
    logger.info(strInput)


if __name__ == "__main__":
    formatter = ColoredFormatter(
        "%(asctime)s - %(log_color)s%(levelname)-8s%(reset)s %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S',
        reset=True,
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        },
        secondary_log_colors={},
        style='%'
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger = logging.getLogger('my_logger')
    logger.addHandler(handler)

    logger.setLevel("DEBUG")

    serial_handler_instance = serial_handler(logger)
    serial_handler_instance.connect()
    logger.info("Serial thread started")
    
    serial_handler_instance.direct_write('\x03') # '\x03'
    time.sleep(3)
    serial_handler_instance.add_to_write_queue("fs_list\r\n\r\n", processFileList)
    time.sleep(3)
    #serial_handler_instance.write_to_serial_port_raw('\r\n') # '\x03'
    while True:
        serial_handler_instance.add_to_write_queue("dump\r\n\r\n", processDumpJson)
        time.sleep(10)
        pass