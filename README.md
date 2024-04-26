# shrooly-cli

Install: pip3 install -e .
run: python3 -m shrooly_cli

usage: shrooly_cli [-h] [--serial-port SERIAL_PORT] [--serial-baud SERIAL_BAUD] [--log-level {DEBUG,INFO,WARNING}] [--no-reset] [--serial-log SERIAL_LOG] [--no-fw-check]
                   {send_file,delete_file,read_file,save_file,set_humidifier,start_script,stop_script,set_current_time,get_current_time,logger,status,list_files,reset,disable_bt}
