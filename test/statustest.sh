#!/bin/bash

# Name of the Python script to be executed
PYTHON_SCRIPT_FIRST="-m shrooly_cli --log-level DEBUG status"
PYTHON_SCRIPT="-m shrooly_cli --no-reset --log-level DEBUG status"
LOG_FILE="output.log"

> $LOG_FILE

python3 $PYTHON_SCRIPT_FIRST
# Loop to run the Python script 100 times
# Clear the log file before starting

# Loop to run the Python script 100 times
for ((i=1; i<=100; i++))
do
    echo "Attempt number: $i" | tee -a $LOG_FILE
    python3 $PYTHON_SCRIPT >> $LOG_FILE 2>&1
done