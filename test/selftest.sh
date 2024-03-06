RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
RESET='\033[0m'

if [ -d "logs" ]; then
    echo "logs folder already exist, deleting it"
    rm -rf logs
fi

echo "creating logs folder"
mkdir logs

rm hex_stream.txt

echo -e "${YELLOW}>>> Testing status <<< ${RESET}"
python3 -m shrooly_cli --log-level INFO --no-fw-check --serial-log logs/log_0_status.txt status
echo -e "${YELLOW}>>> Testing get_current_time <<< ${RESET}"
python3 -m shrooly_cli --log-level INFO --no-reset --no-fw-check --serial-log logs/log_1_get_current_time.txt get_current_time
echo -e "${YELLOW}>>> Testing set_current_time <<< ${RESET}"
python3 -m shrooly_cli --log-level INFO --no-reset --no-fw-check --serial-log logs/log_2_set_current_time.txt set_current_time
echo -e "${YELLOW}>>> Testing send_file <<< ${RESET}"
rm recipe_copy.lua
cp recipe.lua recipe_copy.lua
python3 -m shrooly_cli --log-level INFO --no-reset --no-fw-check --serial-log logs/log_3_send_file.txt send_file --file recipe_copy.lua
rm recipe_copy.lua
echo -e "${YELLOW}>>> Testing save_file <<< ${RESET}"
python3 -m shrooly_cli --log-level INFO --no-reset --no-fw-check --serial-log logs/log_4_save_file.txt save_file --file recipe_copy.lua
echo -e "${YELLOW}>>> Testing delete_file <<< ${RESET}"
python3 -m shrooly_cli --log-level INFO --no-reset --no-fw-check --serial-log logs/log_5_delete_file.txt delete_file --file recipe_copy.lua
echo -e "${YELLOW}>>> Testing list_files <<< ${RESET}"
python3 -m shrooly_cli --log-level INFO --no-reset --no-fw-check --serial-log logs/log_6_list_files.txt list_files