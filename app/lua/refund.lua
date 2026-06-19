local state_key = KEYS[1]
local consume_key = KEYS[2]
local refund_key = KEYS[3]

local ttl = tonumber(ARGV[1])

local existing_refund = redis.call("GET", refund_key)
if existing_refund then
  return {1, "already_refunded"}
end

local consumed_units = redis.call("GET", consume_key)
if not consumed_units then
  return {0, "consume_not_found"}
end

local units = tonumber(consumed_units)
if units == nil or units <= 0 then
  return {0, "invalid_state"}
end

local used = tonumber(redis.call("HGET", state_key, "used") or "0")
if used < units then
  return {0, "invalid_state"}
end

redis.call("HINCRBY", state_key, "used", -units)
redis.call("SET", refund_key, tostring(units), "EX", ttl)

return {1, "refunded"}
