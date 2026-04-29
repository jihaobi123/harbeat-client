import redis
r = redis.from_url("redis://harbeat-redis:6379/0")
ttl = r.ttl("harbeat:analysis_lock")
val = r.get("harbeat:analysis_lock")
print(f"Lock value: {val}")
print(f"Lock TTL: {ttl} seconds")
if ttl > 0:
    print(f"Lock expires in: {ttl//60}m {ttl%60}s")
elif ttl == -1:
    print("Lock exists but has NO TTL (permanent!)")
elif ttl == -2:
    print("Lock does not exist (FREE)")
