# Realtime authentication

Staging currently uses a one-time `ws_ticket` issued by the authenticated API
and consumed by Channels middleware. Tickets are not bearer URLs after use and
legacy routes remain protected by the same middleware. Centrifugo migration
requires short-lived signed connection tokens plus logout/revocation support;
it is not enabled until that contract exists.
