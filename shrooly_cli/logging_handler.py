class logging_level:
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

class logging_handler:
    ext_log_pipe = None
    log_level = logging_level.INFO

    def setLevel(self, log_level):
        if self.ext_log_pipe is not None:
            self.ext_log_pipe.setLevel(log_level)
        self.log_level = log_level
    
    def debug(self, message):
        if self.ext_log_pipe != None:
            self.ext_log_pipe.debug(message)
        elif self.log_level <=10:
            print("[DEBUG]" + message)

    def info(self, message):
        if self.ext_log_pipe != None:
            self.ext_log_pipe.info(message)
        elif self.log_level <=20:
            print("[INFO]" + message)

    def warning(self, message):
        if self.ext_log_pipe != None:
            self.ext_log_pipe.critical(message)
        elif self.log_level <=30:
            print("[WARNING]" + message)

    def error(self, message):
        if self.ext_log_pipe != None:
            self.ext_log_pipe.critical(message)
        elif self.log_level <=40:
            print("[ERROR]" + message)
    
    def critical(self, message):
        if self.ext_log_pipe != None:
            self.ext_log_pipe.critical(message)
        elif self.log_level <=50:
            print("[CRITICAL]" + message)