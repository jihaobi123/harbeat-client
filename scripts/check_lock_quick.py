import redis
r = redis.Redis(host='harbeat-redis')
print('Analysis lock:', r.get('harbeat:analysis_lock'))
print('TTL:', r.ttl('harbeat:analysis_lock'))
