import sys # used for detecting host OS
import argparse # argument parsing
import json
import re # regex
import csv # csv writing
import os
import time # pausing executing, formatting timestrings
import logging # logging
import signal # for handling Ctrl-C exit preoperly
from colorlog import ColoredFormatter
from datetime import datetime # getting current time for logging
from pathlib import Path # for opening and saving files
from serial.tools import list_ports
import yaml
import binascii
from enum import Enum
# local dependencies
from shrooly_cli.serial_handler import serial_handler, serial_trigger_response_type, serial_callback_status
from .logger_switcher import logger_switcher, logging_level
from .constants import PROMPT_REGEX
from .fileconverter import string_to_comand_chunks

class shrooly_file:
    def __init__(self, name, size, last_modified):
        self.name = name
        self.size = size
        self.last_modified = last_modified

    def __repr__(self):
        return f"filename: \"{self.name}\", size: {self.size} byte(s), last_modified: {self.last_modified}"
    
class command_success(Enum):
    OK = 0
    ERROR = 1

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
            self.status['fw_version'] = payload
        else:
            self.logger.error("[CLI] Error while getting fw-version, got: " + str(payload))

    def callback_hw_version(self, status, payload):
        if status == serial_callback_status.OK and len(payload) == 2:
            self.logger.info("[CLI] HW Version: " + payload[0] + " (" + payload[1] + ")")
            self.status['hw_version'] = payload
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

    def getStatus(self, format="PARSED"):
        self.logger.info("[CLI] Requesting status of device..")
        request_string = f"status"
        resp_status, resp_payload = self.terminal_handler_inst.send_command(request_string, name="status_prompt")
        self.logger.debug("[CLI] Response status:" + str(resp_status))
        if resp_status is not serial_callback_status.OK:
            self.logger.error("[CLI] Error during request: " + str(resp_status))

        yaml_body = resp_payload[resp_payload.find("\r\n")+2:]
        
        yaml_data = yaml.safe_load(yaml_body)
        self.status.update(yaml_data) # TBD: manual update, omitting (%)-s
        return yaml_data
    
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
        
    # def save_file(self, strInput):
    #     self.logger.info("Requesting read of file: " + strInput)
    #     request_string = f"fs_read {strInput}\r\n"
    #     self.serial_handler_instance.add_to_write_queue(request_string, self.callback_save_file)
    
    # def disable_radios(self):
    #     self.logger.info("Disabling Radios")
    #     self.serial_handler_instance.add_to_write_queue("disable_radios\r\n", self.callback_disable_radios)

    # def turn_on_humidifer(self):
    #     self.logger.info("Turning on humidifer")
    #     self.serial_handler_instance.add_to_write_queue("ping_rp wpt_power 1\r\n", self.callback_turn_on_humidifer)

    # def start_cultivation(self, file):
    #     self.logger.info("Requesting cultivation start: " + file)
    #     request_string = f"start_cultivation file {file}\r\n"
    #     self.serial_handler_instance.add_to_write_queue(request_string, self.callback_start_cultivation)

    # def stop_cultivation(self):
    #     self.logger.info("Stopping cultivation")
    #     self.serial_handler_instance.add_to_write_queue("stop_cultivation\r\n", self.callback_stop_cultivation)
    
    # def callback_delete_file(self, strInput, metadata):
    #     strInput_parsed = strInput.split('\n')
    #     self.logger.info("Response: " + strInput_parsed[0])

    # def callback_save_file(self, strInput, metadata):
    #     index = strInput.find('\n')
    #     #print(index)
    #     first_line = strInput[0:index]
    #     #print(first_line)
    #     strInput = strInput[index+1:]
        
    #     if strInput.startswith("File does not exist"):
    #         filename = first_line.split(':')[1]
    #         self.logger.error("File doesn't exist:" + filename)
    #     else:
    #         re_match = re.search(r'\(([^)]+)\)', first_line)
    #         if re_match:
    #             file_name = re_match.group(1)
    #             with open(file_name, "w") as file:
    #                 file.write(strInput)
    #             self.logger.info("File successfully saved: " + file_name)
    #         else:
    #             self.logger.error("File name wasn't found in the first line, aborting.")
        
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

