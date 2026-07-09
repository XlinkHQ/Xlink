# xlink-sdk

Official Python SDK for the [XLink](https://github.com/XlinkHQ/Xlink) panel HTTP API.
Minimal, typed, and dependency-light (only `httpx`).

## Install

```bash
pip install xlink-sdk
# or, from this repo:
pip install ./sdk/python
```

## Authentication

The SDK authenticates with an **API key** (not the admin JWT flow). Create one in
the panel under **API Keys** — the secret (`xlk_<prefix>_<secret>`) is shown only
once, so store it immediately. The key inherits the scope of the admin that
created it.

## Usage

```python
from xlink_sdk import XLinkClient

GIB = 2**30
with XLinkClient("https://panel.example.com", "xlk_ab12cd34_your-secret") as client:
    # create a user with a 10 GiB cap
    user = client.create_user(username="alice", data_limit_bytes=10 * GIB)

    # get their subscription link (give this to the VPN client)
    sub = client.get_user_subscription_token(user.id)
    print(sub.subscription_url)

    # check usage
    usage = client.get_user_usage(user.id)
    print(usage.used_bytes, "of", usage.limit_bytes)
```

## What's covered

| Area | Methods |
| --- | --- |
| Users | `create_user`, `get_user`, `list_users`, `update_user`, `delete_user`, `enable_user`, `disable_user`, `restore_user`, `revoke_user_subscription` |
| Subscription | `get_user_subscription_token`, `get_my_subscription_token` |
| Usage / traffic | `get_user_usage`, `get_users_usage`, `get_user_usage_series`, `get_user_node_usage`, `reset_user_usage` |
| Nodes (read) | `list_nodes`, `get_node` |
| Profiles (read) | `list_profiles`, `get_profile` |
| Groups (read) | `list_groups`, `get_group` |
| Assignments | `create_assignment`, `list_assignments`, `get_assignment` |

List endpoints return a `CursorPage` — pass the previous page's `next_cursor` as
the `cursor=` argument to page forward.

## Errors

Any non-2xx response raises `XLinkAPIError`, parsed from the panel's error
envelope:

```python
from xlink_sdk import XLinkAPIError

try:
    client.create_user(username="alice")
except XLinkAPIError as exc:
    print(exc.status, exc.code, exc.message)  # e.g. 409 conflict "..."
```
