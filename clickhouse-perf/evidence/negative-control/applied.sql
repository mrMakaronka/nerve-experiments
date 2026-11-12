ALTER TABLE bench.hits ADD INDEX idx_url URL TYPE bloom_filter GRANULARITY 4;
ALTER TABLE bench.hits MATERIALIZE INDEX idx_url SETTINGS mutations_sync = 2;
ALTER SETTINGS PROFILE dashboard_profile SETTINGS max_execution_time = 600, max_threads = 32;
