-- DarkCounter OBS Studio Lua Script
-- Monitors a local death/kill counter output file (e.g., values/deaths)
-- and notifies the TwitchTTS server when the count increases.

local obs = obslua

-- Script Settings & State
local server_url = "http://localhost:5000"
local channel = ""
local counter_file = "values/deaths"
local poll_interval = 1.0
local api_token = ""
local enable_script = true

local last_count = -1

-- Parse integer counter value from a text file
local function read_counter_file(filepath)
    if not filepath or filepath == "" then return -1 end
    local file = io.open(filepath, "r")
    if not file then return -1 end
    local content = file:read("*a")
    file:close()

    if not content or content == "" then return -1 end

    local numbers = {}
    for num in string.gmatch(content, "%d+") do
        table.insert(numbers, num)
    end

    if #numbers > 0 then
        return tonumber(numbers[#numbers])
    end
    return -1
end

-- Send HTTP POST to TwitchTTS /api/counter
local function notify_server(count, increment)
    if not server_url or server_url == "" then return end
    
    local endpoint = string.gsub(server_url, "/+$", "") .. "/api/counter"
    local payload
    if channel and channel ~= "" then
        payload = string.format('{"count": %d, "increment": %d, "trigger_tts": true, "channel": "%s"}', count, increment, channel)
    else
        payload = string.format('{"count": %d, "increment": %d, "trigger_tts": true}', count, increment)
    end

    local is_windows = package.config:sub(1,1) == '\\'
    local cmd

    if is_windows then
        local token_header = ""
        if api_token and api_token ~= "" then
            token_header = string.format(' -H "X-Counter-Token: %s" -H "Authorization: Bearer %s"', api_token, api_token)
        end
        local escaped_payload = payload:gsub('"', '\\"')
        cmd = string.format('curl.exe -s -X POST "%s" -H "Content-Type: application/json"%s -d "%s"', endpoint, token_header, escaped_payload)
    else
        local token_header = ""
        if api_token and api_token ~= "" then
            token_header = string.format(" -H 'X-Counter-Token: %s' -H 'Authorization: Bearer %s'", api_token, api_token)
        end
        cmd = string.format("curl -s -X POST '%s' -H 'Content-Type: application/json'%s -d '%s' &", endpoint, token_header, payload)
    end

    os.execute(cmd)
    obs.script_log(obs.LOG_INFO, string.format("[DarkCounter OBS] Sent count #%d to TwitchTTS server", count))
end

-- Timer callback function
local function poll_tick()
    if not enable_script then return end
    if not counter_file or counter_file == "" then return end

    local current_count = read_counter_file(counter_file)
    if current_count >= 0 then
        if last_count >= 0 and current_count > last_count then
            local delta = current_count - last_count
            obs.script_log(obs.LOG_INFO, string.format("[DarkCounter OBS] Counter INCREASE: %d -> %d (+%d)", last_count, current_count, delta))
            notify_server(current_count, delta)
        end
        last_count = current_count
    end
end

-- OBS Script Properties UI Definition
function script_properties()
    local props = obs.obs_properties_create()
    obs.obs_properties_add_bool(props, "enable_script", "Enable File Watcher")
    obs.obs_properties_add_text(props, "server_url", "TwitchTTS Server URL", obs.OBS_TEXT_DEFAULT)
    obs.obs_properties_add_text(props, "channel", "Target Channel (Optional)", obs.OBS_TEXT_DEFAULT)
    obs.obs_properties_add_path(props, "counter_file", "Counter File Path (e.g. values/deaths)", obs.OBS_PATH_FILE, "Text Files (*.txt);;All Files (*)", nil)
    obs.obs_properties_add_float(props, "poll_interval", "Poll Interval (Seconds)", 0.2, 10.0, 0.5)
    obs.obs_properties_add_text(props, "api_token", "API Token (Optional)", obs.OBS_TEXT_PASSWORD)

    obs.obs_properties_add_button(props, "test_button", "🧪 Test Bible Verse TTS", function()
        local test_val = last_count >= 0 and last_count or 1
        notify_server(test_val, 1)
        return true
    end)

    return props
end

-- OBS Script Defaults
function script_defaults(settings)
    obs.obs_data_set_default_bool(settings, "enable_script", true)
    obs.obs_data_set_default_string(settings, "server_url", "http://localhost:5000")
    obs.obs_data_set_default_string(settings, "channel", "")
    obs.obs_data_set_default_string(settings, "counter_file", "values/deaths")
    obs.obs_data_set_default_double(settings, "poll_interval", 1.0)
    obs.obs_data_set_default_string(settings, "api_token", "")
end

-- OBS Script Update Callback
function script_update(settings)
    enable_script = obs.obs_data_get_bool(settings, "enable_script")
    server_url = obs.obs_data_get_string(settings, "server_url")
    channel = obs.obs_data_get_string(settings, "channel")
    counter_file = obs.obs_data_get_string(settings, "counter_file")
    poll_interval = obs.obs_data_get_double(settings, "poll_interval")
    api_token = obs.obs_data_get_string(settings, "api_token")

    obs.timer_remove(poll_tick)
    if enable_script then
        local interval_ms = math.max(200, math.floor((poll_interval or 1.0) * 1000))
        obs.timer_add(poll_tick, interval_ms)
        obs.script_log(obs.LOG_INFO, string.format("[DarkCounter OBS] Monitoring '%s' every %dms", counter_file, interval_ms))
    end
end

-- OBS Script Description
function script_description()
    return "⚔️ DarkCounter OBS Studio Integration\n\nMonitors your local Dark Souls counter file (e.g. values/deaths) and notifies your TwitchTTS server when counts increase to trigger Bible verse TTS playback."
end

-- OBS Script Load
function script_load(settings)
    script_update(settings)
end
