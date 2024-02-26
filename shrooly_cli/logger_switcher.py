class logging_level:
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

class logger_switcher:
    ext_log_pipe = None
    level = logging_level.INFO

    def setLevel(self, level):
        if self.ext_log_pipe != None:
            self.ext_log_pipe.setLevel(level)
        self.level = level
    
    def debug(self, message):
        if self.ext_log_pipe != None:
            self.ext_log_pipe.debug(message)
        elif self.level <=10:
            print("[DEBUG]" + message)

    def info(self, message):
        if self.ext_log_pipe != None:
            self.ext_log_pipe.info(message)
        elif self.level <=20:
            print("[INFO]" + message)

    def warning(self, message):
        if self.ext_log_pipe != None:
            self.ext_log_pipe.critical(message)
        elif self.level <=30:
            print("[WARNING]" + message)

    def error(self, message):
        if self.ext_log_pipe != None:
            self.ext_log_pipe.critical(message)
        elif self.level <=40:
            print("[ERROR]" + message)
    
    def critical(self, message):
        if self.ext_log_pipe != None:
            self.ext_log_pipe.critical(message)
        elif self.level <=50:
            print("[CRITICAL]" + message)