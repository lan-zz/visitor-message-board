module("luci.controller.visitor-board", package.seeall)

function index()
	entry({"admin", "services", "visitor-board"}, alias("admin", "services", "visitor-board", "status"), _("访客留言板"), 60)
	entry({"admin", "services", "visitor-board", "status"}, template("visitor-board/status"), _("状态管理"), 1)
	entry({"admin", "services", "visitor-board", "action"}, call("container_action"), nil).leaf = true
	entry({"admin", "services", "visitor-board", "get_status"}, call("get_status"), nil)
	entry({"admin", "services", "visitor-board", "get_logs"}, call("get_logs"), nil)
end

function get_status()
	luci.http.prepare_content("application/json")
	local handle = io.popen("/usr/bin/visitor-board.sh status 2>/dev/null")
	local result = handle:read("*a")
	handle:close()
	luci.http.write(result)
end

function get_logs()
	local lines = luci.http.formvalue("lines") or "50"
	luci.http.prepare_content("application/json")
	local handle = io.popen("/usr/bin/visitor-board.sh logs " .. lines .. " 2>/dev/null")
	local result = handle:read("*a")
	handle:close()
	luci.http.write(result)
end

function container_action()
	local action = luci.http.formvalue("action")
	local valid = { start = true, stop = true, restart = true }
	if not valid[action] then
		luci.http.prepare_content("application/json")
		luci.http.write('{"ok":false,"error":"invalid action"}')
		return
	end
	luci.http.prepare_content("application/json")
	local handle = io.popen("/usr/bin/visitor-board.sh " .. action .. " 2>/dev/null")
	local result = handle:read("*a")
	handle:close()
	luci.http.write(result)
end
