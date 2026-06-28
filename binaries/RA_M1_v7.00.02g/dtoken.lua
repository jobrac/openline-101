-- Copyright 2009 Steven Barth <steven@midlink.org>
-- Copyright 2009 Jo-Philipp Wich <jow@openwrt.org>
-- Licensed to the public under the Apache License 2.0.

local M = {} 

local fs = require "nixio.fs"
local json  = require "luci.jsonc"
local nx = require "nixio"


local function logger_print(flag, message)
	nx.openlog("JYTL_TO"..flag.."_"..arg[0]:match(".+/(%S+)$"):upper())
	nx.syslog("info",message)
	nx.closelog()
end

local function get_developmode(dtoken, token)
	if get_debug_mode() == 99 then
		return 1
	end

	local develop_mode = 0
	if token ~= '-' and token == dtoken then
		develop_mode = 1
	else
		develop_mode = 0
	end
	
	return develop_mode
end

local function get_debug_mode()
	local debug_mode = fs.readfile("/data/jytl_factory/debug_mode") or '0'
	debug_mode = tonumber(debug_mode)
	
	return debug_mode
end

local function check_acl(methods, func, mode)
	local method = methods[func]
	
	if not method then
		print(json.stringify({ error = "Method not found" }))
		os.exit(1)
	end
	
	local super = (method.super and 1 or 0)
	
	if super == 1 and mode == 0 then
		return false
	end

	return true
end

function M.develop_mode_exit()
	os.execute("rm -f /tmp/jy_developer_mode")
	os.execute("rm -f /tmp/jy_developer_token")
end

function M.is_invalid(dtoken, token)
	local invalid = false
	if (token ~= '-' and token ~= dtoken) or (token == '-' and dtoken ~= '-') then
		invalid = true
	else
		invalid = false
	end
	
	return invalid
end

function M.is_not_develop(token)
	if token == '-' then
		return true
	end
	
	return false
end

function M.is_debug_mode()
	if get_debug_mode() == 99 then
		return true
	end
	
	return false
end

function M.auth_ubus_acl(rpc_sid, methods, func, dtoken)
	local token = fs.readfile("/tmp/jy_developer_token") or '-'
	
	if not rpc_sid then
		return true
	end
	
	-- DEBUG MODE BYPASS: skip ALL checks when debug_mode=99
	if M.is_debug_mode() then
		return true
	end

	if M.is_invalid(dtoken, token) then
		print(json.stringify({ error = "Invalid token" }))
		logger_print('FL',"ubus call "..func.." result: Invalid token, dtoken: "..dtoken..", token: "..token)
		M.develop_mode_exit()
		os.exit(1)
		return false
	end

	if not check_acl(methods, func, get_developmode(dtoken, token)) then
		if not M.is_debug_mode() then
			print(json.stringify({ error = "ACL error" }))
			logger_print('FL',"ubus call "..func.." result: ACL Err, dtoken: "..dtoken..", token: "..token)
			M.develop_mode_exit()
			os.exit(1)
			return false
		end
	end
	
	return true
end

function M.check_luci_acl(super, token)
	if M.is_not_develop(token) and super then
		return false
	end
	
	return true
end

M.ST_OK=0
M.ST_INVALID_TOKEN=1
M.ST_ACL_ERR=2


function M.check_luci_acl_st(dtoken, super)
	-- DEBUG MODE BYPASS: skip ALL checks when debug_mode=99
	if M.is_debug_mode() then
		return M.ST_OK
	end

	local token = fs.readfile("/tmp/jy_developer_token") or '-'
	
	if M.is_invalid(dtoken, token) then
		return M.ST_INVALID_TOKEN
	end

	if not M.is_debug_mode() then
		if not M.check_luci_acl(super, token) then
			return M.ST_ACL_ERR
		end
	end
	
	return M.ST_OK
end

return M

