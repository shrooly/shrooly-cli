import serial
import time
import argparse

def string_to_comand_chunks(args, content, maxlinelen):
    command = ""
    for argpart in args:
        command += argpart
        command += " "

    #print(maxlinelen)
    #print(len(command))
    # payloadcount must be an even number because one char is represented by two hex digits
    payloadcount = maxlinelen - len(command) - (maxlinelen - len(command))%2
    #print("No of payloads: " + str(payloadcount))

    # Buffer to store 64-byte chunks
    array = []
    buffer = ""

    index = 0
    while index < len(content):
        char = content[index]
        index += 1

        hex_value = format(ord(char), '02x')
        buffer += hex_value

        if len(buffer) == payloadcount:
            data = f"{command}{buffer}"
            array.append(data)
            buffer = ""

    # Stream any remaining characters
    data = f"{command}{buffer}"
    array.append(data)
    buffer = ""

    return array

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Stream a file to a target device over a serial port.')
    parser.add_argument('target_device', help='The target device (e.g., "/dev/ttyACM0")')
    parser.add_argument('target_fname', help='The filename on the device')
    parser.add_argument('file_to_stream', help='The file to be streamed')

    args = parser.parse_args()

    print(args.target_device)
    print(args.target_fname)
    print(args.file_to_stream)

    file_content = ""
    with open(args.file_to_stream, 'r') as file:
        file_content = file.read()

    print(file_content)

    command = "fs_write"
    target_file_name = "foo.lua"
    max_line_length = 64

    chunks = string_to_comand_chunks([command, target_file_name], file_content, max_line_length)

    for element in chunks:
        print(element)
    
    print("\nStreaming complete.")