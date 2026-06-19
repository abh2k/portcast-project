local state_key = KEYS[1]
local request_key = KEYS[2]

local units = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local org_id = ARGV[3]
local feature = ARGV[4]
local period = ARGV[5]

if units == nil or units <= 0 then
  return {0, "invalid_units"}
end

local status = redis.call("HGET", request_key, "status")
if status then
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
redis.call(
  "HSET",
  request_key,
  "org_id", org_id,
  "feature", feature,
  "period", period,
  "units", tostring(units),
  "status", "consumed"
)
redis.call("EXPIRE", request_key, ttl)

return {1, "consumed"}
