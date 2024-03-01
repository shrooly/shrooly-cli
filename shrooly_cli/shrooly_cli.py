import sys # used for detecting host OS
import argparse # argument parsing
import json
import re # regex
import csv # csv writing
import logging # logging
import signal # for handling Ctrl-C exit preoperly
from colorlog import ColoredFormatter
from datetime import datetime # getting current time for logging

# local dependencies
from .shrooly import shrooly, command_success
from .logger_switcher import logger_switcher, logging_level

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
        success = shrooly_instance.send_file(args.file)

        if success == command_success.OK:
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
    elif args.subcommand == "status":
        success = shrooly_instance.connect(args.serial_port, args.serial_baud, args.no_reset)
        
        if success == False:
            logger.critical("[CLI] Error during connection, exiting..")
            shrooly_instance.disconnect()
            sys.exit()
        
        success, resp = shrooly_instance.updateStatus(args.format)
        
        if success:
            logger.info("Status updated")
            json_converted = json.dumps(shrooly.status, indent=4)
            print(json_converted)
        #yaml_out = yaml.dump(shrooly_instance.status)
        #print(yaml_out)
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