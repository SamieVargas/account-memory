# reference/pixels_rag

Verbatim copies of the pixels-rag modules that account-memory will adapt in
Parts 7, 9 and 14 (router, contracts, answer, pipeline, eval runner, MCP
server). They are here to be read and ported, not imported: nothing in
`core/` imports from this folder, and the day-log fields in them do not
apply to contracts. Each file's source commit and hash is in
`docs/PROVENANCE.md`. When a module is ported into `core/`, its copy here is
deleted and the provenance row moves from "reference" to "adapted".
