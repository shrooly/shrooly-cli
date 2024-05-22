class ANSI_code:
    def __init__(self, str_name, ANSI_string):
        self.ANSI_string = ANSI_string
        self.str_name = str_name

ANSI_Codes = [
    ANSI_code("ANSI_GREEN", "\x1b[0;32m"),
    ANSI_code("ANSI_RESET", "\x1b[0m"),
    ANSI_code("ANSI_NOISEPROBE", "\x1b[5n")]

max_length = max(len(code.ANSI_string) for code in ANSI_Codes)

# Print the result
print(f"The length of the longest ANSI string is: {max_length}")