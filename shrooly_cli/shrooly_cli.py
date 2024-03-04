import sys # used for detecting host OS
import argparse # argument parsing
import json
import re # regex
import csv # csv writing
import logging # logging
import time
import signal # for handling Ctrl-C exit preoperly
from colorlog import ColoredFormatter
from datetime import datetime # getting current time for logging

# local dependencies
from .shrooly import shrooly, command_success
from .logger_switcher import logger_switcher, logging_level
from .constants import MIN_FW_VERSION

def compare_calver_versions(version1, version2):
    """
    Compare two calendar versions (CalVer) strings
    Returns:
    -1 if version1 < version2
     0 if version1 == version2
     1 if version1 > version2
    """
    def parse_calver(version):
        # Remove 'v' prefix and split the string by '.'
        version = version.lstrip('v')
        year, month_patch = version.split('.', 1)
        month, patch = month_patch.split('-', 1)
        return int(year), int(month), int(patch)

    year1, month1, patch1 = parse_calver(version1)
    year2, month2, patch2 = parse_calver(version2)

    if year1 != year2:
        return -1 if year1 < year2 else 1
    if month1 != month2:
        return -1 if month1 < month2 else 1
    if patch1 != patch2:
        return -1 if patch1 < patch2 else 1
    return 0

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
    parser_start_cultivation = subparsers.add_parser('start_script', help='start a script (like a cultivation)')
    parser_start_cultivation.add_argument('--file', help='name of the lua script (stored on Shrooly) to start', required=True)
    subparsers.add_parser('stop_script', help='stop a script (like a cultivation)')
    subparsers.add_parser('set_current_time', help='set the current time')
    parser_logger = subparsers.add_parser('logger', help='start the logging feature (dev)')
    parser_logger.add_argument('--period', help='logger period in seconds')
    subparsers.add_parser('status', help='get status of Shrooly')
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
    
    logger.info("[CLI] Application has started!")

    shrooly_instance = shrooly(logger)
    
    success = shrooly_instance.connect(args.serial_port, args.serial_baud, args.no_reset)
    
    if success == False:
        logger.critical("[CLI] Error during connection, exiting..")
        shrooly_instance.disconnect()
        sys.exit()
    
    success, resp = shrooly_instance.updateStatus()
        
    if success:
        logger.info("[CLI] Status updated")
        if args.no_reset == False:
            if compare_calver_versions(MIN_FW_VERSION, shrooly_instance.status['Boot-Firmware']['version']) <= 0:
                logger.info("[CLI] Firmware version is higher than the required minimum")
            else:
                logger.error("[CLI] Firmware version is LOWER than the required minimum: " + MIN_FW_VERSION)
        else:
            logger.info("[CLI] no-reset flag is set, couldn't check if satisifies minimum fw version of: " + MIN_FW_VERSION)
    else:
        logger.error("[CLI] Error during status update command, continuing..")

    if args.subcommand == "list_files":
        success, files = shrooly_instance.list_files()
        if success is command_success.OK:
            logger.info("Found " + str(len(files)) + " file(s):")
            for file in files:
                logger.info(file)
        else:
            logger.error("Error during listing of files..")
    elif args.subcommand == "read_file":
        success, resp = shrooly_instance.read_file(args.file)
        if success is command_success.OK:
            logger.info("[CLI] File read success")
            print(resp)
        else:
            logger.error("Error during reading of file, maybe it doesn't exist?")
    elif args.subcommand == "send_file":
        success = shrooly_instance.send_file(args.file)

        if success == command_success.OK:
            logger.info("[CLI] File transfer success!")
        else:
            logger.error("[CLI] Error during file transfer, exiting..")
    elif args.subcommand == "delete_file":
        resp = shrooly_instance.delete_file(args.file)
        
        if resp == command_success.OK:
            logger.info("[CLI] File delete success!")
        else:
            logger.error("[CLI] Error during file delete (maybe it doesn't exist on Shrooly?), exiting..")
    elif args.subcommand == "save_file":
        success, resp = shrooly_instance.read_file(args.file)
        if success is command_success.OK:
            logger.info("[CLI] File save success")
            with open(args.file, "w") as file:
                file.write(resp)
        else:
            logger.error("Error during reading of file, maybe it doesn't exist?")
    elif args.subcommand == "status":
        json_converted = json.dumps(shrooly.status, indent=4)
        print(json_converted)
    elif args.subcommand == "logger":
        period = 10
        if args.period is not None and isinstance(args.period, int):
            period = args.period
        #shrooly_instance.turn_on_humidifer()
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        csv_file = "log-" + timestamp + ".csv"
        field_names = ['Timestamp', 'Temperature', 'Humidity', 'VBUS', 'Fan duty', 'Fan speed', 'Humidiifer', 'Water level']

        first_line = ",".join(field_names)
        logger.info(first_line)
        # Create the CSV file and write the header
        with open(csv_file, mode='w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=field_names)
            writer.writeheader()

        # Infinite loop to append a line every second
        while True:
            try:
                with open(csv_file, mode='a', newline='') as file:
                    writer = csv.DictWriter(file, fieldnames=field_names)
                    
                    # Get the current timestamp
                    timestamp = datetime.now().isoformat()

                    success, response = shrooly_instance.updateStatus()
                    
                    if success == command_success.OK:         
                        writer.writerow(
                            {
                                'Timestamp': timestamp, 
                                'Temperature': response["Environment"]["Temperature"],
                                'Humidity': response["Environment"]["Humidity"],
                                'Fan duty': response["Environment"]["Fan_duty"],
                                'Fan speed': response["Environment"]["Fan_speed"],
                                'Humidiifer': response["Environment"]["Humidifier"],
                                'Water level': response["Environment"]["Water_level"],
                                })
                        logger.info(f"{timestamp}, {response['Environment']['Temperature']}, {response['Environment']['Humidity']}, {response['Environment']['Fan_duty']}, {response['Environment']['Fan_speed']}, {response['Environment']['Humidifier']}, {response['Environment']['Water_level']}")
                    else:
                        logger.error("Error during update! Couldn't write CSV")
                
                time.sleep(period)
            except Exception as e:
                logger.error("Error: " + str(e))
            except KeyboardInterrupt:
                shrooly_instance.disconnect()
                logger.info("Program terminated.")
                break
    elif args.subcommand == "disable_bt":
        success = shrooly_instance.disable_bt()

        if success == command_success.OK:
            logger.info("[CLI] Bluetooth disable success")
        else:
            logger.error("[CLI] Error during bluetooth disable, exiting..")
    elif args.subcommand == "set_current_time":
        current_time = datetime.now()
        formatted_time = current_time.strftime("%Y-%m-%dT%H:%M:%S")
        request_success = shrooly_instance.set_datetime(formatted_time)
        check_success = shrooly_instance.updateStatus()
        if request_success and check_success:
            logger.info("[CLI] Time read from device: " + shrooly_instance.status['System']['Datetime'])
            time_from_device = datetime.fromisoformat(shrooly_instance.status['System']['Datetime'])
            if abs((time_from_device-current_time).total_seconds()) < 5:
                logger.info("[CLI] Time setting OK!")
            else:
                logger.error("[CLI] The read time doesn't match the sent one")
        else:
            logger.error("[CLI] Error during time update")
    elif args.subcommand == "start_script":
        success = shrooly_instance.start_script(args.file)

        if success == command_success.OK:
            logger.info("[CLI] Script start success!")
        else:
            logger.error("[CLI] Error during script start, exiting..")

        success = shrooly_instance.updateStatus()

        if success:
            print(json.dumps(shrooly_instance.status['Program status'], indent=4))
    elif args.subcommand == "stop_script":
        success = shrooly_instance.stop_script()

        if success == command_success.OK:
            logger.info("[CLI] Script stop success!")
        else:
            logger.error("[CLI] Error during script stop, exiting..")

        success = shrooly_instance.updateStatus()

        if success:
            print(json.dumps(shrooly_instance.status['Program status'], indent=4))
    else:
        logger.warning("No command has been specified, disconnecting and exiting.")

    shrooly_instance.disconnect()

# if __name__ == '__main__':
#     main()