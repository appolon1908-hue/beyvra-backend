# Realtime authorization

The `/ws/v1/` gateway derives tenant membership server-side and validates
market channels against the supported instrument/interval registry. Demo event
groups are tenant and user scoped. Cross-tenant and forbidden-channel tests are
required before private account channels are added.
