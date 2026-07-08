"""XLink SDK quickstart.

Run with:
    export XLINK_BASE_URL="https://panel.example.com"
    export XLINK_API_KEY="xlk_ab12cd34_your-secret"
    python examples/quickstart.py
"""

from __future__ import annotations

import os

from xlink_sdk import XLinkClient, XLinkAPIError

GIB = 2**30


def main() -> None:
    base_url = os.environ["XLINK_BASE_URL"]
    api_key = os.environ["XLINK_API_KEY"]

    with XLinkClient(base_url, api_key) as client:
        # 1. Create a user with a 10 GiB data cap.
        try:
            user = client.create_user(username="alice", data_limit_bytes=10 * GIB)
        except XLinkAPIError as exc:
            if exc.code == "conflict":
                # Already exists — look it up instead.
                user = next(u for u in client.list_users(search="alice").items)
            else:
                raise
        print(f"user: {user.username} ({user.id})")

        # 2. Get their subscription link (hand this to the VPN client).
        sub = client.get_user_subscription_token(user.id)
        print(f"subscription: {sub.subscription_url}")

        # 3. Check how much data they've used.
        usage = client.get_user_usage(user.id)
        cap = "unlimited" if usage.unlimited else f"{usage.limit_bytes / GIB:.1f} GiB"
        print(f"usage: {usage.used_bytes / GIB:.3f} GiB of {cap}")


if __name__ == "__main__":
    main()
