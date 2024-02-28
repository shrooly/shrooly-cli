import argparse

def string_to_comand_chunks(offset, content, maxlinelen):
    # payloadcount must be an even number because one char is represented by two hex digits
    payloadcount = maxlinelen - offset - (maxlinelen - offset)%2
    # print("offset: " + str(offset))
    # print("payload length: " + str(payloadcount))
    # print("content length: " + str(len(content)))
    # Buffer to store chunks
    array = []
    buffer = ""
    index = 0
    
    while index < len(content):
        char = content[index]
        index += 1

        hex_value = format(ord(char), '02x')
        buffer += hex_value

        if len(buffer) >= payloadcount:
            #print("payload length limit reached, index: " + str(index) + ", appending: " + buffer)
            array.append(buffer)
            buffer = ""
    
    #print("Exited chunk making loop")
    if buffer:
        #print("Remaining stuff: " + buffer) 
        array.append(buffer)

    return array

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Stream a file to a target device over a serial port.')
    parser.add_argument('target_device', help='The target device (e.g., "/dev/ttyACM0")')
    parser.add_argument('target_fname', help='The filename on the device')
    parser.add_argument('file_to_stream', help='The file to be streamed')

    args = parser.parse_args()

    # print(args.target_device)
    # print(args.target_fname)
    # print(args.file_to_stream)

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