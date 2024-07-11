from calendar import c
import time # pausing executing, formatting timestrings
import yaml
import re
import sys
import os
import binascii
from pathlib import Path # for opening and saving files
from enum import Enum
from serial.tools import list_ports
from datetime import datetime # getting current time for logging
from shrooly_cli.serial_handler import serial_handler, serial_trigger_response_type, serial_trigger_result
from .logging_handler import logging_handler, logging_level
from .terminal_handler import terminal_handler
from .fileconverter import string_to_comand_chunks
from .constants import PROMPT_REGEX, CLI_VERSION

class command_success(Enum):
    OK = 0
    ERROR = 1

class shrooly_file:
    def __init__(self, name, size, last_modified):
        self.name = name
        self.size = size
        self.last_modified = last_modified

    def __repr__(self):
        return f"filename: \"{self.name}\", size: {self.size} byte(s), last_modified: {self.last_modified}"

class shrooly:
    status = {}
    boot_successful = False
    login_successful = False
    connected = False
    communication_in_progress = False
    file_list = []
    terminal_handler_inst = None
    version = CLI_VERSION

    logger = logging_handler()
    esp_reset_callback = None
    exceptionCallback = None

    def __init__(self, log_level=None, ext_logger=None, serial_log=None, exceptionCallback=None):
        self.logger.ext_log_pipe = ext_logger
        self.exceptionCallback = exceptionCallback
        
        if log_level is not None:
            self.logger.setLevel(log_level)
        elif ext_logger is not None:
            self.logger.setLevel(ext_logger.getEffectiveLevel())
        
        self.serial_handler_instance = serial_handler(log_level, ext_logger, serial_log)
        self.terminal_handler_inst = terminal_handler(self.serial_handler_instance)

    def kill(self):
        self.logger.debug("[SHROOLY] Kill has been called, stopping all threads and subprocesses")
        self.serial_handler_instance.disconnect()
        self.connected = False
        sys.exit()

    def serialExceptionCallback(self):
        self.logger.critical("[SHROOLY] Unexpected serial error in serial_handler")
        
        if self.connected:
            self.serial_handler_instance.disconnect()
            self.connected = False
        
        if self.exceptionCallback is not None:
            self.exceptionCallback()
        sys.exit()

    def connect(self, port=None, baud=921600, no_reset=False, esp_reset_callback=None):
        self.esp_reset_callback = esp_reset_callback
        if port is None:
            self.logger.debug("[SHROOLY] Serial port is not specified, autoselecting it..")
            port = self.autoselect_serial()
        
        if port == "":
            self.logger.critical("[SHROOLY] No serial devices found, exiting..")
            sys.exit()
        
        if no_reset == False:
            self.serial_handler_instance.add_serial_trigger("boot_finish", r"I \(\d+\) [a-zA-Z_]*: Initialization completed\.", self.callback_boot, True)
            self.serial_handler_instance.add_serial_trigger("fw_version", r"I \(\d+\) SHROOLY_MAIN: Firmware: (v\d+.\d+-\d+) \((Build: [a-zA-Z0-9,: ]+)\)", self.callback_fw_version, True, serial_trigger_response_type.MATCHGROUPS)
            self.serial_handler_instance.add_serial_trigger("hw_revision", r"I \(\d+\) SHROOLY_MAIN: HW revision:\s+(0b\d+) \(PCB (v\d\.\d)\)", self.callback_hw_version, True, serial_trigger_response_type.MATCHGROUPS)
            self.serial_handler_instance.add_serial_trigger("esp_error_catcher", r"E \(\d+\).*", 
                                                            lambda x, y: 
                                                                self.logger.error("[SHROOLY] ESP_ERROR: " + str(y[:-2])), False, serial_trigger_response_type.LINE, response_timeout=0)
            
        self.logger.info("[SHROOLY] Connecting to Shrooly at: " + port + " @baud: " + str(baud))
        self.serial_handler_instance.serialExceptionCallback = self.serialExceptionCallback
        self.connected = self.serial_handler_instance.connect(port, no_reset)
        
        return self.connected
    
    def enterTerminal(self, wait_for_reset=True):
        if self.esp_reset_callback is not None:
            time.sleep(0.5)
            self.serial_handler_instance.add_serial_trigger(
                trigger_name="esp_reset_catcher", 
                regex_trigger=r"rst:0x[0-9a-f]+ \(([A-Z_]+)\),boot:0x[0-9a-f]+ \(([A-Z_]+)\).*",
                callback=self.esp_reset_callback, 
                single_use=False, 
                response_type=serial_trigger_response_type.LINE, 
                response_timeout=0)
        
        boot_started_time = time.time()
        
        if wait_for_reset is True:
            self.logger.info("[SHROOLY] Waiting for boot to finish..")
            boot_tries = 0
            boot_tries_limit = 100
            
            while True:
                if self.boot_successful == True:
                    boot_finish_time = time.time()
                    self.logger.info("[SHROOLY] Booted successfully! Time: " + "{:.2f}".format((boot_finish_time-boot_started_time)) + " s")
                    break
                time.sleep(0.1)
                boot_tries+=1
                if boot_tries == boot_tries_limit:
                    self.logger.critical("[SHROOLY] Couldn't finish boot in 10 seconds, exiting..")
                    self.kill()
            
        time.sleep(1)
            
        self.logger.info("[SHROOLY] Sending CTRL+C to Shrooly to enter interactive mode")

        success = self.serial_handler_instance.direct_write('\x03')
        
        if success == False:
            self.logger.error("[SHROOLY] Error while sending CTRL+C, exiting..")
            self.disconnect()
            return False

        time.sleep(0.1)
        self.logger.debug("[SHROOLY] Sending CRLF")

        resp_status, resp_payload = self.terminal_handler_inst.send_command(strInput='', name="login_prompt")
        
        if resp_status == serial_trigger_result.OK:
            self.logger.info("[SHROOLY] Successfully entered interactive mode")
            self.login_successful = True
            return True
        elif resp_status == serial_trigger_result.TIMEOUT:
            self.logger.error("[SHROOLY] Timeout during entering interactive mode, exiting..")
            self.disconnect()
            return False
        elif resp_status == serial_trigger_result.ERROR:
            self.logger.error("[SHROOLY] Error during entering interactive mode, exiting..")
            self.disconnect()
            return False
        else:
            self.logger.critical("[SHROOLY] Unknown during entering interactive mode, exiting..")
            self.disconnect()
            return False
    
    def disconnect(self):
        if self.connected:
            self.serial_handler_instance.disconnect()
    
    def autoselect_serial(self):
        #logger.info("Host OS: " + sys.platform)
        port_list = list_ports.comports()
        autoselected_port = ""

        if len(port_list) == 0:
            autoselected_port = ""
        elif len(port_list) == 1:
            autoselected_port = port_list[0].device
        else:
            if sys.platform == "linux":
                for port_iterator in port_list:
                    if re.search("^\/dev\/ttyACM\d$", port_iterator.device):
                        autoselected_port = port_iterator.device

                if autoselected_port == "":
                    autoselected_port = port_list[0].device
            elif sys.platform == "darwin":
                for port_iterator in port_list:
                    if re.search("^\/dev\/cu.usbmodem\d*$", port_iterator.device):
                        autoselected_port = port_iterator.device

                if autoselected_port == "":
                    autoselected_port = port_list[0].device
            elif sys.platform == "nt":
                logger.error("Serial port autoselect is not yet available, please select a serial port manually. Exiting")
                sys.exit()
        #logger.info("Autoselected serial port: " + autoselected_port)
        return autoselected_port
    
    def callback_fw_version(self, status, payload):
        if status == serial_trigger_result.OK:
            self.logger.info("[SHROOLY] FW Version: " + payload[0])
            json_line = {}
            json_line['Boot-Firmware'] = {'version': payload[0],'build_date': payload[1]}
            self.status.update(json_line)
        else:
            self.logger.error("[SHROOLY] Error while getting fw-version, got: " + str(payload))

    def callback_hw_version(self, status, payload):
        if status == serial_trigger_result.OK and len(payload) == 2:
            self.logger.info("[SHROOLY] HW Version: " + payload[0] + " (" + payload[1] + ")")
            
            json_line = {}
            json_line['Boot-Hardware'] = {'version': payload[1], 'hwcfg':payload[0]}
            self.status.update(json_line)
        else:
            self.logger.error("[SHROOLY] Error while getting hw-version, got: " + str(payload))

    def callback_compile_time(self, status, payload):
        if status == serial_trigger_result.OK:
            self.logger.info("[SHROOLY] Compile time: " + payload[0])
            self.status['compile_time'] = payload
        else:
            self.logger.error("[SHROOLY] Error while getting compile time, got: " + str(payload))
    
    def callback_boot(self, status, payload):
        if status == serial_trigger_result.OK:
            self.boot_successful = True
        else:
            self.logger.error("[SHROOLY] Error while looking for boot, got: " + str(payload))
        # TBD: kivételkezelés a status-ra

    def list_files(self):
        self.logger.info("[SHROOLY] Requesting list of files..")
        request_string = f"fs list"
        
        resp_status, resp_payload = self.terminal_handler_inst.send_command(strInput=request_string, name="fs_list_prompt")
        self.logger.debug("[SHROOLY] Response status:" + str(resp_status))

        if resp_status is not serial_trigger_result.OK:
            self.logger.error("[SHROOLY] Error during request: " + str(resp_status))
            # TBD: handle other types of errors
            return command_success.ERROR, ""
        
        yaml_body = resp_payload[resp_payload.find("\r\n")+2:]
        
        files = []
        parsed_data = yaml.safe_load(yaml_body)
        
        for filename, file_data in parsed_data.get("Files", {}).items():
            name = filename
            size = int(file_data.get("Size").split()[0])  # Parse size as number
            last_modified = file_data.get("Last modified on")  # Parse date string
            files.append(shrooly_file(name, size, last_modified))

        return command_success.OK, files

    def updateStatus(self):
        self.logger.info("[SHROOLY] Requesting status of device..")
        request_string = f"status"
        resp_status, resp_payload = self.terminal_handler_inst.send_command(request_string, name="status_prompt")
        self.logger.debug("[SHROOLY] Response status:" + str(resp_status))
        
        if resp_status is not serial_trigger_result.OK:
            self.logger.error("[SHROOLY] Error during request: " + str(resp_status))
            return command_success.ERROR, ""

        try:
            yaml_body = resp_payload[resp_payload.find("\r\n")+2:]        
            yaml_data = yaml.safe_load(yaml_body)
            
            json_resp = {}
            for yaml_block in yaml_data.items():
                category_parsed = yaml_block[0]
                yaml_body = yaml_block[1]
                
                json_resp[category_parsed] = []
                json_line = {}
                for dictionary in yaml_body:
                    
                    for key, value in dictionary.items():
                        regex_str = "([A-Za-z_]+)[\(%\)]*"
                        re_match = re.search(regex_str, key)
                        key_cleaned = re_match.group(1) # cleaning the unit inside the ()
                        if isinstance(value, datetime):
                            value = str(value.isoformat())
                        json_line[key_cleaned] = value

                json_resp[category_parsed] = json_line
            
            self.status.update(json_resp) # TBD: selective update

            return command_success.OK, json_resp
        except Exception as e:
            self.logger.error("[SHROOLY] Error during parsing of response: " + str(e))
            return command_success.ERROR, ""

    
    def read_file(self, strInput):
        self.logger.info("[SHROOLY] Requesting read of file: " + strInput)
        request_string = f"fs read --file {strInput} --format ASCII"
        resp_status, resp_payload = self.terminal_handler_inst.send_command(request_string, name="fs_read_prompt")
        
        if resp_status is not serial_trigger_result.OK:
            self.logger.error("[SHROOLY] Error during request: " + str(resp_status))
            return command_success.ERROR, ""
        #print(resp_payload.encode().hex())

        
        if resp_payload.endswith('\r\n'):
            resp_payload = resp_payload[:-2]
            #print(resp_payload.encode().hex())

        payload_body = resp_payload.split('\r\n')
        if payload_body[1].startswith("status: file does not exist"):
            return command_success.ERROR, ""
        
        resp_payload = resp_payload.split("data: ")[1]
        #print(resp_payload)
        return command_success.OK, resp_payload

    def send_file(self, file_path):
        self.logger.info("[SHROOLY] File transfer process has started!")
        file_name = Path(file_path).name
        self.logger.debug("[SHROOLY] File name from path: " + file_name)
        
        if os.path.exists(file_path) is False:
            self.logger.error("[SHROOLY] Requested file doesn't exist on client device, exiting..")
            return command_success.ERROR
        
        file_content = ""
        file_size = os.path.getsize(file_path)
        
        self.logger.info("[SHROOLY] File to send: " + file_name + ", size: " + str(file_size) + " byte(s)")
        
        request_string = f"fs delete {file_name}"
        resp_status, resp_payload = self.terminal_handler_inst.send_command(request_string, name="fs_delete_prompt")

        if resp_status is serial_trigger_result.OK:
            response_split = resp_payload.split('\r\n')
            if response_split[1].startswith("status: error while deleting file"):
                self.logger.info("[SHROOLY] File doesn't exist on Shrooly.")
            else:
                self.logger.info("[SHROOLY] File already existed on Shrooly, deleted it.")

        else:
            self.logger.error("[SHROOLY] Error while trying to delete file")
        
        try:
            with open(file_path, 'r') as file:
                file_content = file.read()
            self.logger.info("[SHROOLY] File successfully opened on client")
        except:
            self.logger.error("[SHROOLY] Error while opening file, maybe it doesn't extist?")
            return command_success.ERROR

        max_line_length = 192
        #fs read --file testfile.lua --format ASCII
        
        chunks = string_to_comand_chunks(42+len(file_name), file_content, max_line_length)

        retries = 0
        
        chunk_counter = 0        
        start_time = time.time()
        
        while chunk_counter < len(chunks):
            element = chunks[chunk_counter]
            self.logger.info("[SHROOLY] Sending chunk: " + str(chunk_counter) + "/" + str(len(chunks)-1))

            hex_bytes = bytes.fromhex(element)

            crc32_value = binascii.crc32(hex_bytes)
            crc32_value_hex = hex(crc32_value)[2:]
            
            self.logger.debug("Chunk content: " + element + ", CRC32: " + str(crc32_value_hex))

            request_string = f"fs append --file {file_name} --crc {crc32_value_hex} --stream {element}"
            self.logger.debug("Request string: " + request_string)

            resp_status, resp_payload = self.terminal_handler_inst.send_command(request_string, name="fs_append_prompt")
            #print(resp_status)
            #print(resp_payload)

            if resp_status is serial_trigger_result.OK:
                #self.logger.info("[SHROOLY] Chunk successfully transferred")
                response_split = resp_payload.split('\r\n')
                # print(response_split)
                # print(response_split[2])
                transfer_status = response_split[2]
                
                if "status: ok" in response_split:
                    self.logger.debug("[SHROOLY] Transfer and CRC are OK, getting next chunk!")
                    chunk_counter += 1
                else:
                    self.logger.error("[SHROOLY] Transfer was OK, but chunk wasn't accepted, retrying with same chunk.")
                    retries+= 1
            elif resp_status is serial_trigger_result.ERROR:
                self.logger.error("[SHROOLY] Error during transmission, exiting.")
                return command_success.ERROR
            elif resp_status is serial_trigger_result.TIMEOUT:
                self.logger.error("[SHROOLY] Timeout during transmission, NOT getting next chunk! Retry..")
                retries+= 1
            
            if retries > 5:
                self.logger.error("[SHROOLY] Too many retries during sending of file. Exiting..")
                break

            #time.sleep(10)

        #self.logger.info("[SHROOLY] File transfer has finished!")
        end_time = time.time()
        self.logger.info("[SHROOLY] File transfer time: " + "{:.2f}".format((end_time-start_time)) + " s, speed: " + "{:.2f}".format(file_size/(end_time-start_time)) + " bytes/second" )
        return command_success.OK

    def delete_file(self, strInput):
        self.logger.info(f"[SHROOLY] Requesting deletion of file: {strInput}")
        request_string = f"fs delete {strInput}"
        
        resp_status, resp_payload = self.terminal_handler_inst.send_command(strInput=request_string, name="fs_delete_prompt")
        self.logger.debug("[SHROOLY] Response status:" + str(resp_status))

        if resp_status is not serial_trigger_result.OK:
            self.logger.error("[SHROOLY] Error during request: " + str(resp_status))
            # TBD: handle other types of errors
            return command_success.ERROR

        payload_body = resp_payload.split('\r\n')
        if payload_body[1].startswith("status: error while deleting file"):
            return command_success.ERROR    
        
        return command_success.OK
    
    def set_datetime(self, timeInput):
        self.logger.info(f"[SHROOLY] Trying to set datetime to: {timeInput}")
        request_string = f"datetime set {timeInput}"
        
        resp_status, resp_payload = self.terminal_handler_inst.send_command(strInput=request_string, name="set_datetime_prompt")
        self.logger.debug("[SHROOLY] Response status:" + str(resp_status))

        if resp_status is not serial_trigger_result.OK:
            self.logger.error("[SHROOLY] Error during request: " + str(resp_status))
            return command_success.ERROR
        
        return command_success.OK
    
    def set_humidifier(self, state):
        if state != 0 and state != 1:
            self.logger.error("[SHROOLY] Invalid state for humidifier, must be 0 or 1")
            return command_success.ERROR
        
        self.logger.info(f"[SHROOLY] Trying to set humidifer to: {state}")
        request_string = f"lua execute set_humidifier({state})"
        
        resp_status, resp_payload = self.terminal_handler_inst.send_command(strInput=request_string, name="set_humidifer_prompt")
        self.logger.debug("[SHROOLY] Response status:" + str(resp_status))

        if resp_status is not serial_trigger_result.OK:
            self.logger.error("[SHROOLY] Error during request: " + str(resp_status))
            return command_success.ERROR
        
        return command_success.OK
    
    def get_datetime(self):
        self.logger.info(f"[SHROOLY] Trying to get datetime..")
        request_string = f"datetime get"
        
        resp_status, resp_payload = self.terminal_handler_inst.send_command(strInput=request_string, name="get_datetime_prompt")
        self.logger.debug("[SHROOLY] Response status:" + str(resp_status))

        if resp_status is not serial_trigger_result.OK:
            self.logger.error("[SHROOLY] Error during request: " + str(resp_status))
            return command_success.ERROR, ""
        
        payload_split = resp_payload.split('\r\n')

        regex_match = re.search("(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", payload_split[1])
        if regex_match == False:
            return command_success.ERROR, ""
        
        payload = regex_match.groups()[0]
        time_from_device = datetime.fromisoformat(payload)

        return command_success.OK, time_from_device

    def start_script(self, strInput):
        self.logger.info(f"[SHROOLY] Requesting start of script: {strInput}")
        request_string = f"lua start {strInput}"
        
        resp_status, resp_payload = self.terminal_handler_inst.send_command(strInput=request_string, name="start_script_prompt")
        self.logger.debug("[SHROOLY] Response status:" + str(resp_status))

        if resp_status is not serial_trigger_result.OK:
            self.logger.error("[SHROOLY] Error during request: " + str(resp_status))
            return command_success.ERROR
        
        return command_success.OK

    def stop_script(self):
        self.logger.info(f"[SHROOLY] Requesting stop of running script")
        request_string = f"lua stop"
        
        resp_status, resp_payload = self.terminal_handler_inst.send_command(strInput=request_string, name="stop_script_prompt")
        self.logger.debug("[SHROOLY] Response status:" + str(resp_status))

        if resp_status is not serial_trigger_result.OK:
            self.logger.error("[SHROOLY] Error during request: " + str(resp_status))
            return command_success.ERROR
        
        return command_success.OK

    def disable_bt(self):
        self.logger.info(f"[SHROOLY] Requesting disabling of bt interface")
        request_string = f"bt disable"
        
        resp_status, resp_payload = self.terminal_handler_inst.send_command(strInput=request_string, name="bt_disable_prompt")
        self.logger.debug("[SHROOLY] Response status:" + str(resp_status))

        if resp_status is not serial_trigger_result.OK:
            self.logger.error("[SHROOLY] Error during request: " + str(resp_status))
            return command_success.ERROR
        
        return command_success.OK
    
    def reset(self):
        self.logger.info(f"[SHROOLY] Requesting reset of device")
        request_string = f"reboot"
        
        resp_status, resp_payload = self.terminal_handler_inst.send_command(strInput=request_string, name="reboot_prompt", no_trigger=True)
        self.logger.debug("[SHROOLY] Response status:" + str(resp_status))

        if resp_status is not serial_trigger_result.OK:
            self.logger.error("[SHROOLY] Error during request: " + str(resp_status))
            return command_success.ERROR
        
        return command_success.OK
    
    def capture_frame_buffer(self):
        self.logger.info(f"[SHROOLY] Requesting frame from device")
        request_string = f"capture_frame_buffer"
        
        resp_status, resp_payload = self.terminal_handler_inst.send_command(strInput=request_string, name="capture_frame_buffer_prompt")
        self.logger.debug("[SHROOLY] Response status:" + str(resp_status))

        if resp_status is not serial_trigger_result.OK:
            self.logger.error("[SHROOLY] Error during request: " + str(resp_status))
            return command_success.ERROR, ""
        
        return command_success.OK, resp_payload

    def parse_json(self, json_obj, path=''):
        if isinstance(json_obj, dict):
            for k, v in json_obj.items():
                current_path = f"{path}.{k}" if path else k
                self.parse_json(v, current_path)
        elif isinstance(json_obj, list):
            for i, item in enumerate(json_obj):
                current_path = f"{path}[{i}]"
                self.parse_json(item, current_path)
        else:
            self.logger.info(f"{path}: {json_obj}")
