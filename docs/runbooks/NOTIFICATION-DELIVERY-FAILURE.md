# Notification delivery failure

Check bounded metrics by category/channel/result, then inspect the safe failure class. Retry transient failures with bounded backoff; dead-letter permanent or exhausted failures. Never mark delivered without evidence. Security-critical delivery gaps are incidents and may require an alternate approved channel.
