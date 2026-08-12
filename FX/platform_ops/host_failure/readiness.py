def topology(hosts,regions):return {"multi_host_ha":"YES" if hosts>1 else "NO","multi_region_ha":"YES" if regions>1 else "NO","regional_failover":"IMPLEMENTED" if regions>1 else "NOT_IMPLEMENTED"}
