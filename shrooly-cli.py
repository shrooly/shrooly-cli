import argparse
import logging # used for logging
import threading
import json
import fileconverter
import re
import csv
import time
from datetime import datetime
from pathlib import Path
from colorlog import ColoredFormatter
from serial_handler import serial_handler

class shrooly:    
    json_status = ""
    file_list = []
    prompt_enteres = False
    def __init__(self, logger):
        self.logger = logger
        self.serial_handler_instance = serial_handler(logger)

    def connect(self, port="/dev/ttyACM0", baud=921600, login="true"):
        connection_success = False
        self.logger.info("Connecting to Shrooly at: " + port + " @baud: " + str(baud))
        self.serial_handler_instance.connect(port, baud)
        self.logger.info("Successfully connected to serial!")
        
        #self.list_files()

        if(login=="true"):
            retry_counter = 0   
                
            while retry_counter < 5:
                self.logger.info("Sending CTRL+C to Shrooly-Terminal to enter interactive mode")
                self.serial_handler_instance.direct_write('\x03')
                self.logger.debug("CTRL+C sent directly")
                time.sleep(0.5)
                self.serial_handler_instance.direct_write('\r\n')
                self.logger.debug("Newline sent directly")
                time.sleep(0.5)
                
                if self.serial_handler_instance.prompt_received:
                    self.logger.info("Successfully entered interactive mode")
                    self.serial_handler_instance.direct_write('ping_rp wpt_power 1')
                    connection_success = True
                    return connection_success
                self.logger.info("Prompt wasn't received in 500 ms, retry no. " + str(retry_counter+1) + ". Waiting 2000 ms before retry")
                retry_counter += 1
                time.sleep(2)

            self.logger.critical("Couldn't connect in 5 tries, aborting.")
            self.serial_handler_instance.disconnect()
            return connection_success
        else:
            return True

    def commandInProgress(self):
        if self.serial_handler_instance.getQueueSize() > 0 or self.serial_handler_instance.getActiveElement() is not None:
            return True
        else:
            return False
    def waitForCommandCompletion(self):
        while True:
            if self.commandInProgress() == False:
                break

    def disconnect(self):
        self.serial_handler_instance.disconnect()

    def send_file(self, file_to_stream):
        self.logger.info("File transfer process has started!")
        #file_to_stream = "/home/pi/testfarm-v2/test.lua"
        file_name = Path(file_to_stream).name
        self.logger.debug("File name from path: " + file_name)
        file_content = ""
        
        self.logger.info("File to send: " + file_to_stream)
        
        try:
            with open(file_to_stream, 'r') as file:
                file_content = file.read()
            self.logger.info("File successfully opened")
        except:
            self.logger.error("Error while opening file, maybe it doesn't extist?")
            return

        self.logger.debug("File content: ")
        self.logger.debug(file_content)

        command = "fs_write"
        target_file_name = file_name
        max_line_length = 256
        
        chunks = fileconverter.string_to_comand_chunks([command, target_file_name], file_content, max_line_length)

        chunk_counter = 0
        chunk_count = len(chunks)
        self.logger.info("Command: " + command + ", target: " + target_file_name + ", chunk size: " + str(max_line_length) + " bytes, no. of chunks: " + str(chunk_count))

        for element in chunks:
            self.logger.debug("Adding chunk to queue: " + str(chunk_counter) + "/" + str(len(chunks)-1))
            self.logger.debug("Chunk content: " + element)
            if chunk_counter < chunk_count - 1:
                self.serial_handler_instance.add_to_write_queue(element + "\r\n", self.callback_acknowledgeChunk, [chunk_counter, chunk_count])
                chunk_counter = chunk_counter + 1
            else:
                self.serial_handler_instance.add_to_write_queue(element + "\r\n", self.callback_acknowledgeFinalChunk, [chunk_counter, chunk_count])
        
        self.logger.info("File chunks have been added to queue!")

    def delete_file(self, strInput):
        self.logger.info("Requesting file deletion: " + strInput)
        request_string = f"fs_delete {strInput}\r\n"
        self.serial_handler_instance.add_to_write_queue(request_string, self.callback_delete_file)
    
    def read_file(self, strInput):
        self.logger.info("Requesting read of file: " + strInput)
        request_string = f"fs_read {strInput}\r\n"
        self.serial_handler_instance.add_to_write_queue(request_string, self.callback_open_file)

    def list_files(self):
        self.logger.info("Requesting list of files..")
        self.serial_handler_instance.add_to_write_queue("fs_list\r\n", self.callback_list_files)

    def getStatus(self, format="PARSED"):
        self.logger.info("Requesting status of device..")
        self.serial_handler_instance.add_to_write_queue("dump\r\n", self.callback_getStatus, format)
        self.waitForCommandCompletion()
        return self.json_status
    
    def disable_radios(self):
        self.logger.info("Disabling Radios")
        self.serial_handler_instance.add_to_write_queue("disable_radios\r\n", self.callback_disable_radios)

    def turn_on_humidifer(self):
        self.logger.info("Turning on humidifer")
        self.serial_handler_instance.add_to_write_queue("ping_rp wpt_power 1\r\n", self.callback_turn_on_humidifer)

    def start_cultivation(self, file):
        self.logger.info("Requesting cultivation start: " + file)
        request_string = f"start_cultivation file {file}\r\n"
        self.serial_handler_instance.add_to_write_queue(request_string, self.callback_start_cultivation)

    def stop_cultivation(self):
        self.logger.info("Stopping cultivation")
        self.serial_handler_instance.add_to_write_queue("stop_cultivation\r\n", self.callback_stop_cultivation)

    def callback_list_files(self, strInput, metadata):
        strInput_parsed = strInput.split('\n')
        files_found = 0
        self.file_list = []
        for line in strInput_parsed:
            filename_pattern = "[a-zA-Z0-9]+\.[a-zA-Z0-9]+$"
            filename_match = re.search(filename_pattern, line)

            if filename_match:
                self.logger.info("> " + line)
                files_found += 1
                self.file_list.append(line)
            
        self.logger.info("End of list, number of files found: " + str(files_found))
    
    def callback_delete_file(self, strInput, metadata):
        strInput_parsed = strInput.split('\n')
        self.logger.info("Response: " + strInput_parsed[0])
    
    def callback_open_file(self, strInput, metadata):
        strInput_parsed = strInput.split('\n')
        lines_found = 0
        for line in strInput_parsed:
            print(line)
            lines_found = lines_found + 1

        self.logger.info("End of file, number of lines found: " + str(lines_found))
        
    def callback_acknowledgeChunk(self, strInput, metadata):
        current = metadata[0]+1
        all = metadata[1]
        self.logger.info("Chunk transferred ACK from device (" + str(current) + "/" + str(all) + ")")

    def callback_acknowledgeFinalChunk(self, strInput, metadata):
        current = metadata[0]+1
        all = metadata[1]
        self.logger.info("File transfer completed: (" + str(current) + "/" + str(all) + ")")

    def callback_getStatus(self, strInput, metadata):
        if metadata == "PARSED":
            #print("SHIT: " + strInput)
            json_resp = json.loads(strInput)
            self.parse_json(json_resp)
        else:
            #self.logger.info("JSON response: " + strInput)
            pass
        
        self.json_status = strInput

    def callback_disable_radios(self, strInput, metadata):
        self.logger.info("Response: " + strInput)

    def callback_turn_on_humidifer(self, strInput, metadata):
        self.logger.info("Response: " + strInput)

    def callback_stop_cultivation(self, strInput, metadata):
        self.logger.info("Response: " + strInput)

    def callback_start_cultivation(self, strInput, metadata):
        self.logger.info("Response: " + strInput)

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

    def file_exists(self, strInput):
        exists = False
        for file in self.file_list:
            if file == strInput:
                exists = True
        
        return exists

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

    parser = argparse.ArgumentParser(description="Shrooly API wrapper")
    subparsers = parser.add_subparsers(dest='subcommand')
    parser_send_file = subparsers.add_parser('send_file', help='send a file')
    parser_send_file.add_argument('--file', help='name of the file to send', required=True)
    parser_delete_file = subparsers.add_parser('delete_file', help='delete a file')
    parser_delete_file.add_argument('--file', help='name of the file to delete', required=True)
    parser_read_file = subparsers.add_parser('read_file', help='read a file')
    parser_read_file.add_argument('--file', help='name of the file to open', required=True)
    parser_start_cultivation = subparsers.add_parser('start_cultivation', help='start a cultivation')
    parser_start_cultivation.add_argument('--file', help='name of the lua script (stored on Shrooly) to start', required=True)
    subparsers.add_parser('stop_cultivation', help='stop cultivation')
    subparsers.add_parser('logger', help='logging')
    parser_get_status = subparsers.add_parser('get_status', help='get status of Shrooly')
    parser_get_status.add_argument('--format', choices=["JSON", "PARSED"], help='output format', default="PARSED", required=False)

    subparsers.add_parser('list_files', help='list files on Shrooly')
    subparsers.add_parser('disable_rf', help='disable Bluetooth and WiFi radios')
    
    parser.add_argument("--serial-port", default="/dev/ttyACM0", help="set the Shrooly's serial-port")
    parser.add_argument("--login", default="true", help="enter interactive terminal or not")
    parser.add_argument("--serial-baud", default="921600", help="set the Shrooly's serial-port baud")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING"], default="INFO", help="Set the logging level (DEBUG, INFO, WARNING)")

    args = parser.parse_args()

    #if args.subcommand == 'send_file':
    #    print(f"Sending file at {args.file}")

    logger.setLevel(args.log_level)
    logger.info("Shrooly CLI wrapper started")

    shrooly_instance = shrooly(logger)
    shrooly_instance.connect(args.serial_port, args.serial_baud, args.login)

    if args.subcommand == "send_file":
        shrooly_instance.send_file(args.file)
        shrooly_instance.waitForCommandCompletion()
        shrooly_instance.list_files()
    if args.subcommand == "delete_file":
        shrooly_instance.delete_file(args.file)
    elif args.subcommand == "list_files":
        shrooly_instance.list_files()
    elif args.subcommand == "read_file":
        shrooly_instance.read_file(args.file)
    elif args.subcommand == "get_status":
        resp = shrooly_instance.getStatus(args.format)
        print(resp)
    elif args.subcommand == "logger":
        shrooly_instance.turn_on_humidifer()
        shrooly_instance.waitForCommandCompletion()
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        csv_file = "log-" + timestamp + ".csv"
        field_names = ['Timestamp', 'Temperature', 'Humidity', 'VBUS', 'Fan duty', 'Fan speed', 'Humidiifer', 'Water level']

        # Create the CSV file and write the header
        with open(csv_file, mode='w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=field_names)
            writer.writeheader()

        # Infinite loop to append a line every second
        while True:
            try:
                # Open the CSV file in append mode
                with open(csv_file, mode='a', newline='') as file:
                    writer = csv.DictWriter(file, fieldnames=field_names)
                    
                    # Get the current timestamp
                    timestamp = datetime.now().isoformat()

                    
                    # Generate some example data (you can replace this with your own data)
                    resp = shrooly_instance.getStatus("JSON")
                    print(type(resp))
                    print(resp)
                    resp = json.loads(resp)
                    print(resp)
                    
                    
                    # Write a new row to the CSV file
                    writer.writerow(
                        {
                            'Timestamp': timestamp, 
                            'Temperature': resp["Monitoring"]["Temperature"],
                            'Humidity': resp["Monitoring"]["Humidity"],
                            'VBUS': resp["Debug"]["VBUS"],
                            'Fan duty': resp["Debug"]["Fan duty"],
                            'Fan speed': resp["Debug"]["Fan speed"],
                            'Humidiifer': resp["Debug"]["Humidifier"],
                            'Water level': resp["Monitoring"]["Water level"],
                            })
                
                # Wait for 10 second before appending the next line
                time.sleep(10)
            except Exception as e:
                pass
            except KeyboardInterrupt:
                shrooly_instance.waitForCommandCompletion()
                shrooly_instance.disconnect()
                print("Program terminated.")
                break
    elif args.subcommand == "disable_radios":
        shrooly_instance.disable_radios()
    elif args.subcommand == "start_cultivation":
        shrooly_instance.start_cultivation(args.file)
        shrooly_instance.waitForCommandCompletion()
        time.sleep(5)
        resp = shrooly_instance.getStatus()
    elif args.subcommand == "stop_cultivation":
        shrooly_instance.stop_cultivation()
        shrooly_instance.waitForCommandCompletion()
        resp = shrooly_instance.getStatus()

    shrooly_instance.waitForCommandCompletion()
    shrooly_instance.disconnect()