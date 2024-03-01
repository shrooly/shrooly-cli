import time # pausing executing, formatting timestrings
import yaml
import re
import sys
import os
import binascii
from pathlib import Path # for opening and saving files
from enum import Enum
from serial.tools import list_ports
from shrooly_cli.serial_handler import serial_handler, serial_trigger_response_type, serial_callback_status
from .logger_switcher import logger_switcher
from .terminal_handler import terminal_handler
from .fileconverter import string_to_comand_chunks
from .constants import PROMPT_REGEX

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

    logger = logger_switcher() # TBD: meg kellene szüntetni a logger_switchert

    def __init__(self, ext_logger=None):
        if ext_logger != None:
            self.logger.ext_log_pipe = ext_logger
            self.logger.ext_log_pipe.setLevel(ext_logger.getEffectiveLevel())
        
        self.serial_handler_instance = serial_handler(ext_logger)
        self.terminal_handler_inst = terminal_handler(self.serial_handler_instance)

    def kill(self):
        self.logger.debug("[CLI] Kill has been called, stopping all threads and subprocesses")
        self.serial_handler_instance.kill()
        sys.exit()

    def connect(self, port=None, baud=921600, no_reset=False):
        if port is None:
            self.logger.info("[CLI] Serial port is not specified, autoselecting it..")
            port = self.autoselect_serial()
        
        if port == "":
            self.logger.critical("[CLI] No serial devices found, exiting..")
            sys.exit()
        
        if no_reset == False:
            self.serial_handler_instance.add_serial_trigger("boot_finish", "I \(\d+\) [a-zA-Z_]*: Task initialization completed\.", self.callback_boot, True)
            self.serial_handler_instance.add_serial_trigger("fw_version", "I \(\d+\) SHROOLY_MAIN: Firmware: (v\d+.\d+-\d+) \((Build: [a-zA-Z0-9,: ]+)\)", self.callback_fw_version, True, serial_trigger_response_type.MATCHGROUPS)
            self.serial_handler_instance.add_serial_trigger("hw_revision", "I \(\d+\) SHROOLY_MAIN: HW revision:\s+(0b\d+) \(PCB (v\d\.\d)\)", self.callback_hw_version, True, serial_trigger_response_type.MATCHGROUPS)

        self.logger.info("[CLI] Connecting to Shrooly at: " + port + " @baud: " + str(baud))
        self.connected = self.serial_handler_instance.connect(port, baud, no_reset)
        
        if self.connected == False:
            #self.logger.critical("[CLI] Error during connecting")
            return False
        
        boot_started_time = time.time()
        
        if no_reset == False:
            self.logger.info("[CLI] Waiting for boot to finish..")
            boot_tries = 0
            boot_tries_limit = 100
            while True:
                if self.boot_successful == True:
                    boot_finish_time = time.time()
                    self.logger.info("[CLI] Booted successfully! Time: " + "{:.2f}".format((boot_finish_time-boot_started_time)) + " s")
                    break
                time.sleep(0.1)
                boot_tries+=1
                if boot_tries == boot_tries_limit:
                    self.logger.critical("[CLI] Couldn't finish boot in 10 seconds, exiting..")
                    self.kill()
            
        time.sleep(1)
            
        self.logger.info("[CLI] Sending CTRL+C to Shrooly to enter interactive mode")

        self.serial_handler_instance.direct_write('\x03')
        time.sleep(0.1)
        self.logger.debug("[CLI] Sending CRLF")

        resp_status, resp_payload = self.terminal_handler_inst.send_command(strInput='\r\n', name="login_prompt")
        
        if resp_status:
            self.logger.info("[CLI] Successfully entered interactive mode")
            self.login_successful = True
            return True
        else:
            self.serial_handler_instance.disconnect()
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
        if status == serial_callback_status.OK:
            self.logger.info("[CLI] FW Version: " + payload[0])
            json_line = {}
            json_line['Firmware'] = {'version': payload[0],'build_date': payload[1]}
            self.status.update(json_line)
        else:
            self.logger.error("[CLI] Error while getting fw-version, got: " + str(payload))

    def callback_hw_version(self, status, payload):
        if status == serial_callback_status.OK and len(payload) == 2:
            self.logger.info("[CLI] HW Version: " + payload[0] + " (" + payload[1] + ")")
            
            json_line = {}
            json_line['Hardware'] = {'version': payload[1], 'hwcfg':payload[0]}
            self.status.update(json_line)
        else:
            self.logger.error("[CLI] Error while getting hw-version, got: " + str(payload))

    def callback_compile_time(self, status, payload):
        if status == serial_callback_status.OK:
            self.logger.info("[CLI] Compile time: " + payload[0])
            self.status['compile_time'] = payload
        else:
            self.logger.error("[CLI] Error while getting compile time, got: " + str(payload))
    
    def callback_boot(self, status, payload):
        if status == serial_callback_status.OK:
            self.boot_successful = True
        else:
            self.logger.error("[CLI] Error while looking for boot, got: " + str(payload))
        # TBD: kivételkezelés a status-ra

    def list_files(self):
        self.logger.info("[CLI] Requesting list of files..")
        request_string = f"fs list"
        
        resp_status, resp_payload = self.terminal_handler_inst.send_command(strInput=request_string, name="fs_list_prompt")
        self.logger.debug("[CLI] Response status:" + str(resp_status))

        if resp_status is not serial_callback_status.OK:
            self.logger.error("[CLI] Error during request: " + str(resp_status))
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

    def updateStatus(self, format="PARSED"):
        self.logger.info("[CLI] Requesting status of device..")
        request_string = f"status"
        resp_status, resp_payload = self.terminal_handler_inst.send_command(request_string, name="status_prompt")
        self.logger.debug("[CLI] Response status:" + str(resp_status))
        
        if resp_status is not serial_callback_status.OK:
            self.logger.error("[CLI] Error during request: " + str(resp_status))
            return command_success.ERROR, ""

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
                    
                    if re_match:
                        key_new = re_match.group(1)
                        if key_new == "Datetime":
                            value = str(value.isoformat())
                        json_line[key_new] = value
                    else:
                        print("no regex at: " + key)

            json_resp[category_parsed] = json_line
        
        self.status.update(json_resp) # TBD: selective update

        return command_success.OK, json_resp
    
    def read_file(self, strInput):
        self.logger.info("Requesting read of file: " + strInput)
        request_string = f"fs read --file {strInput} --format ASCII"
        resp_status, resp_payload = self.terminal_handler_inst.send_command(request_string, name="fs_read_prompt")
        
        if resp_status is not serial_callback_status.OK:
            self.logger.error("[CLI] Error during request: " + str(resp_status))
            return command_success.ERROR, ""
        
        payload_body = resp_payload.split('\r\n')
        if payload_body[1].startswith("status: file does not exist"):
            return command_success.ERROR, ""
        
        resp_payload = resp_payload.split("data: ")[1]

        return command_success.OK, resp_payload

    def send_file(self, file_name):
        self.logger.info("[CLI] File transfer process has started!")
        file_path = Path(file_name).name
        self.logger.debug("[CLI] File name from path: " + file_path)
        
        if os.path.exists(file_path) is False:
            self.logger.error("[CLI] Requested file doesn't exist on client device, exiting..")
            return command_success.ERROR
        
        file_content = ""
        file_size = os.path.getsize(file_path)
        
        self.logger.info("[CLI] File to send: " + file_name + ", size: " + str(file_size) + " byte(s)")
        
        request_string = f"fs delete {file_name}"
        resp_status, resp_payload = self.terminal_handler_inst.send_command(request_string, name="fs_delete_prompt")

        if resp_status is serial_callback_status.OK:
            response_split = resp_payload.split('\r\n')
            if response_split[1].startswith("status: ok"):
                self.logger.info("[CLI] File already existed on Shrooly, deleted it.")
            else:
                self.logger.info("[CLI] File doesn't exist on Shrooly.")

        else:
            self.logger.error("[CLI] Error while trying to delete file")
        
        try:
            with open(file_name, 'r') as file:
                file_content = file.read()
            self.logger.info("[CLI] File successfully opened on client")
        except:
            self.logger.error("[CLI] Error while opening file, maybe it doesn't extist?")
            return command_success.ERROR

        #self.logger.debug("File content: ")
        #self.logger.debug(file_content)

        #target_file_name = file_name
        max_line_length = 192
        #fs read --file testfile.lua --format ASCII
        
        chunks = string_to_comand_chunks(42+len(file_name), file_content, max_line_length)

        chunk_counter = 0
        # TBD: count retries
        #self.logger.info("Command: fs append, target: " + target_file_name + ", chunk size: " + str(max_line_length) + " bytes, no. of chunks: " + str(len(chunks)))
        
        start_time = time.time()
        retries = 0
        
        while chunk_counter < len(chunks):
            element = chunks[chunk_counter]
            self.logger.info("[CLI] Sending chunk: " + str(chunk_counter) + "/" + str(len(chunks)-1))

            hex_bytes = bytes.fromhex(element)

            crc32_value = binascii.crc32(hex_bytes)
            crc32_value_hex = hex(crc32_value)[2:]
            
            self.logger.debug("Chunk content: " + element + ", CRC32: " + str(crc32_value_hex))

            request_string = f"fs append --file {file_name} --crc {crc32_value_hex} --stream {element}"
            self.logger.debug("Request string: " + request_string)

            resp_status, resp_payload = self.terminal_handler_inst.send_command(request_string, name="fs_append_prompt")
            #print(resp_status)
            #print(resp_payload)

            if resp_status is serial_callback_status.OK:
                #self.logger.info("[CLI] Chunk successfully transferred")
                response_split = resp_payload.split('\r\n')
                #print(response_split)
                # print(response_split[2])
                transfer_status = response_split[2]
                
                if transfer_status == "status: ok":
                    self.logger.debug("[CLI] Transfer and CRC are OK, getting next chunk!")
                    chunk_counter += 1
                else:
                    self.logger.error("[CLI] Transfer was OK, but chunk wasn't accepted, retrying with same chunk.")
                    retries+= 1
            elif resp_status is serial_callback_status.ERROR:
                self.logger.error("[CLI] Error during transmission, exiting.")
                return command_success.ERROR
            elif resp_status is serial_callback_status.TIMEOUT:
                self.logger.error("[CLI] Timeout during transmission, NOT getting next chunk! Retry..")
                retries+= 1
            
            if retries > 5:
                self.logger.error("[CLI] Too many retries during sending of file. Exiting..")
                break

        #self.logger.info("[CLI] File transfer has finished!")
        end_time = time.time()
        self.logger.info("[CLI] File transfer time: " + "{:.2f}".format((end_time-start_time)) + " s, speed: " + "{:.2f}".format(file_size/(end_time-start_time)) + " bytes/second" )
        return command_success.OK

    def delete_file(self, strInput):
        self.logger.info(f"[CLI] Requesting deletion of file: {strInput}")
        request_string = f"fs delete {strInput}"
        
        resp_status, resp_payload = self.terminal_handler_inst.send_command(strInput=request_string, name="fs_delete_prompt")
        self.logger.debug("[CLI] Response status:" + str(resp_status))

        if resp_status is not serial_callback_status.OK:
            self.logger.error("[CLI] Error during request: " + str(resp_status))
            # TBD: handle other types of errors
            return command_success.ERROR

        payload_body = resp_payload.split('\r\n')
        if payload_body[1].startswith("status: error while deleting file"):
            return command_success.ERROR    
        
        return command_success.OK
    
    def save_file(self, strInput):
        pass

    def start_cultivation(self, strInput):
        pass

    def stop_cultivation(self):
        pass

    def disable_radios(self):
        pass

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
