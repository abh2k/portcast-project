local state_key = KEYS[1]
local consume_key = KEYS[2]

local units = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])

if units == nil or units <= 0 then
  return {0, "invalid_units"}
end

local existing_units = redis.call("GET", consume_key)
if existing_units then
  return {1, "already_consumed"}
end

local limit = tonumber(redis.call("HGET", state_key, "limit") or "-1")
local used = tonumber(redis.call("HGET", state_key, "used") or "0")

if limit < 0 then
  return {0, "quota_not_configured"}
end

local available = limit - used
if available < units then
  return {0, "quota_exceeded"}
end

redis.call("HINCRBY", state_key, "used", units)
redis.call("SET", consume_key, tostring(units), "EX", ttl)

return {1, "consumed"}
