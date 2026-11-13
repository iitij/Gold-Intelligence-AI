# Open decisions and assumptions

| ID | Question | Current handling |
|---|---|---|
| DEC-001 | GitHub destination owner and repository visibility | **RESOLVED 2026-11-07:** private iitij/Gold-Intelligence-AI |
| DEC-002 | Exact NVIDIA VRAM, RAM, disk on workstation | inventory task; no GPU training decision until known |
| DEC-003 | MT5 Wine bridge viability and broker symbol | proof-of-concept, demo only |
| DEC-004 | Broker tick/contract sizing and timezone conventions | collect specs, prohibit execution before verified |
| DEC-005 | Original market-data source and raw history duration | source/hash, acquisition settings and technical coverage; no additional rights investigation |
| DEC-006 | Exact Qwen checkpoint and context size | **PARTLY RESOLVED:** Qwen3-4B and Qwen3.5-2B commit SHAs pinned, Hugging Face license metadata checked; weights not downloaded, runtime compatibility/context still require validation; no additional license review |
| DEC-007 | Selected research horizons / spread acceptance | M15 4/8/16 initial hypothesis, optimize only via research protocol |
| DEC-008 | Company/repository code license and publication decision | unset; private default |
| DEC-009 | Vendor scope: complete source or approved modules | **RESOLVED 2026-11-07:** archived 584 full-source files at verified pinned SHAs for Aurum, TradingAgents and Midas; operational integration/security remains pending |
| DEC-010 | Whether human approval is removed after demo maturity | not pre-authorized; requires separate change request |
