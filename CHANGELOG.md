# Changelog

## Unreleased

Open-source release.

### Security

* Paddle webhook now fails closed when no secret is configured, rejects stale signatures, and can no longer modify admin or blocked accounts
* Image and review-page downloads are protected against SSRF (private/link-local addresses blocked, redirects re-validated, size capped)
* Login no longer leaks whether a username exists through response timing; bcrypt runs off the event loop
* Internal error details are no longer returned to API clients

### Bug Fixes

* Passwords longer than 72 bytes caused a 500 on login
* Relative "see reviews" links were resolved against the site root instead of the page
* Daily quota now resets at midnight UTC regardless of database timezone
* Reverse image search reported "no dropship domains" when every search had failed
* `httpx` was only a dev dependency but is used at runtime

### Maintenance

* Removed the Reddit brand-reputation skill and the `praw` dependency
* Shared, configurable LLM client (`VERIDEX_LLM_MODEL`) replaces twelve hard-coded instances
* Unit and Postgres-backed integration test suites; strict mypy passes
* Non-root Docker image, docker compose with Postgres, simplified CI
* MIT license

## [0.5.0](https://github.com/kroshtan/veridex_backend/compare/0.4.0...0.5.0) (2026-03-02)

### Features

* add admin functionality ([a6e58ff](https://github.com/kroshtan/veridex_backend/commit/a6e58ff2c39724df1d4cb335c57878d22a28d46a))

## [0.4.0](https://github.com/kroshtan/veridex_backend/compare/0.3.0...0.4.0) (2026-03-01)

### Features

* Add paddle for payment ([37ca493](https://github.com/kroshtan/veridex_backend/commit/37ca4938096c0cdd26e8ae865c9a091a6b36d7d6))

## [0.3.0](https://github.com/kroshtan/veridex_backend/compare/0.2.5...0.3.0) (2026-03-01)

### Features

* protect signup endpoint + lowercase usernames ([cdc8ae9](https://github.com/kroshtan/veridex_backend/commit/cdc8ae971a3cc4e5e5633a7d616f892002a50acc))

## [0.2.5](https://github.com/kroshtan/veridex_backend/compare/0.2.4...0.2.5) (2026-02-28)

## [0.2.4](https://github.com/kroshtan/veridex_backend/compare/0.2.3...0.2.4) (2026-02-27)

### Bug Fixes

* imports ([ed52b51](https://github.com/kroshtan/veridex_backend/commit/ed52b5117c8fd4d8c06cb347113e253850bad920))
* imports ([383a927](https://github.com/kroshtan/veridex_backend/commit/383a927cffae3dab886f8166fbe61b03becf118c))

## [0.2.3](https://github.com/kroshtan/veridex_backend/compare/0.2.2...0.2.3) (2026-02-27)

### Bug Fixes

* Import error ([a8308df](https://github.com/kroshtan/veridex_backend/commit/a8308dfa8dfbcef1b2aa151d73e96ad020374c41))

## [0.2.2](https://github.com/kroshtan/veridex_backend/compare/0.2.1...0.2.2) (2026-02-27)

### Bug Fixes

* Actually fix dockerfile ([6c0fd9c](https://github.com/kroshtan/veridex_backend/commit/6c0fd9c5bad40305283e9635f15c72d0fa282c12))

## [0.2.1](https://github.com/kroshtan/veridex_backend/compare/0.2.0...0.2.1) (2026-02-27)

### Bug Fixes

* Dockerfile properly installs project package ([136a719](https://github.com/kroshtan/veridex_backend/commit/136a719a98050bb9e032c0a45178191732264cdb))

## [0.2.0](https://github.com/kroshtan/veridex_backend/compare/0.1.1...0.2.0) (2026-02-27)

### Features

* add account access from web portal ([35cab30](https://github.com/kroshtan/veridex_backend/commit/35cab304728474ef49a0608cd4e7c005ada5f1af))

## [0.1.1](https://github.com/kroshtan/veridex_backend/compare/0.1.0...0.1.1) (2026-02-27)

## [0.1.0](https://github.com/kroshtan/veridex_backend/compare/0.0.1...0.1.0) (2026-02-26)

### Features

* First release ([f8fd62f](https://github.com/kroshtan/veridex_backend/commit/f8fd62f9ac795ad7b8da2ac04eb5c84006f14f36))

## 0.0.1 (2026-02-26)
