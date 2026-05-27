# CHANGELOG

<!-- version list -->

## v1.0.0 (2026-05-27)

### Bug Fixes

- Bind production port to localhost; drop deployment section
  ([`67bce90`](https://github.com/Pondsiders/Alpha/commit/67bce902395601b27ece22bdf8608e57a6aa2d05))

- Cap recall hook output at 10K chars per Claude Code limit
  ([`754af47`](https://github.com/Pondsiders/Alpha/commit/754af4798140a69e800d606a5fe2e752c11f6d05))

- Return empty body for hook no-op instead of empty additionalContext
  ([`ca8837d`](https://github.com/Pondsiders/Alpha/commit/ca8837d400c05484196c6c319c0ae65c666d8bff))

- Sort recall results by Qwen's query order, not by cosine score
  ([`9b71220`](https://github.com/Pondsiders/Alpha/commit/9b7122074592f6b4a929afa7a59215cc4f9817dc))

- Sync pyproject.toml version to v0.1.0 tag ([#61](https://github.com/Pondsiders/Alpha/pull/61),
  [`4ebe843`](https://github.com/Pondsiders/Alpha/commit/4ebe843e7294e1689d8c62a9e9ea50f2f25f5dc5))

- **ci**: Unset LOGFIRE_TOKEN to satisfy the new settings validator
  ([`6ab2b3d`](https://github.com/Pondsiders/Alpha/commit/6ab2b3d5f50a518838f66eff7845449986d549b2))

- **compose**: Add Tailscale serve-config.json for tailnet access
  ([`5036edb`](https://github.com/Pondsiders/Alpha/commit/5036edbe36f465a7a9dda4c8f7aca7071e82e6fb))

- **compose-dev**: Reload on .md edits too, not just .py
  ([`dec6cf6`](https://github.com/Pondsiders/Alpha/commit/dec6cf693b1a123462d65eca6d74265242e0b0f6))

- **cortex**: Correct tool name in instructions from retrieve_memory to get_memory
  ([#48](https://github.com/Pondsiders/Alpha/pull/48),
  [`6e0fb3f`](https://github.com/Pondsiders/Alpha/commit/6e0fb3fda8a391272eed40a6c760135ab299106e))

- **cortex**: Route add_to_diary created_at through clock.now()
  ([#53](https://github.com/Pondsiders/Alpha/pull/53),
  [`3584e4a`](https://github.com/Pondsiders/Alpha/commit/3584e4a5b5dbec87ce4a208998f4234415a2950f))

- **hooks**: Return ToolResult to avoid Optional wrapper poisoning
  ([#24](https://github.com/Pondsiders/Alpha/pull/24),
  [`43f13c3`](https://github.com/Pondsiders/Alpha/commit/43f13c349fe01118963c1dd270acae2c634781e6))

- **mechanism**: Close asyncpg pool and AsyncOpenAI clients on shutdown
  ([#54](https://github.com/Pondsiders/Alpha/pull/54),
  [`8344f02`](https://github.com/Pondsiders/Alpha/commit/8344f02a0e1b97453aded15409dac6b30f1bf62c))

- **mechanism**: Collapse Stop-hook double-surface; pin wire shapes
  ([`197c565`](https://github.com/Pondsiders/Alpha/commit/197c56599fe1711c9d46573f637b768b0c8d0fb7))

- **mechanism**: Short-circuit memories and anamneses on slash commands
  ([#59](https://github.com/Pondsiders/Alpha/pull/59),
  [`923ec08`](https://github.com/Pondsiders/Alpha/commit/923ec08d2567b0ba794517e112e7bc28a5b1b760))

- **prompts**: Restore memories v2 (one-per-topic, sentence ceiling)
  ([`f95ce83`](https://github.com/Pondsiders/Alpha/commit/f95ce83587a25834190d556826b5db0e9d2eab75))

- **reflection**: Shift cadence to turns 3, 6, 9 (skip turn 1)
  ([`679fa16`](https://github.com/Pondsiders/Alpha/commit/679fa167151051bda39309a8d1b5a26b1f34c712))

- **tests**: Restore green after the hook→MCP cutover
  ([`4e9eb16`](https://github.com/Pondsiders/Alpha/commit/4e9eb16faafb67e722772b5cb70e384bfc682204))

- **utils**: Enforce fetch body size limit mid-stream
  ([#56](https://github.com/Pondsiders/Alpha/pull/56),
  [`8943624`](https://github.com/Pondsiders/Alpha/commit/8943624ba7fbc38c57430900629b05900e7630db))

- **utils**: Run SSRF DNS resolution off the event loop
  ([#52](https://github.com/Pondsiders/Alpha/pull/52),
  [`0e0fd65`](https://github.com/Pondsiders/Alpha/commit/0e0fd653814a9f92802f78968bc7e6ec72ecb412))

### Build System

- **docker**: Exclude tests and evals from production image
  ([#51](https://github.com/Pondsiders/Alpha/pull/51),
  [`0a56618`](https://github.com/Pondsiders/Alpha/commit/0a56618a0eb9c858d279c3c93def993484c2545d))

### Chores

- Add pre-commit config (ruff-check, ruff-format, basedpyright)
  ([`4fa9697`](https://github.com/Pondsiders/Alpha/commit/4fa9697278738b23c31c5efc79b24a5c2c52d485))

- Swap build-backend from hatchling to uv_build
  ([`c4b7352`](https://github.com/Pondsiders/Alpha/commit/c4b735286895dc2cdb132d47d3d0092f91e30dd8))

- Thin CLAUDE.md; defer general Python conventions to dotclaude rules
  ([`f7085d1`](https://github.com/Pondsiders/Alpha/commit/f7085d19345b6f3eb827a57cd38915869938d3b7))

- **compose**: Land prod tailscale-sidecar shape and per-deploy override pattern
  ([`8e5b1a7`](https://github.com/Pondsiders/Alpha/commit/8e5b1a747e6bdbde5c5fd9dcfccff42396202b19))

- **dev**: Enable uvicorn --reload and ignore alpha.dump
  ([`c2dbbdd`](https://github.com/Pondsiders/Alpha/commit/c2dbbdd5fcf57b8311a34470cc33deedf98b0b37))

- **gitignore**: Ignore eval cache and per-suite artifacts
  ([`d8b61a3`](https://github.com/Pondsiders/Alpha/commit/d8b61a394552f4e0954bc6166638c5857ef64efe))

- **justfile**: Replace stale alpha-server references with mechanism
  ([`f4c9cec`](https://github.com/Pondsiders/Alpha/commit/f4c9cec2ea5ab8d1c6af1acbf4d147b1a761430d))

### Code Style

- Fix wording in CLAUDE.md special rule about merging
  ([`da79c41`](https://github.com/Pondsiders/Alpha/commit/da79c41d3e99cabee600f5a20cc99c8373662fe4))

- Ruff format pass
  ([`a0e9502`](https://github.com/Pondsiders/Alpha/commit/a0e9502f6d6e86334d3bc1d9985bac2756ce5133))

- Switch test_store_memory SQL to triple-quoted literal
  ([`53284a1`](https://github.com/Pondsiders/Alpha/commit/53284a12e40e42449d1f49b822ed035606c6818f))

### Continuous Integration

- GitHub Actions workflow for pytest, ruff, basedpyright
  ([`1b265de`](https://github.com/Pondsiders/Alpha/commit/1b265dee678243c07de11542cdd4429715cf4a39))

### Documentation

- Add review-before-commit rule for this repository
  ([`3e62e6b`](https://github.com/Pondsiders/Alpha/commit/3e62e6beac869ba79609e5a550c1ffac32239e09))

- Correct CLAUDE.md claim about coexisting dev stacks
  ([#50](https://github.com/Pondsiders/Alpha/pull/50),
  [`ee5fe04`](https://github.com/Pondsiders/Alpha/commit/ee5fe04fab2f00373400c86c7cf2146574d26d83))

- Refresh CLAUDE.md for the Starlette + three-FastMCP architecture
  ([`b677a72`](https://github.com/Pondsiders/Alpha/commit/b677a72e6b2b00b83b7cd641ffb85522ca877a23))

- Update CLAUDE.md to remove author name and email requirements
  ([`0978da2`](https://github.com/Pondsiders/Alpha/commit/0978da2419b22f45d3ae25a61fbd6f502ee734ac))

- **evals**: Update memories eval docstrings to current module path
  ([#49](https://github.com/Pondsiders/Alpha/pull/49),
  [`d545231`](https://github.com/Pondsiders/Alpha/commit/d545231a5bbdd3c3a5a1642c361523a1424d486a))

- **origin_validation**: Document buffering constraint, closes #34
  ([#62](https://github.com/Pondsiders/Alpha/pull/62),
  [`cf98fd0`](https://github.com/Pondsiders/Alpha/commit/cf98fd039c8dd35683814f5147a935d2e72c18f3))

### Features

- Add .dockerignore; uv cache mount on deps layer
  ([`df39a4b`](https://github.com/Pondsiders/Alpha/commit/df39a4b1193f91442faca40f6ae37cc7d00d9ef2))

- Add /hooks/anamneses for explicit-reference recall
  ([`923a4b8`](https://github.com/Pondsiders/Alpha/commit/923a4b8158f0d466f2bdb60680b28086b0914518))

- Add Logfire instrumentation for TTFT investigation
  ([`d66e85e`](https://github.com/Pondsiders/Alpha/commit/d66e85ee87225db097d9e41bf69b51bc9985ed03))

- Add Origin header validation middleware (MCP-spec MUST)
  ([`40328ba`](https://github.com/Pondsiders/Alpha/commit/40328baf3f2649595b5525d5ca6d31b6af1f8813))

- Add utils MCP server with fetch tool
  ([`49af2ca`](https://github.com/Pondsiders/Alpha/commit/49af2ca8d4fcf8a53d14cd00c0b9de657327e6d8))

- Drop bearer-token auth; trust boundary is the host
  ([`e9e606c`](https://github.com/Pondsiders/Alpha/commit/e9e606c4bf606e5aad7ee7f50f0869bbc218bb1b))

- Enable per-checkout dev compose overrides
  ([`79a56c1`](https://github.com/Pondsiders/Alpha/commit/79a56c1379a82b0f92811d7498f22cb093c5513b))

- **auth**: Require MECHANISM_TOKEN, drop the optional path
  ([`bce49e1`](https://github.com/Pondsiders/Alpha/commit/bce49e1cd812299384e4a789dc7f7df3cb8207e2))

- **ci**: Add release pipeline (PSR + changelog + Docker publish)
  ([#63](https://github.com/Pondsiders/Alpha/pull/63),
  [`9338386`](https://github.com/Pondsiders/Alpha/commit/9338386f65799ef8fd68593b536ffe83a8a7319c))

- **evals**: Generalize harness with P/R/F1, suite layout, compare_prompts
  ([`43eaabb`](https://github.com/Pondsiders/Alpha/commit/43eaabbefe6577d292af9624259b0ffa32aeb50d))

- **evals**: Restore harness and wire to post-cutover code
  ([`5c427e5`](https://github.com/Pondsiders/Alpha/commit/5c427e562108604c1c14fb6d140a31386f681088))

- **evals**: Runner with two-score scoring, first baseline landed
  ([`fe627bd`](https://github.com/Pondsiders/Alpha/commit/fe627bdee7b89b13bb9d2517d57677eb55568bea))

- **evals**: Scaffold extract-queries eval harness, dataset extractor
  ([`43d0aca`](https://github.com/Pondsiders/Alpha/commit/43d0acac8c08bab51597948592bebb584f8328f9))

- **evals**: Scaffold Pydantic Evals loader for the memories-prompt eval
  ([`1382670`](https://github.com/Pondsiders/Alpha/commit/1382670b95ee984da4664decb01d1a89abf26eee))

- **mcp**: Declare anthropic/alwaysLoad in every tool's _meta
  ([`42ee80a`](https://github.com/Pondsiders/Alpha/commit/42ee80a731fef906586c0e556cc93b478f74fe3d))

- **memories**: Prompt v2 — distinct queries, sentence cap
  ([`fb4a731`](https://github.com/Pondsiders/Alpha/commit/fb4a731d3d09f47542b4697d37e1b743bc1a4a01))

- **settings**: Make LOGFIRE_TOKEN/OTEL_SERVICE_NAME optional but coupled
  ([`deda578`](https://github.com/Pondsiders/Alpha/commit/deda5780001063d836ab8ee7b1ef2238e28d42e4))

- **tests**: Isolated test stack with first hook and tool tests
  ([`d612576`](https://github.com/Pondsiders/Alpha/commit/d6125768775dc1a2c6189f2eb19a257f9f23bded))

- **timestamp**: Elapsed-since-previous-message line on later turns
  ([#57](https://github.com/Pondsiders/Alpha/pull/57),
  [`49e7886`](https://github.com/Pondsiders/Alpha/commit/49e78860ec4e02f784800f1390df0a6187460a9e))

- **timestamp**: Return elapsed-since-previous-message line on later turns
  ([#57](https://github.com/Pondsiders/Alpha/pull/57),
  [`49e7886`](https://github.com/Pondsiders/Alpha/commit/49e78860ec4e02f784800f1390df0a6187460a9e))

### Refactoring

- Collapse dev stack into single compose-dev.yml
  ([`66eb641`](https://github.com/Pondsiders/Alpha/commit/66eb641dea86fdb1e4faaab2323f736df37cbe33))

- Migrate hook handlers to MCP tools
  ([`ab5babb`](https://github.com/Pondsiders/Alpha/commit/ab5babb7bf11fba71d38556135842ed4ca0888e7))

- Rename alpha-server to mechanism throughout the codebase
  ([`480cd3d`](https://github.com/Pondsiders/Alpha/commit/480cd3daae808914d03d6890dc146a35545b50ce))

- Rename memories prompt for hook-to-prompt mapping clarity
  ([`c2264ac`](https://github.com/Pondsiders/Alpha/commit/c2264ac526e400def20ec81b99f1f0b857054153))

- **compose-dev**: Mechanism-dev stack name, bind DBs to localhost
  ([`142444b`](https://github.com/Pondsiders/Alpha/commit/142444b8cd47d96a84599e0e40fc3f342201b790))

- **conftest**: Use Settings as gatekeeper for config detection
  ([#55](https://github.com/Pondsiders/Alpha/pull/55),
  [`a6c249c`](https://github.com/Pondsiders/Alpha/commit/a6c249c818bb4b93edb43ae1348f86d00fbfa60d))

- **deps**: Use PEP 735 dependency-groups for dev tooling
  ([`2024a70`](https://github.com/Pondsiders/Alpha/commit/2024a70b8c9e67d09c2906a6695dc3702f7cde3e))

- **hooks**: Remove legacy FastAPI sub-app ([#23](https://github.com/Pondsiders/Alpha/pull/23),
  [`45635ab`](https://github.com/Pondsiders/Alpha/commit/45635ab1559ea0d1a9ead4e1287a0a1034d4ae41))

- **mechanism**: Defer hook-shaped tools from the model's tool surface
  ([#60](https://github.com/Pondsiders/Alpha/pull/60),
  [`aad12f6`](https://github.com/Pondsiders/Alpha/commit/aad12f62cbfcda732de71a9d1dbb8eaa4b6b758e))

- **mechanism**: Move prompts out of the Python package
  ([`f4f8529`](https://github.com/Pondsiders/Alpha/commit/f4f8529b49ea618fdf5875c752bf454880f96ccc))

- **mechanism**: Unified prompt loader, deploy-isolated bundle
  ([`f07e17e`](https://github.com/Pondsiders/Alpha/commit/f07e17e45a66800db96c923bd49aa7cfb46246f1))

- **tests**: Replace compose-test stack with Testcontainers
  ([`f8f55d5`](https://github.com/Pondsiders/Alpha/commit/f8f55d535e09be4aed3927c4257e9ff0c8ed1928))

- **timestamp**: Store last-msg as UTC ISO, not local-offset
  ([#57](https://github.com/Pondsiders/Alpha/pull/57),
  [`49e7886`](https://github.com/Pondsiders/Alpha/commit/49e78860ec4e02f784800f1390df0a6187460a9e))

### Testing

- Add LLM-mock fixture and memories hook end-to-end test
  ([`d0ae989`](https://github.com/Pondsiders/Alpha/commit/d0ae989c8b724b14f1f16eac2b522899aade1629))

- Add seed-fixture infrastructure and get_memory test
  ([`fc26255`](https://github.com/Pondsiders/Alpha/commit/fc262556c2d2652b44f634dd08b7e34c8ca495f1))

- Cover reflection and timestamp MCP tools
  ([`4dae21e`](https://github.com/Pondsiders/Alpha/commit/4dae21edd42092c0d79f69f396e8321e64baa761))

- Pin /hooks/anamneses end-to-end chain
  ([`5e676ff`](https://github.com/Pondsiders/Alpha/commit/5e676ff12c2d77195f7b2eba4fd8e8a258d274d7))

- Pin /hooks/timestamp gap-clause contract
  ([`8dca17a`](https://github.com/Pondsiders/Alpha/commit/8dca17a270343c2d35078c058b7f0a8fafcbdf44))

- Pin anamneses and memories envelope shapes incl. no-op path
  ([`f49419f`](https://github.com/Pondsiders/Alpha/commit/f49419fff126da8dbe4a8c960c106df5e7d71aa3))

- Pin read_from_diary against seed
  ([`1b5ff77`](https://github.com/Pondsiders/Alpha/commit/1b5ff77a09cbc74cd06f874e6a496fce4e1d1a85))

- Pin recent_memories against seed
  ([`dc9686a`](https://github.com/Pondsiders/Alpha/commit/dc9686a2c9c5e35712fbcf765bb1a3cdb9fc242d))

- Pin store_memory writes content + embedding
  ([`bded4b7`](https://github.com/Pondsiders/Alpha/commit/bded4b756b1d77baa5a23ec0514786447806ae8a))

- Smoke test for GET /livez
  ([`9172700`](https://github.com/Pondsiders/Alpha/commit/9172700ec6ac2f4629e0c6a5e050619e3f2390e1))

- **conftest**: Stub Settings env vars so tests run without .env
  ([#55](https://github.com/Pondsiders/Alpha/pull/55),
  [`a6c249c`](https://github.com/Pondsiders/Alpha/commit/a6c249c818bb4b93edb43ae1348f86d00fbfa60d))


## v0.1.0 (2026-05-19)

- Initial Release
