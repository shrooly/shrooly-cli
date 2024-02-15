-- File: General.lua
-- This LUA recipe turn on the fun for fan_cycle_duration[0] seconds and turns it off for fan_cycle_duration[1]
-- White LED (intensity is 5%) is controlled is switched on between sunrise and sunrise+photoperiod.
-- Name of the recipe is disclosed (muhsroomName)

println('LUA_WORKER: Starting execution of: General.lua')

--Pod name and version information reported--
podID    = "190"
podName  = "bb"
recipeVersion = 1
luaAPIVersion = 3
set_recipe_info(podID, recipeVersion, podName)
---------------------------------------------

-----------------Constants-------------------
white_led_brightness             = 100
photoperiod                      = 43200
fan_cycle_durations              = {30, 60}  -- Unequal cycle durations in seconds, format: {on_seconds, off_seconds}
target_rh                        = 75
fan_speed                        = 100
---------------------------------------------

-----------------Variables-------------------
sunrise                          = 28800
---------------------------------------------

-----------------Functions-------------------
function alternate(current_time, cycle_duration)
    elapsed_time = current_time - start_epoch
    cycle_count = math.floor(elapsed_time / cycle_duration)
    
    if((cycle_count % 2) == 1) 
    then
        return 1
    else
        return 0
    end
end

function control_lighting(current_time)
    local currentHour = tonumber(os.date("%H", current_time))
    local currentMinute = tonumber(os.date("%M", current_time))
    local currentSecond = tonumber(os.date("%S", current_time))

    local aggSeconds = currentSecond + 60*currentMinute + currentHour*3600

    print("LUA_WHITE_LED_CONTROLLER: current time in seconds: ", aggSeconds, ", sunrise: ", sunrise, ", photoperiod: ", photoperiod, ". Result: ")
    if ((aggSeconds >= sunrise) and (aggSeconds < sunrise+photoperiod)) 
    then
        println('0N!')
        set_white_led_pwm(white_led_brightness)
    else
        println('OFF!')
        set_white_led_pwm(0)
    end
    
    return
end

function control_fan(start_time, current_time)
    local elapsed_time = current_time - start_time
    local total_duration = 0
    local active_cycle = 1
    local state = 0

    while elapsed_time > total_duration + fan_cycle_durations[active_cycle] do
        total_duration = total_duration + fan_cycle_durations[active_cycle]
        active_cycle = (active_cycle % #fan_cycle_durations) + 1
    end

    print("LUA_FAN_CONTROLLER: elapsed_time: ", elapsed_time, ". Result: ")
    
    state = active_cycle % 2  -- Toggle the state based on active_cycle
    if state == 1
    then
        println('0N!')
        set_fan_pwm(fan_speed)
    else
        println('0FF!')
        set_fan_pwm(0)
    end
    return state
end

start_epoch                = program_startepoch()
local current_epoch        = get_time_epoch() 

println('LUA_WORKER: Running..')
set_humidifier(1)
control_lighting(current_epoch)
control_fan(start_epoch, current_epoch)
println('LUA_WORKER: Cultivation program ended, next run in 2000 ms')
