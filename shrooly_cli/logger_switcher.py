class logging_level:
    debug = 10
    info = 20
    warning = 30
    error = 40
    critical = 50

class logger_switcher:
    ext_log_pipe = None
    level = 10

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