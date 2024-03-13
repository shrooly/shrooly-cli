from shrooly_cli import shrooly
import json

shrooly_instance = shrooly()
shrooly_instance.connect()
shrooly_instance.enterTerminal()
success, resp_json = shrooly_instance.updateStatus()
resp_formatted = json.dumps(resp_json, indent=4)
print(resp_formatted)
shrooly_instance.disconnect()