from __future__ import annotations

import asyncio

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.cache import CacheProtocol
from app.core.logging import get_logger

logger = get_logger("xlink.acme")

CHALLENGE_PREFIX = "acme:challenge:"
ACCOUNT_KEY_CACHE = "acme:account_key"
_CHALLENGE_TTL = 600
_LETSENCRYPT_PROD = "https://acme-v02.api.letsencrypt.org/directory"
_LETSENCRYPT_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"


class AcmeError(Exception):
    pass


async def get_challenge(cache: CacheProtocol, token: str) -> str | None:
    return await cache.client.get(CHALLENGE_PREFIX + token)


def _new_account_key() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _issue_blocking(
    domain: str, account_key_pem: str, directory_url: str, email: str, set_challenge, del_challenge
) -> tuple[str, str]:
    import josepy as jose
    from acme import challenges, client, crypto_util, messages
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa

    account_key = serialization.load_pem_private_key(account_key_pem.encode(), password=None)
    jwk_key = jose.JWKRSA(key=account_key)
    net = client.ClientNetwork(jwk_key, user_agent="xlink-acme")
    directory = client.ClientV2.get_directory(directory_url, net)
    acme_client = client.ClientV2(directory, net=net)

    registration = messages.NewRegistration.from_data(
        email=email or None, terms_of_service_agreed=True
    )
    try:
        acme_client.new_account(registration)
    except messages.Error as exc:
        if "already" not in str(exc).lower():
            raise

    domain_key = _rsa.generate_private_key(public_exponent=65537, key_size=2048)
    domain_key_pem = domain_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    csr_pem = crypto_util.make_csr(domain_key_pem, [domain])
    order = acme_client.new_order(csr_pem)

    # Track every challenge token we publish so it is removed from Redis on ANY
    # exit path — a poll_and_finalize timeout/failure previously left the
    # validation values dangling in the cache because cleanup ran only on the
    # success path.
    published_tokens: list[str] = []
    try:
        for authz in order.authorizations:
            http_challenge = None
            for ch in authz.body.challenges:
                if isinstance(ch.chall, challenges.HTTP01):
                    http_challenge = ch
                    break
            if http_challenge is None:
                raise AcmeError("No HTTP-01 challenge offered.")
            response, validation = http_challenge.response_and_validation(jwk_key)
            token = http_challenge.chall.encode("token")
            set_challenge(token, validation)
            published_tokens.append(token)
            acme_client.answer_challenge(http_challenge, response)

        finalized = acme_client.poll_and_finalize(order)
        return finalized.fullchain_pem, domain_key_pem.decode()
    finally:
        for token in published_tokens:
            del_challenge(token)


async def issue_certificate(
    cache: CacheProtocol,
    domain: str,
    email: str,
    staging: bool = False,
) -> tuple[str, str]:
    account_key_pem = await cache.client.get(ACCOUNT_KEY_CACHE)
    if not account_key_pem:
        account_key_pem = _new_account_key()
        await cache.client.set(ACCOUNT_KEY_CACHE, account_key_pem)

    def set_challenge(token: str, validation: str) -> None:
        asyncio.run_coroutine_threadsafe(
            cache.client.set(CHALLENGE_PREFIX + token, validation, ex=_CHALLENGE_TTL), loop
        ).result()

    def del_challenge(token: str) -> None:
        asyncio.run_coroutine_threadsafe(
            cache.client.delete(CHALLENGE_PREFIX + token), loop
        ).result()

    loop = asyncio.get_running_loop()
    directory_url = _LETSENCRYPT_STAGING if staging else _LETSENCRYPT_PROD
    try:
        return await asyncio.to_thread(
            _issue_blocking,
            domain,
            account_key_pem,
            directory_url,
            email,
            set_challenge,
            del_challenge,
        )
    except Exception as exc:
        logger.warning("acme_issue_failed", domain=domain, error=str(exc))
        raise AcmeError(str(exc)) from exc
