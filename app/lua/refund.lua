local state_key = KEYS[1]
local request_key = KEYS[2]

local ttl = tonumber(ARGV[1])

local status = redis.call("HGET", request_key, "status")
if not status then
  return {0, "consume_not_found"}
end

if status == "refunded" then
  return {1, "already_refunded"}
end

if status ~= "consumed" then
  return {0, "invalid_state"}
end

local units = tonumber(redis.call("HGET", request_key, "units"))
if units == nil or units <= 0 then
  return {0, "invalid_state"}
end

local used = tonumber(redis.call("HGET", state_key, "used") or "0")
if used < units then
  return {0, "invalid_state"}
end

redis.call("HINCRBY", state_key, "used", -units)
redis.call("HSET", request_key, "status", "refunded")
redis.call("EXPIRE", request_key, ttl)

return {1, "refunded"}
