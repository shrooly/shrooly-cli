import time
import csv # csv writing
from datetime import datetime # getting current time for logging
from .shrooly import command_success

class log_to_file():
    shrooly_instance = None
    logger = None
    period = None
    
    def __init__(self, shrooly_instance, logger, period=10):
        self.shrooly_instance = shrooly_instance
        self.logger = logger
        self.period = period

    def start(self):
        period = 10

        success, response = self.shrooly_instance.updateStatus()
        
        if success == command_success.OK:
            self.logger.info("[LOGGER] Starting logging to file")
        else:
            self.logger.error("[LOGGER] Error during update! Couldn't start logging to file, exiting..")
            return
        
        success = self.shrooly_instance.set_humidifier(1)
        
        if success == command_success.OK:
            self.logger.info("[LOGGER] Humidifier turned on!")
        else:
            self.logger.error("[LOGGER] Error during humidifier turn on! exiting..")
            return
        
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%S')
        csv_file = "log-" + response['System']['MAC_address'] + "-" + timestamp + ".csv"
        field_names = ['Timestamp', 'Temperature', 'Humidity', 'Input_voltage', 'Fan duty', 'Fan speed', 'Humidiifer', 'Water level']
        first_line = "[LOGGER] Registering the following fields: "
        first_line += ",".join(field_names)
        self.logger.info(first_line)
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

                    success, response = self.shrooly_instance.updateStatus()
                    
                    if success == command_success.OK:         
                        writer.writerow(
                            {
                                'Timestamp': timestamp, 
                                'Temperature': response["Environment"]["Temperature"],
                                'Input_voltage': response["System"]["Input_voltage"],
                                'Humidity': response["Environment"]["Humidity"],
                                'Fan duty': response["Environment"]["Fan_duty"],
                                'Fan speed': response["Environment"]["Fan_speed"],
                                'Humidiifer': response["Environment"]["Humidifier"],
                                'Water level': response["Environment"]["Water_level"],
                                })
                        self.logger.info(f"[LOGGER] {timestamp}, {response['Environment']['Temperature']}, {response['Environment']['Humidity']}, {response['System']['Input_voltage']}, {response['Environment']['Fan_duty']}, {response['Environment']['Fan_speed']}, {response['Environment']['Humidifier']}, {response['Environment']['Water_level']}")
                    else:
                        self.logger.error("[LOGGER] Error during update! Couldn't write CSV")
                
                time.sleep(period)
            except Exception as e:
                self.logger.error("[LOGGER] Error: " + str(e))
            except KeyboardInterrupt:
                self.logger.info("[LOGGER] Program terminated.")
                break