def main() -> None:
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

    logger = logging.getLogger('logger')
    logger.addHandler(handler)

    parser = argparse.ArgumentParser(description="Shrooly API wrapper")
    subparsers = parser.add_subparsers(dest='subcommand')
    parser_send_file = subparsers.add_parser('send_file', help='send a file')
    parser_send_file.add_argument('--file', help='name of the file to send', required=True)
    parser_delete_file = subparsers.add_parser('delete_file', help='delete a file')
    parser_delete_file.add_argument('--file', help='name of the file to delete', required=True)
    parser_read_file = subparsers.add_parser('read_file', help='read a file')
    parser_read_file.add_argument('--file', help='name of the file to open', required=True)
    parser_save_file = subparsers.add_parser('save_file', help='save a file')
    parser_save_file.add_argument('--file', help='name of the file to save', required=True)
    parser_start_cultivation = subparsers.add_parser('start_cultivation', help='start a cultivation')
    parser_start_cultivation.add_argument('--file', help='name of the lua script (stored on Shrooly) to start', required=True)
    subparsers.add_parser('stop_cultivation', help='stop cultivation')
    subparsers.add_parser('logger', help='logging')
    parser_status = subparsers.add_parser('status', help='get status of Shrooly')
    parser_status.add_argument('--format', choices=["JSON", "PARSED"], help='output format', default="PARSED", required=False)

    subparsers.add_parser('list_files', help='list files on Shrooly')
    subparsers.add_parser('disable_radios', help='disable Bluetooth and WiFi radios')
    
    parser.add_argument("--serial-port", help="set the Shrooly's serial-port")
    parser.add_argument("--serial-baud", default=921600, help="set the Shrooly's serial-port baud")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING"], default="INFO", help="Set the logging level (DEBUG, INFO, WARNING)")
    parser.add_argument("--no-reset", action='store_true', help="Disable reset on connection")

    args = parser.parse_args()

    logger.setLevel(args.log_level)

    signal.signal(signal.SIGINT, lambda sig, frame: (
        logger.critical("Ctrl-C received from user, stopping all threads.."),
        shrooly_instance.disconnect(),
        sys.exit()
    ))
    logger.info("Application has started!")

    shrooly_instance = shrooly(logger)
    
    if args.subcommand == "list_files":
        success = shrooly_instance.connect(args.serial_port, args.serial_baud, args.no_reset)
        if success == False:
            logger.critical("[CLI] Error during connection, exiting..")
            shrooly_instance.disconnect()
            sys.exit()
        success, files = shrooly_instance.list_files()
        if success is command_success.OK:
            logger.info("Found " + str(len(files)) + " file(s):")
            for file in files:
                logger.info(file)
        else:
            logger.error("Error during listing of files..")
    elif args.subcommand == "read_file":
        success = shrooly_instance.connect(args.serial_port, args.serial_baud, args.no_reset)
        if success == False:
            logger.critical("[CLI] Error during connection, exiting..")
            shrooly_instance.disconnect()
            sys.exit()
        success, resp = shrooly_instance.read_file(args.file)
        if success is command_success.OK:
            logger.info("[CLI] File read success")
            print(resp)
        else:
            logger.error("Error during reading of file, maybe it doesn't exist?")
    elif args.subcommand == "send_file":
        success = shrooly_instance.connect(args.serial_port, args.serial_baud, args.no_reset)
        
        if success == False:
            logger.critical("[CLI] Error during connection, exiting..")
            shrooly_instance.disconnect()
            sys.exit()
        resp = shrooly_instance.send_file(args.file)

        if resp == command_success.OK:
            logger.info("[CLI] File transfer success!")
        else:
            logger.error("[CLI] Error during file transfer, exiting..")
    elif args.subcommand == "delete_file":
        success = shrooly_instance.connect(args.serial_port, args.serial_baud, args.no_reset)
        
        if success == False:
            logger.critical("[CLI] Error during connection, exiting..")
            shrooly_instance.disconnect()
            sys.exit()
        
        resp = shrooly_instance.delete_file(args.file)
        
        if resp == command_success.OK:
            logger.info("[CLI] File delete success!")
        else:
            logger.error("[CLI] Error during file delete (maybe it doesn't exist on Shrooly?), exiting..")
    elif args.subcommand == "save_file":
        logger.critical("subcommand not implemented, exiting")
        # shrooly_instance.save_file(args.file)
    elif args.subcommand == "status":
        shrooly_instance.connect(args.serial_port, args.serial_baud, args.no_reset)
        resp = shrooly_instance.getStatus(args.format)
        print(shrooly_instance.status)
        yaml_out = yaml.dump(shrooly_instance.status)
        print(yaml_out)
    elif args.subcommand == "logger":
        logger.critical("subcommand not implemented, exiting")
        # shrooly_instance.turn_on_humidifer()
        # shrooly_instance.waitForCommandCompletion()
        # timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        # csv_file = "log-" + timestamp + ".csv"
        # field_names = ['Timestamp', 'Temperature', 'Humidity', 'VBUS', 'Fan duty', 'Fan speed', 'Humidiifer', 'Water level']

        # # Create the CSV file and write the header
        # with open(csv_file, mode='w', newline='') as file:
        #     writer = csv.DictWriter(file, fieldnames=field_names)
        #     writer.writeheader()

        # # Infinite loop to append a line every second
        # while True:
        #     try:
        #         # Open the CSV file in append mode
        #         with open(csv_file, mode='a', newline='') as file:
        #             writer = csv.DictWriter(file, fieldnames=field_names)
                    
        #             # Get the current timestamp
        #             timestamp = datetime.now().isoformat()

        #             # Generate some example data (you can replace this with your own data)
        #             resp = shrooly_instance.getStatus("JSON")
        #             print(type(resp))
        #             print(resp)
        #             resp = json.loads(resp)
        #             print(resp)
                                        
        #             # Write a new row to the CSV file
        #             writer.writerow(
        #                 {
        #                     'Timestamp': timestamp, 
        #                     'Temperature': resp["Monitoring"]["Temperature"],
        #                     'Humidity': resp["Monitoring"]["Humidity"],
        #                     'VBUS': resp["Debug"]["VBUS"],
        #                     'Fan duty': resp["Debug"]["Fan duty"],
        #                     'Fan speed': resp["Debug"]["Fan speed"],
        #                     'Humidiifer': resp["Debug"]["Humidifier"],
        #                     'Water level': resp["Monitoring"]["Water level"],
        #                     })
                
        #         # Wait for 10 second before appending the next line
        #         time.sleep(10)
        #     except Exception as e:
        #         pass
        #     except KeyboardInterrupt:
        #         shrooly_instance.waitForCommandCompletion()
        #         shrooly_instance.disconnect()
        #         print("Program terminated.")
        #         break
    elif args.subcommand == "disable_radios":
        logger.critical("subcommand not implemented, exiting")
        # shrooly_instance.disable_radios()
    elif args.subcommand == "start_cultivation":
        logger.critical("subcommand not implemented, exiting")
        # shrooly_instance.start_cultivation(args.file)
        # shrooly_instance.waitForCommandCompletion()
        # time.sleep(5)
        # resp = shrooly_instance.getStatus()
    elif args.subcommand == "stop_cultivation":
        logger.critical("subcommand not implemented, exiting")
        # shrooly_instance.stop_cultivation()
        # shrooly_instance.waitForCommandCompletion()
        # resp = shrooly_instance.getStatus()
    else:
        logger.warning("No command has been specified, disconnecting and exiting.")

    shrooly_instance.disconnect()

# if __name__ == '__main__':
#     main()