# User CSV import

Download `/api/v1/users/imports/template`; supported columns are `external_user_id,first_name,last_name,email,phone,organization_id,locale,country,source,tags,terms_accepted,marketing_allowed`. Uploads require an authenticated organization administrator and an idempotency key. Preview errors are privacy-safe; commit is explicit and asynchronous. Use only synthetic `example.invalid` addresses in staging.
