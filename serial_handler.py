import time
import serial
import threading
from colorlog import ColoredFormatter
import logging
import queue
import re

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
    
    def __init__(self, logger):
        self.logger = logger
        self.serial_line = ""
        self.serial_response = ""
        self.ser = serial.Serial()
        self.logger.setLevel(logger.getEffectiveLevel())
        #self.logger.setLevel("DEBUG")
    
    def connect(self, port='/dev/ttyACM0', baud=921600):
        self.logger.debug("[SERIAL_HANDLER] Serial connect has been called")
        try:
            self.ser = serial.Serial(port, baud, timeout=1)
        except Exception as e:
            self.logger.critical("Couldn't connect to serial at " + port + ", baud: " + str(baud))
            exit()
        
        self.read_thread = threading.Thread(target=self.handle_read_serial_port)
        self.read_thread.start()

        self.write_thread = threading.Thread(target=self.handle_write_serial_port)
        self.write_thread.start()
        self.logger.debug("[SERIAL_HANDLER] Serial connection successful!")

    def disconnect(self):
        self.logger.info("[SERIAL_HANDLER] Serial disconnect has been called")
        self.exit_signal = True
    
    def getQueueSize(self):
        return self.write_buffer_queue.qsize()

    def getActiveElement(self):
        return self.active_element
    
    def handle_read_serial_port(self):
        try:
            if not self.ser.is_open:
                self.logger.info("[SERIAL_HANDLER] Serial port is not open, opening it..")
                self.ser.open()

            while True:
                if self.exit_signal:
                    self.logger.debug("[SERIAL_HANDLER] Exiting serial read thread")
                    break
                
                try:
                    serial_cache = self.ser.read_all()
                    serial_cache = serial_cache.decode("utf-8", "ignore")

                    for serial_character in serial_cache:
                        #self.logger.debug("[SERIAL_HANDLER] SERIAL CHAR RECEIVED: " + serial_character)
                        
                        if serial_character == '\r':
                            pass
                        elif serial_character == '\n':
                            #self.logger.debug("[SERIAL_HANDLER]  End char received, processing: " + self.serial_line)
                            self.serial_line = self.serial_line + '\n'
                            self.process_serial_line(self.serial_line)
                            self.serial_line = ""
                        else:
                            self.serial_line = self.serial_line + str(serial_character)
                        
                        prompt_pattern = "[a-zA-Z0-9]+:~\$.+"
                        prompt_match = re.search(prompt_pattern, self.serial_line)

                        if prompt_match:
                            self.logger.debug("[SERIAL_HANDLER] Prompt found in serial cache, sending it to processor")
                            self.process_serial_line(self.serial_line, True)
                            if self.prompt_received == False: 
                                self.prompt_received = True
                            self.serial_line = ""

                except serial.SerialException as e:
                    self.logger.error("[SERIAL_HANDLER] Serial error: " + str(e))
                    #exit()

        except serial.SerialException as e:
            self.logger.error("[SERIAL_HANDLER] Serial port error: {e}")

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
                    self.logger.debug("[SERIAL_HANDLER] Serial_write: Qsize > 0, no active element, getting next one: " + payload_string_cleaned_capped)
                    self.ser.reset_input_buffer()
                    self.is_first_received_line = True
                    self.direct_write(self.active_element.payload)
                    self.logger.debug("[SERIAL_HANDLER] Serial_write: Payload sent!")
                
                if self.active_element is not None:
                    self.logger.debug("[SERIAL_HANDLER] Serial_write: Active element is being processed, waiting for completion. Qsize: " + str(self.write_buffer_queue.qsize()))
                    time.sleep(0.5)
                
        except serial.SerialException as e:
            self.logger.error("[SERIAL_HANDLER] Serial error: " + str(e))
    
    def direct_write(self, strInput):
        self.logger.debug("[SERIAL_HANDLER] ENTERED DIRECT WRITE")
        #self.ser.reset_input_buffer()
        payload_cleaned = self.remove_special_characters(strInput)
        payload_cleaned_hex = self.get_hex_string(payload_cleaned)
                    
        self.logger.debug("[SERIAL_HANDLER] Serial_write: Sending payload: \'" + payload_cleaned + "\', HEX: " + payload_cleaned_hex)
        data_to_send = strInput.encode('utf-8')
        self.ser.write(data_to_send)
    
    def process_serial_line(self, strInput, prompt=False):
        payload_cleaned = self.remove_special_characters(strInput)
        endstring = ""
        if prompt:
            endstring = " (it is a prompt)"
        self.logger.debug("[SERIAL_HANDLER] Processing serial line: \"" + payload_cleaned +"\""+ endstring) 
        
        if prompt:
            if self.active_element is not None: # it is a prompt and there is a defined active element
                self.logger.debug("[SERIAL_HANDLER] Prompt found, calling callback: \"" + str(self.active_element.callback.__name__) + "\"")
                self.active_element.callback(self.serial_response, self.active_element.metadata)

            self.serial_response = ""
            self.active_element = None
        elif self.is_first_received_line == False: 
            self.serial_response = self.serial_response + strInput
        
        if self.is_first_received_line:
            self.is_first_received_line = False
    
    def remove_special_characters(self, input_string):
        cleaned_string = input_string.replace('\r', '').replace('\t', '').replace('\n', '')
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