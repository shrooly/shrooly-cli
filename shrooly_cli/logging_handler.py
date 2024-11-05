class logging_level:
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

class logging_handler:
    def __init__(self) -> None:
        self.ext_log_pipe = None
        self.log_level = logging_level.INFO
        self.prefix = ""

    def setLevel(self, log_level):
        if self.ext_log_pipe is not None:
            self.ext_log_pipe.setLevel(log_level)
        self.log_level = log_level
    
    def debug(self, message):
        if self.ext_log_pipe != None:
            self.ext_log_pipe.debug(self.prefix + message)
        elif self.log_level <=10:
            print(self.prefix + "[DEBUG]" + message)

    def info(self, message):
        if self.ext_log_pipe != None:
            self.ext_log_pipe.info(self.prefix + message)
        elif self.log_level <=20:
            print(self.prefix + "[INFO]" + message)

    def warning(self, message):
        if self.ext_log_pipe != None:
            self.ext_log_pipe.critical(self.prefix + message)
        elif self.log_level <=30:
            print(self.prefix + "[WARNING]" + message)

    def error(self, message):
        if self.ext_log_pipe != None:
            self.ext_log_pipe.critical(self.prefix + message)
        elif self.log_level <=40:
            print(self.prefix + "[ERROR]" + message)
    
    def critical(self, message):
        if self.ext_log_pipe != None:
            self.ext_log_pipe.critical(self.prefix + message)
        elif self.log_level <=50:
            print(self.prefix + "[CRITICAL]" +  message)