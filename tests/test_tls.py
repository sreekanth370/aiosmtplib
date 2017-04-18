"""
TLS and STARTTLS handling.
"""
import asyncio.sslproto
import ssl
from pathlib import Path

import pytest

from aiosmtplib import SMTP, SMTPConnectError, SMTPStatus, SMTPTimeoutError


pytestmark = pytest.mark.asyncio(forbid_global_loop=True)


async def test_tls_connection(tls_preset_client):
    """
    Use an explicit connect/quit here, as other tests use the context manager.
    """
    await tls_preset_client.connect()
    assert tls_preset_client.is_connected

    await tls_preset_client.quit()
    assert not tls_preset_client.is_connected


async def test_starttls(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'\n'.join([
            b'250-localhost, hello',
            b'250-SIZE 100000',
            b'250 STARTTLS',
        ]))
        preset_client.server.responses.append(b'220 ready for TLS')
        response = await preset_client.starttls(validate_certs=False)
        assert response.code == SMTPStatus.ready

        # Make sure our state has been cleared
        assert not preset_client.esmtp_extensions
        assert not preset_client.supported_auth_methods
        assert not preset_client.supports_esmtp

        # make sure our connection was actually upgraded
        assert isinstance(
            preset_client.transport, asyncio.sslproto._SSLProtocolTransport)

        preset_client.server.responses.append(b'250 all good')
        response = await preset_client.ehlo()
        assert response.code == SMTPStatus.completed


async def test_starttls_timeout(preset_client):
    async with preset_client:
        preset_client.server.responses.append(b'\n'.join([
            b'250-localhost, hello',
            b'250-SIZE 100000',
            b'250 STARTTLS',
        ]))
        await preset_client.ehlo()

        preset_client.timeout = 0.1
        preset_client.server.responses.append(b'220 ready for TLS')
        preset_client.server.delay_next_response = 1

        with pytest.raises(SMTPTimeoutError):
            await preset_client.starttls(validate_certs=False)


async def test_tls_get_transport_info(tls_preset_client):
    async with tls_preset_client:
        compression = tls_preset_client.get_transport_info('compression')
        assert compression is None  # Compression is not used here

        peername = tls_preset_client.get_transport_info('peername')
        assert peername[0] == tls_preset_client.hostname
        assert peername[1] == tls_preset_client.port

        sock = tls_preset_client.get_transport_info('socket')
        assert sock is not None

        sockname = tls_preset_client.get_transport_info('sockname')
        assert sockname is not None

        cipher = tls_preset_client.get_transport_info('cipher')
        assert cipher is not None

        peercert = tls_preset_client.get_transport_info('peercert')
        assert peercert is not None

        sslcontext = tls_preset_client.get_transport_info('sslcontext')
        assert sslcontext is not None

        sslobj = tls_preset_client.get_transport_info('ssl_object')
        assert sslobj is not None


async def test_tls_smtp_connect_to_non_tls_server(preset_server, event_loop):
    tls_client = SMTP(
        hostname='127.0.0.1', port=preset_server.port, loop=event_loop,
        use_tls=True, validate_certs=False)

    with pytest.raises(SMTPConnectError):
        await tls_client.connect()
    assert not tls_client.is_connected


async def test_tls_connection_with_existing_sslcontext(tls_preset_client):
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    await tls_preset_client.connect(tls_context=context)
    assert tls_preset_client.is_connected

    assert tls_preset_client.tls_context is context

    await tls_preset_client.quit()
    assert not tls_preset_client.is_connected


async def test_tls_connection_with_client_cert(tls_preset_client):
    cert_path = str(Path('tests/certs/selfsigned.crt'))
    key_path = str(Path('tests/certs/selfsigned.key'))

    await tls_preset_client.connect(
        hostname='localhost', validate_certs=True, client_cert=cert_path,
        client_key=key_path, cert_bundle=cert_path)
    assert tls_preset_client.is_connected

    await tls_preset_client.quit()
    assert not tls_preset_client.is_connected
