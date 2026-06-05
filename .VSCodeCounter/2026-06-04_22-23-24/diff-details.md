# Diff Details

Date : 2026-06-04 22:23:24

Directory /Users/parsa/Desktop/Xlink

Total : 72 files,  4482 codes, 0 comments, 821 blanks, all 5303 lines

[Summary](results.md) / [Details](details.md) / [Diff Summary](diff.md) / Diff Details

## Files
| filename | language | code | comment | blank | total |
| :--- | :--- | ---: | ---: | ---: | ---: |
| [.claude/settings.json](/.claude/settings.json) | JSON with Comments | 6 | 0 | 0 | 6 |
| [alembic/versions/0007\_traffic\_records.py](/alembic/versions/0007_traffic_records.py) | Python | 56 | 0 | 8 | 64 |
| [alembic/versions/0008\_advanced\_agent.py](/alembic/versions/0008_advanced_agent.py) | Python | 172 | 0 | 11 | 183 |
| [app/agent/command\_service.py](/app/agent/command_service.py) | Python | 118 | 0 | 13 | 131 |
| [app/agent/commands.py](/app/agent/commands.py) | Python | 65 | 0 | 18 | 83 |
| [app/agent/config\_sync.py](/app/agent/config_sync.py) | Python | 115 | 0 | 15 | 130 |
| [app/agent/domain.py](/app/agent/domain.py) | Python | 121 | 0 | 28 | 149 |
| [app/agent/healing.py](/app/agent/healing.py) | Python | 71 | 0 | 15 | 86 |
| [app/agent/provider\_health.py](/app/agent/provider_health.py) | Python | 63 | 0 | 11 | 74 |
| [app/agent/reconcile.py](/app/agent/reconcile.py) | Python | 105 | 0 | 12 | 117 |
| [app/agent/repository.py](/app/agent/repository.py) | Python | 126 | 0 | 21 | 147 |
| [app/agent/service.py](/app/agent/service.py) | Python | 140 | 0 | 16 | 156 |
| [app/agent/streaming.py](/app/agent/streaming.py) | Python | 48 | 0 | 13 | 61 |
| [app/agent/tests/test\_advanced\_agent.py](/app/agent/tests/test_advanced_agent.py) | Python | 278 | 0 | 42 | 320 |
| [app/agent/tests/test\_agent\_traffic.py](/app/agent/tests/test_agent_traffic.py) | Python | 143 | 0 | 23 | 166 |
| [app/api/v1/router.py](/app/api/v1/router.py) | Python | 1 | 0 | 0 | 1 |
| [app/api/v1/routers/agent.py](/app/api/v1/routers/agent.py) | Python | 190 | 0 | 23 | 213 |
| [app/core/config.py](/app/core/config.py) | Python | 38 | 0 | 7 | 45 |
| [app/core/lifespan.py](/app/core/lifespan.py) | Python | 45 | 0 | 3 | 48 |
| [app/db/base.py](/app/db/base.py) | Python | 1 | 0 | 1 | 2 |
| [app/db/session.py](/app/db/session.py) | Python | 19 | 0 | 1 | 20 |
| [app/dependencies/services.py](/app/dependencies/services.py) | Python | 13 | 0 | 0 | 13 |
| [app/domain/\_\_init\_\_.py](/app/domain/__init__.py) | Python | 18 | 0 | 0 | 18 |
| [app/events/models.py](/app/events/models.py) | Python | 18 | 0 | 6 | 24 |
| [app/monitoring/metrics.py](/app/monitoring/metrics.py) | Python | 7 | 0 | 4 | 11 |
| [app/monitoring/service.py](/app/monitoring/service.py) | Python | 22 | 0 | 0 | 22 |
| [app/monitoring/summary.py](/app/monitoring/summary.py) | Python | 101 | 0 | 17 | 118 |
| [app/monitoring/tests/test\_metrics\_summary.py](/app/monitoring/tests/test_metrics_summary.py) | Python | 126 | 0 | 18 | 144 |
| [app/monitoring/tests/test\_monitoring.py](/app/monitoring/tests/test_monitoring.py) | Python | 12 | 0 | 0 | 12 |
| [app/providers/xray/adapter.py](/app/providers/xray/adapter.py) | Python | 2 | 0 | 0 | 2 |
| [app/providers/xray/exceptions.py](/app/providers/xray/exceptions.py) | Python | 9 | 0 | 6 | 15 |
| [app/providers/xray/payloads.py](/app/providers/xray/payloads.py) | Python | 13 | 0 | 7 | 20 |
| [app/providers/xray/stream.py](/app/providers/xray/stream.py) | Python | 116 | 0 | 16 | 132 |
| [app/providers/xray/tests/test\_xray\_transport.py](/app/providers/xray/tests/test_xray_transport.py) | Python | 105 | 0 | 40 | 145 |
| [app/providers/xray/validator.py](/app/providers/xray/validator.py) | Python | 45 | 0 | 2 | 47 |
| [app/schemas/agent.py](/app/schemas/agent.py) | Python | 92 | 0 | 48 | 140 |
| [app/subscription/formats/\_\_init\_\_.py](/app/subscription/formats/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [app/subscription/formats/base.py](/app/subscription/formats/base.py) | Python | 51 | 0 | 24 | 75 |
| [app/subscription/formats/base64.py](/app/subscription/formats/base64.py) | Python | 7 | 0 | 5 | 12 |
| [app/subscription/formats/http\_proxy.py](/app/subscription/formats/http_proxy.py) | Python | 23 | 0 | 6 | 29 |
| [app/subscription/formats/hysteria2.py](/app/subscription/formats/hysteria2.py) | Python | 27 | 0 | 6 | 33 |
| [app/subscription/formats/naive.py](/app/subscription/formats/naive.py) | Python | 20 | 0 | 6 | 26 |
| [app/subscription/formats/shadowsocks.py](/app/subscription/formats/shadowsocks.py) | Python | 19 | 0 | 6 | 25 |
| [app/subscription/formats/socks.py](/app/subscription/formats/socks.py) | Python | 23 | 0 | 6 | 29 |
| [app/subscription/formats/text.py](/app/subscription/formats/text.py) | Python | 5 | 0 | 4 | 9 |
| [app/subscription/formats/trojan.py](/app/subscription/formats/trojan.py) | Python | 20 | 0 | 6 | 26 |
| [app/subscription/formats/tuic.py](/app/subscription/formats/tuic.py) | Python | 28 | 0 | 6 | 34 |
| [app/subscription/formats/uri.py](/app/subscription/formats/uri.py) | Python | 36 | 0 | 7 | 43 |
| [app/subscription/formats/vless.py](/app/subscription/formats/vless.py) | Python | 43 | 0 | 8 | 51 |
| [app/subscription/formats/vmess.py](/app/subscription/formats/vmess.py) | Python | 38 | 0 | 8 | 46 |
| [app/subscription/renderer.py](/app/subscription/renderer.py) | Python | 20 | 0 | 2 | 22 |
| [app/subscription/schemas.py](/app/subscription/schemas.py) | Python | 13 | 0 | 0 | 13 |
| [app/subscription/tests/test\_transport\_rendering.py](/app/subscription/tests/test_transport_rendering.py) | Python | 150 | 0 | 24 | 174 |
| [app/tests/test\_advanced\_agent\_endpoints.py](/app/tests/test_advanced_agent_endpoints.py) | Python | 164 | 0 | 27 | 191 |
| [app/tests/test\_agent\_endpoint.py](/app/tests/test_agent_endpoint.py) | Python | 100 | 0 | 17 | 117 |
| [app/tests/test\_db\_pool.py](/app/tests/test_db_pool.py) | Python | 60 | 0 | 23 | 83 |
| [app/tests/test\_pg\_concurrency.py](/app/tests/test_pg_concurrency.py) | Python | 124 | 0 | 26 | 150 |
| [app/traffic/\_\_init\_\_.py](/app/traffic/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [app/traffic/collector.py](/app/traffic/collector.py) | Python | 44 | 0 | 9 | 53 |
| [app/traffic/models.py](/app/traffic/models.py) | Python | 46 | 0 | 9 | 55 |
| [app/traffic/repository.py](/app/traffic/repository.py) | Python | 101 | 0 | 14 | 115 |
| [app/traffic/retention.py](/app/traffic/retention.py) | Python | 19 | 0 | 9 | 28 |
| [app/traffic/scheduler.py](/app/traffic/scheduler.py) | Python | 53 | 0 | 11 | 64 |
| [app/traffic/schemas.py](/app/traffic/schemas.py) | Python | 44 | 0 | 20 | 64 |
| [app/traffic/service.py](/app/traffic/service.py) | Python | 102 | 0 | 13 | 115 |
| [app/traffic/tests/\_\_init\_\_.py](/app/traffic/tests/__init__.py) | Python | 0 | 0 | 1 | 1 |
| [app/traffic/tests/conftest.py](/app/traffic/tests/conftest.py) | Python | 43 | 0 | 12 | 55 |
| [app/traffic/tests/test\_traffic.py](/app/traffic/tests/test_traffic.py) | Python | 247 | 0 | 30 | 277 |
| [load\_audit.py](/load_audit.py) | Python | 25 | 0 | 0 | 25 |
| [pg\_concurrency\_audit.py](/pg_concurrency_audit.py) | Python | 136 | 0 | 29 | 165 |
| [pyproject.toml](/pyproject.toml) | TOML | 4 | 0 | 0 | 4 |
| [scale\_audit.py](/scale_audit.py) | Python | 27 | 0 | 0 | 27 |

[Summary](results.md) / [Details](details.md) / [Diff Summary](diff.md) / Diff Details